"""Time, session, funding and risk-budget rules shared by replay and live.

Everything here is pure: it takes timestamps / numbers and returns decisions.
No SDK calls.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable

from .params import DECISION_INTERVAL_MINUTES, PlaybookParams

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# clock helpers
# --------------------------------------------------------------------------- #
def to_utc(ts: Any) -> datetime:
    """Accept datetime / pandas.Timestamp / epoch-ns int and return aware UTC datetime."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    if hasattr(ts, "to_pydatetime"):
        dt = ts.to_pydatetime()
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    if isinstance(ts, (int, float)):
        # epoch nanoseconds (Nautilus) or milliseconds
        value = float(ts)
        if value > 1e14:
            value = value / 1e9
        elif value > 1e11:
            value = value / 1e3
        return datetime.fromtimestamp(value, tz=UTC)
    raise TypeError(f"unsupported timestamp type {type(ts)!r}")


def parse_hhmm(text: str) -> time:
    hh, mm = text.strip().split(":")
    return time(int(hh), int(mm), tzinfo=UTC)


def parse_windows(windows: Iterable[str]) -> list[tuple[time, time]]:
    out = []
    for w in windows:
        start, end = [part.strip() for part in w.split("-")]
        out.append((parse_hhmm(start), parse_hhmm(end)))
    return out


def in_session(now: datetime, params: PlaybookParams) -> bool:
    """Entry window check: start inclusive, end exclusive (UTC)."""
    t = now.astimezone(UTC).time().replace(tzinfo=UTC)
    for start, end in parse_windows(params.session_windows):
        if start <= t < end:
            return True
    return False


