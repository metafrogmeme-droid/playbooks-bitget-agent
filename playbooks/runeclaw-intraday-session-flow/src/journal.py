"""Order journal, persisted state and position/fill reconciliation (live path).

Persistence contract (see sandbox-runtime.md): only ``.state/`` may survive
between runs, and the runner hydrates/syncs it.  Everything else is rewritten
each run.  Per-run artifacts go to ``output/`` (package-relative) where the
Runner collects ``*.json`` / ``*.csv``.

Journal row schema (one row per order event):
    signal_id, timestamp, symbol, side, event, order_id, limit_price,
    fill_price, stop, target, qty, exit_reason, note
Events: entry_placed, entry_filled, entry_expired, entry_cancelled,
        stop_set, target_set, stop_modified, target_modified,
        flatten_requested, exit, reconcile_flag
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .params import PLAYBOOK_VERSION, PlaybookParams
from .risk import DailyLedger, to_utc

UTC = timezone.utc
# Paths are relative to the package working directory (the runner executes
# `python -m src.main` from the package root and collects `<package>/output/*`).
STATE_DIR = Path(".state") / "runeclaw"
OUTPUT_DIR = Path("output")
STATE_FILE = STATE_DIR / "state.json"
ORDERS_FILE = STATE_DIR / "orders.jsonl"

JOURNAL_FIELDS = (
    "signal_id", "timestamp", "symbol", "side", "event", "order_id", "limit_price",
    "fill_price", "stop", "target", "qty", "exit_reason", "note",
)


def _iso(ts: Any) -> str:
    return to_utc(ts).isoformat() if ts is not None else ""


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def empty_state() -> dict[str, Any]:
    return {
        "playbook_version": PLAYBOOK_VERSION,
        "ledger": DailyLedger().as_dict(),
        "pending": {},          # symbol -> pending entry order
        "open": {},             # symbol -> open trade
        "reconcile_flags": [],  # unresolved mismatches
        "last_run": "",
        "last_reconcile": "",
    }


def load_state() -> dict[str, Any]:
    try:
        if STATE_FILE.exists():
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                base = empty_state()
                base.update(raw)
                return base
    except (OSError, ValueError):
        pass
    return empty_state()


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


class Journal:
    """Collects order rows for this run and appends them to the persistent log."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def log(self, *, signal_id: str, timestamp: Any, symbol: str, side: str, event: str,
            order_id: str = "", limit_price: Any = None, fill_price: Any = None,
            stop: Any = None, target: Any = None, qty: Any = None,
            exit_reason: str = "", note: str = "") -> dict[str, Any]:
        row = {
            "signal_id": signal_id,
            "timestamp": _iso(timestamp),
            "symbol": symbol,
            "side": side,
            "event": event,
            "order_id": str(order_id or ""),
            "limit_price": _finite(limit_price),
            "fill_price": _finite(fill_price),
            "stop": _finite(stop),
            "target": _finite(target),
            "qty": _finite(qty),
            "exit_reason": exit_reason,
            "note": note,
        }
        self.rows.append(row)
        return row

    def flush(self) -> None:
        if not self.rows:
            return
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with ORDERS_FILE.open("a", encoding="utf-8") as fh:
            for row in self.rows:
                fh.write(json.dumps(row, default=str) + "\n")


def write_run_outputs(*, decisions: list[dict[str, Any]], journal: Journal, state: dict[str, Any],
                      run_id: str, now: datetime) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "decisions.json").write_text(
        json.dumps({"run_id": run_id, "generated_at": _iso(now), "decisions": decisions}, indent=2, default=str),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "orders_log.json").write_text(
        json.dumps({"run_id": run_id, "fields": list(JOURNAL_FIELDS), "rows": journal.rows}, indent=2, default=str),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "state_snapshot.json").write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


# --------------------------------------------------------------------------- #
# payload parsing helpers (Trade SDK payload shapes are normalized defensively)
# --------------------------------------------------------------------------- #
_PRICE_KEYS = ("priceAvg", "price_avg", "fillPrice", "fill_price", "price", "openPriceAvg", "averageOpenPrice",
               "avgPrice", "open_price_avg")
