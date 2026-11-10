"""Single source of truth for every tunable in RUNECLAW Intraday Session Flow.

Both execution paths build a ``PlaybookParams`` object:

* live  -> ``PlaybookParams.from_config(runtime.manifest["strategy_config"])``
* replay -> ``main_backtest`` copies the same ``strategy_config`` into the
  Nautilus strategy config, and ``strategy.py`` rebuilds ``PlaybookParams``
  from its own fields.

Defaults below MUST match ``manifest.yaml -> strategy_config``.  The table in
``docs/.../PARAMETERS.md`` is generated from the same values.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

PLAYBOOK_VERSION = "0.8.1"
DECISION_INTERVAL_MINUTES = 15  # 15m execution bars and 15m live cadence


def _as_tuple(value: Any, cast=str) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    return tuple(cast(item) for item in value)


@dataclass(frozen=True)
class PlaybookParams:
    # --- universe / sizing -------------------------------------------------
    trading_symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
    margin_budget: float = 1000.0          # USDT; risk denominator + platform return basis
    leverage: int = 3
    risk_pct_per_trade: float = 0.5        # % of margin_budget risked between entry and stop
    min_24h_notional_usdt: float = 200_000_000.0
    max_spread_bps: float = 3.0            # live-only gate (needs L1 quote)
    # --- regime / bias -----------------------------------------------------
    regime_atr_period: int = 14            # on 4H bars
    regime_atr_pct_min: float = 0.6
    regime_atr_pct_max: float = 3.0
    bias_ema_period: int = 20              # on 1H closes
    bias_flat_slope_pct: float = 0.05      # |slope| below this = "flat"
    # --- sessions (UTC) ----------------------------------------------------
    session_windows: tuple[str, ...] = ("07:00-10:00", "13:30-16:30")
    # --- Signal A: VWAP reversion -----------------------------------------
    enable_signal_a: bool = False      # v0.4: disabled for one version to isolate Signal B
    vwap_anchor: str = "utc_day"
    vwap_trigger_sigma: float = 1.5
    vwap_limit_sigma: float = 1.0
    vwap_stop_sigma: float = 2.0
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    signal_a_expiry_minutes: int = 45
    # --- Signal B: volume-spike breakout ----------------------------------
    enable_signal_b: bool = True
    volume_spike_mult: float = 2.5     # v0.5 value (v0.6 tried 3.0, not adopted)
    volume_median_bars: int = 20
    breakout_lookback_bars: int = 20
    # Entry limit price for Signal B. "midpoint" is the default (v0.5 behaviour).
    # "close" (tested as v0.8.0) stays available but failed both evaluation windows.
    signal_b_entry_mode: str = "midpoint"
    signal_b_expiry_minutes: int = 30
    signal_b_target_r: float = 2.0     # v0.5 value (v0.6 tried 1.5, not adopted)
    signal_b_trail_r: float = 1.0
    # --- funding rule ------------------------------------------------------
    funding_hours_utc: tuple[int, ...] = (0, 8, 16)
    funding_flatten_lead_minutes: int = 10
    funding_direction_aware: bool = True   # live: only when the position pays funding
    # --- risk limits -------------------------------------------------------
    max_concurrent_positions: int = 2
    max_trades_per_day_symbol: int = 3
    daily_loss_cap_pct: float = 1.5
    daily_cap_flatten: bool = True
    time_stop_minutes: int = 180      # v0.5: 120 → 180 (14 of 109 v0.4 trades were cut by the time stop)
    eod_flatten_time: str = "23:45"
    # --- ops ---------------------------------------------------------------
    reconcile_interval_minutes: int = 5    # requested cadence; effective = scheduler cadence
    halt_on_reconcile_mismatch: bool = True
    backtest_days: int = 90
    warmup_days: int = 5
    max_backtest_symbols: int = 4   # 180 s sandbox budget: ~20 s data + replay per symbol
    # Pinned evaluation end so successive versions replay the same bars; move it only
    # when a new baseline window is adopted (record it in CHANGELOG.md).
    backtest_end_utc: str = "2026-11-09T17:15:00+00:00"

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None) -> "PlaybookParams":
        cfg = dict(cfg or {})
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in cfg or cfg[f.name] is None:
                continue
            raw = cfg[f.name]
            if f.name in ("trading_symbols", "session_windows"):
                kwargs[f.name] = _as_tuple(raw, str)
            elif f.name == "funding_hours_utc":
                kwargs[f.name] = _as_tuple(raw, int)
            elif f.type in ("bool", bool):
                kwargs[f.name] = bool(raw) if not isinstance(raw, str) else raw.strip().lower() in ("1", "true", "yes")
            elif f.type in ("int", int):
                kwargs[f.name] = int(raw)
            elif f.type in ("float", float):
                kwargs[f.name] = float(raw)
            else:
                kwargs[f.name] = str(raw)
        return cls(**kwargs)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value
        return out

    @property
    def risk_usdt_per_trade(self) -> float:
        return self.margin_budget * self.risk_pct_per_trade / 100.0

    @property
    def daily_loss_cap_usdt(self) -> float:
        return self.margin_budget * self.daily_loss_cap_pct / 100.0

    @property
    def effective_funding_lead_minutes(self) -> int:
        # With 15-minute decision points a 10-minute lead can never be observed;
        # the rule fires at the last decision point before funding instead.
        return max(self.funding_flatten_lead_minutes, DECISION_INTERVAL_MINUTES)


def signal_id(symbol: str, kind: str, ts) -> str:
    """Deterministic id: RC-<symbol>-<A|B>-<YYYYMMDDTHHMM> (UTC)."""
    stamp = ts.strftime("%Y%m%dT%H%M")
    return f"RC-{symbol}-{kind}-{stamp}"