def minutes_to_next_funding(now: datetime, params: PlaybookParams) -> float:
    now = now.astimezone(UTC)
    candidates = []
    for day_offset in (0, 1):
        base = (now + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        for hour in params.funding_hours_utc:
            candidates.append(base + timedelta(hours=int(hour)))
    future = [c for c in candidates if c > now]
    nxt = min(future)
    return (nxt - now).total_seconds() / 60.0


def funding_flatten_due(now: datetime, params: PlaybookParams) -> bool:
    """True inside the pre-funding window (effective lead >= decision interval)."""
    return minutes_to_next_funding(now, params) <= params.effective_funding_lead_minutes


def position_pays_funding(side: str, funding_rate: float | None) -> bool | None:
    """Longs pay when the rate is positive, shorts pay when it is negative.
    Returns None when the rate is unknown (caller decides the fallback)."""
    if funding_rate is None or not math.isfinite(float(funding_rate)):
        return None
    rate = float(funding_rate)
    if side == "long":
        return rate > 0
    if side == "short":
        return rate < 0
    return None


def eod_flatten_due(now: datetime, params: PlaybookParams) -> bool:
    t = now.astimezone(UTC).time().replace(tzinfo=UTC)
    return t >= parse_hhmm(params.eod_flatten_time)


def minutes_to_eod_flatten(now: datetime, params: PlaybookParams) -> float:
    now = now.astimezone(UTC)
    eod = parse_hhmm(params.eod_flatten_time)
    target = now.replace(hour=eod.hour, minute=eod.minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds() / 60.0


def time_stop_due(opened_at: datetime, now: datetime, params: PlaybookParams) -> bool:
    return (now - opened_at).total_seconds() / 60.0 >= params.time_stop_minutes


def utc_day_key(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# daily risk ledger
# --------------------------------------------------------------------------- #
@dataclass
class DailyLedger:
    day: str = ""
    realized_pnl_usdt: float = 0.0
    trades_by_symbol: dict[str, int] | None = None
    halted: bool = False
    halt_reason: str = ""

    def __post_init__(self) -> None:
        if self.trades_by_symbol is None:
            self.trades_by_symbol = {}

    def roll(self, now: datetime) -> bool:
        key = utc_day_key(now)
        if key != self.day:
            self.day = key
            self.realized_pnl_usdt = 0.0
            self.trades_by_symbol = {}
            self.halted = False
            self.halt_reason = ""
            return True
        return False

    def record_entry(self, symbol: str) -> None:
        self.trades_by_symbol[symbol] = self.trades_by_symbol.get(symbol, 0) + 1

    def record_pnl(self, pnl_usdt: float, params: PlaybookParams) -> None:
        self.realized_pnl_usdt += float(pnl_usdt)
        if self.realized_pnl_usdt <= -params.daily_loss_cap_usdt and not self.halted:
            self.halted = True
            self.halt_reason = "daily_loss_cap"

    def symbol_budget_left(self, symbol: str, params: PlaybookParams) -> bool:
        return self.trades_by_symbol.get(symbol, 0) < params.max_trades_per_day_symbol

    def as_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "realized_pnl_usdt": round(self.realized_pnl_usdt, 6),
            "trades_by_symbol": dict(self.trades_by_symbol),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "DailyLedger":
        raw = raw or {}
        return cls(
            day=str(raw.get("day", "")),
            realized_pnl_usdt=float(raw.get("realized_pnl_usdt", 0.0) or 0.0),
            trades_by_symbol=dict(raw.get("trades_by_symbol", {}) or {}),
            halted=bool(raw.get("halted", False)),
            halt_reason=str(raw.get("halt_reason", "")),
        )


# --------------------------------------------------------------------------- #
# sizing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SizePlan:
    qty: float
    notional_usdt: float
    margin_usdt: float
    risk_usdt: float
    capped_by_margin: bool
    ok: bool
    reason: str


def size_from_risk(limit_price: float, stop_price: float, params: PlaybookParams,
                   size_step: float, min_qty: float) -> SizePlan:
    """qty = risk_usdt / |entry - stop|, capped so margin <= margin_budget."""
    distance = abs(float(limit_price) - float(stop_price))
    if distance <= 0 or limit_price <= 0:
        return SizePlan(0.0, 0.0, 0.0, 0.0, False, False, "zero_stop_distance")
    risk = params.risk_usdt_per_trade
    qty = risk / distance
    max_notional = params.margin_budget * params.leverage
    capped = False
    if qty * limit_price > max_notional:
        qty = max_notional / limit_price
        capped = True
    if size_step > 0:
        qty = math.floor(qty / size_step) * size_step
    qty = float(f"{qty:.12g}")
    if qty <= 0 or qty < min_qty:
        return SizePlan(qty, qty * limit_price, qty * limit_price / params.leverage, qty * distance, capped, False, "below_min_qty")
    notional = qty * limit_price
    return SizePlan(qty, notional, notional / params.leverage, qty * distance, capped, True, "ok")


def can_open_new(now: datetime, params: PlaybookParams, ledger: DailyLedger, symbol: str,
                 open_positions: int, pending_entries: int, has_exposure_on_symbol: bool,
                 reconcile_flags: int, notional_24h: float | None, spread_bps: float | None) -> tuple[bool, str]:
    """All entry gates except signal logic. Order matters for the reason code."""
    if ledger.halted:
        return False, f"halted:{ledger.halt_reason}"
    if reconcile_flags and params.halt_on_reconcile_mismatch:
        return False, "halted:reconcile_mismatch"
    if not in_session(now, params):
        return False, "outside_session"
    if has_exposure_on_symbol:
        return False, "symbol_already_exposed"
    if open_positions + pending_entries >= params.max_concurrent_positions:
        return False, "max_concurrent"
    if not ledger.symbol_budget_left(symbol, params):
        return False, "max_trades_per_day_symbol"
    if funding_flatten_due(now, params):
        return False, "pre_funding_window"
    if eod_flatten_due(now, params):
        return False, "eod"
    if notional_24h is not None and notional_24h < params.min_24h_notional_usdt:
        return False, "volume_below_min"
    if spread_bps is not None and spread_bps > params.max_spread_bps:
        return False, "spread_above_max"
    return True, "ok"


def trail_stop(side: str, entry: float, best_excursion: float, current_stop: float, r: float,
               params: PlaybookParams) -> float | None:
    """Signal B trailing: once MFE >= trail_r * R, keep the stop trail_r*R behind the best price.
    Returns a new stop only when it improves on the current stop."""
    trail = params.signal_b_trail_r * r
    if side == "long":
        if best_excursion - entry < trail:
            return None
        candidate = best_excursion - trail
        return candidate if candidate > current_stop else None
    if best_excursion <= 0:
        return None
    if entry - best_excursion < trail:
        return None
    candidate = best_excursion + trail
    return candidate if candidate < current_stop else None