_ORDER_ID_KEYS = ("orderId", "order_id", "clientOid", "client_oid")


def first_number(record: Any, keys: tuple[str, ...]) -> float | None:
    if not isinstance(record, dict):
        return None
    for key in keys:
        if key in record:
            value = _finite(record[key])
            if value is not None:
                return value
    return None


def extract_order_id(payload: Any) -> str:
    """Find an order id in a Trade SDK result envelope (dict / nested data / list)."""
    if payload is None:
        return ""
    if isinstance(payload, dict):
        for key in _ORDER_ID_KEYS:
            if payload.get(key):
                return str(payload[key])
        for nested_key in ("data", "result", "order", "raw"):
            nested = payload.get(nested_key)
            found = extract_order_id(nested)
            if found:
                return found
        return ""
    if isinstance(payload, (list, tuple)):
        for item in payload:
            found = extract_order_id(item)
            if found:
                return found
        return ""
    for attr in ("order_id", "orderId", "raw", "data"):
        if hasattr(payload, attr):
            found = extract_order_id(getattr(payload, attr))
            if found:
                return found
    return ""


def records_from(payload: Any) -> list[dict[str, Any]]:
    """Normalize list-ish envelopes (`data`, `data.list`, `orders`, `entrustedList`) into dict rows."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "result", "list", "orders", "entrustedList", "fillList", "positions"):
            if key in payload:
                rows = records_from(payload[key])
                if rows:
                    return rows
        return []
    for attr in ("data", "raw"):
        if hasattr(payload, attr):
            rows = records_from(getattr(payload, attr))
            if rows:
                return rows
    return []


def pending_order_ids(pending_payload: Any, symbol: str = "") -> set[str]:
    ids: set[str] = set()
    for row in records_from(pending_payload):
        if symbol and str(row.get("symbol", "")).upper() not in ("", symbol.upper()):
            continue
        for key in _ORDER_ID_KEYS[:2]:
            if row.get(key):
                ids.add(str(row[key]))
    return ids


def position_side_and_size(pos_records: list[dict[str, Any]], symbol: str) -> tuple[str, float]:
    """Return ("long"|"short"|"", size) for a symbol from normalized position records."""
    for row in pos_records:
        if str(row.get("symbol", "")).upper() != symbol.upper():
            continue
        size = first_number(row, ("total", "size", "available", "holdSize", "hold_size")) or 0.0
        if size <= 0:
            continue
        side = str(row.get("holdSide") or row.get("hold_side") or row.get("side") or "").lower()
        if side in ("long", "short"):
            return side, size
    return "", 0.0


# --------------------------------------------------------------------------- #
# reconciliation
# --------------------------------------------------------------------------- #
def reconcile(*, state: dict[str, Any], pos_records: list[dict[str, Any]], pending_payload: Any,
              fills_lookup, now: datetime, params: PlaybookParams, ledger: DailyLedger,
              journal: Journal) -> list[dict[str, Any]]:
    """Compare journaled expectations with exchange truth.  Mutates ``state``.

    * pending order gone + position present  -> entry filled (record fill)
    * pending order gone + no position       -> expired/cancelled externally (flag)
    * open trade + no position               -> closed by exchange TP/SL or externally (record exit)
    * exchange position with no journal      -> untracked exposure (flag, halts entries)
    ``fills_lookup(symbol, order_id) -> list[dict]`` is injected so this module
    stays free of SDK imports.
    """
    flags: list[dict[str, Any]] = []
    live_pending = pending_order_ids(pending_payload)

    for symbol, pend in list(state.get("pending", {}).items()):
        order_id = str(pend.get("order_id", ""))
        if order_id and order_id in live_pending:
            continue
        side, size = position_side_and_size(pos_records, symbol)
        if side == pend.get("side") and size > 0:
            fill_price = None
            try:
                for rec in fills_lookup(symbol, order_id) or []:
                    fill_price = first_number(rec, _PRICE_KEYS)
                    if fill_price is not None:
                        break
            except Exception as exc:  # noqa: BLE001 - fill lookup is best effort
                journal.log(signal_id=pend["signal_id"], timestamp=now, symbol=symbol, side=side,
                            event="reconcile_flag", order_id=order_id, note=f"fills lookup failed: {exc}")
            if fill_price is None:
                fill_price = first_number(next((r for r in pos_records if str(r.get("symbol", "")).upper() == symbol.upper()), {}), _PRICE_KEYS)
            if fill_price is None:
                fill_price = pend.get("limit_price")
                note = "fill price unavailable; using limit price"
            else:
                note = ""
            trade = {
                "signal_id": pend["signal_id"],
                "kind": pend["kind"],
                "side": side,
                "qty": size,
                "entry_price": fill_price,
                "stop": pend["stop"],
                "target": pend["target"],
                "r_distance": pend["r_distance"],
                "opened_at": now.isoformat(),
                "best_excursion": fill_price,
                "entry_order_id": order_id,
            }
            state["open"][symbol] = trade
            ledger.record_entry(symbol)
            journal.log(signal_id=pend["signal_id"], timestamp=now, symbol=symbol, side=side, event="entry_filled",
                        order_id=order_id, limit_price=pend["limit_price"], fill_price=fill_price,
                        stop=pend["stop"], target=pend["target"], qty=size, note=note)
        else:
            journal.log(signal_id=pend["signal_id"], timestamp=now, symbol=symbol, side=pend.get("side", ""),
                        event="entry_expired", order_id=order_id, limit_price=pend.get("limit_price"),
                        note="order left the pending list without a position (GTD expiry or external cancel)")
        del state["pending"][symbol]

    for symbol, trade in list(state.get("open", {}).items()):
        side, size = position_side_and_size(pos_records, symbol)
        if side == trade.get("side") and size > 0:
            if abs(size - float(trade.get("qty", 0.0) or 0.0)) > 1e-9:
                trade["qty"] = size
            continue
        exit_price = None
        try:
            for rec in fills_lookup(symbol, "") or []:
                exit_price = first_number(rec, _PRICE_KEYS)
                if exit_price is not None:
                    break
        except Exception:  # noqa: BLE001
            exit_price = None
        stop, target = float(trade["stop"]), float(trade["target"])
        if exit_price is None:
            reason, pnl, note = "exchange_exit_unknown_price", None, "closed on exchange; fill price unavailable"
        else:
            reason = "stop_hit" if abs(exit_price - stop) <= abs(exit_price - target) else "target_hit"
            sign = 1.0 if trade["side"] == "long" else -1.0
            pnl = sign * (exit_price - float(trade["entry_price"])) * float(trade["qty"])
            note = "exit reason inferred from fill price proximity"
        if pnl is not None:
            ledger.record_pnl(pnl, params)
        journal.log(signal_id=trade["signal_id"], timestamp=now, symbol=symbol, side=trade["side"], event="exit",
                    order_id=trade.get("entry_order_id", ""), fill_price=exit_price, stop=stop, target=target,
                    qty=trade.get("qty"), exit_reason=reason, note=f"{note}; pnl_usdt={pnl}")
        del state["open"][symbol]

    tracked = set(state.get("open", {}).keys())
    for row in pos_records:
        symbol = str(row.get("symbol", "")).upper()
        size = first_number(row, ("total", "size", "available", "holdSize", "hold_size")) or 0.0
        if symbol and size > 0 and symbol not in tracked:
            flag = {"type": "untracked_position", "symbol": symbol, "size": size, "seen_at": now.isoformat()}
            flags.append(flag)
            journal.log(signal_id="", timestamp=now, symbol=symbol, side=str(row.get("holdSide", "")), event="reconcile_flag",
                        qty=size, note="exchange position without journal entry")

    for symbol, pend in state.get("pending", {}).items():
        if pend.get("order_id") and pend["order_id"] not in live_pending:
            flags.append({"type": "pending_mismatch", "symbol": symbol, "order_id": pend["order_id"], "seen_at": now.isoformat()})

    state["reconcile_flags"] = flags
    state["last_reconcile"] = now.isoformat()
    return flags
