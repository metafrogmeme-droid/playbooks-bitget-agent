"""Live follow-trade path (runs on the 15-minute schedule).

Per run:
 1. load persisted state, roll the UTC day ledger
 2. RECONCILE journal vs exchange positions / pending orders (every run; the
    platform scheduler floor is 15 minutes, so the requested 5-minute cadence
    is honoured as "every scheduled run")
 3. per symbol: fetch closed 15m bars, compute features, read ticker (24h
    volume, spread) and the current funding rate, build ONE decision
 4. emit the decision with ``runtime.emit_signal_or_follow``; the managed
    permission gate decides whether ``execution.execute`` runs
 5. persist state + write run artifacts

Decision actions / intents (``meta.intent``):
    long|short + open      new limit entry with attached TP/SL
    long|short + manage    position already open on that side; adjust TP/SL
    close      + flatten   exit now (time stop, funding, EOD, daily cap)
    close      + cancel_expired  cancel an expired resting entry
    hold                   nothing actionable
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from getagent import backtest, data, runtime, trade

from . import execution, features, journal as journal_mod, risk
from .params import PlaybookParams, signal_id
from .risk import DailyLedger

UTC = timezone.utc
BARS_TO_FETCH = 600          # ~6 days of 15m bars: enough for 4H ATR warm-up + 24h notional
STALE_AFTER_MINUTES = 30     # refuse to act when newest closed bar is older than 2 intervals


def _records(payload: Any) -> list[dict[str, Any]]:
    try:
        return [r for r in data.to_records(payload) if isinstance(r, dict)]
    except Exception:  # noqa: BLE001
        return journal_mod.records_from(payload)


def _ticker_info(symbol: str) -> dict[str, Any]:
    info: dict[str, Any] = {"quote_volume_24h": None, "spread_bps": None, "last": None}
    try:
        rows = _records(data.crypto.futures.ticker(symbol=symbol, exchange="bitget"))
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"ticker: {exc}"
        return info
    if not rows:
        info["error"] = "ticker: empty"
        return info
    row = rows[0]
    info["quote_volume_24h"] = journal_mod.first_number(row, ("quote_volume",))
    info["last"] = journal_mod.first_number(row, ("last",))
    bid = journal_mod.first_number(row, ("bid",))
    ask = journal_mod.first_number(row, ("ask",))
    if bid and ask and bid > 0 and ask >= bid:
        info["spread_bps"] = (ask - bid) / ((ask + bid) / 2.0) * 1e4
    return info


def _current_funding_rate(symbol: str) -> float | None:
    """Latest funding rate for the symbol; None when unavailable (never a constant)."""
    for sym in (symbol, symbol.replace("USDT", "")):
        try:
            rows = _records(data.crypto.futures.funding_rate(symbol=sym, exchange="bitget", interval="1h", limit=1))
        except Exception:  # noqa: BLE001
            continue
        if rows:
            value = journal_mod.first_number(rows[-1], ("funding_rate", "estimated_rate"))
            if value is not None:
                return value
    return None


def _fetch_features(symbol: str, params: PlaybookParams, now: datetime) -> tuple[pd.DataFrame | None, str]:
    bars = data.crypto.futures.kline(symbol=symbol, interval="15m", exchange="bitget", limit=BARS_TO_FETCH, closed_only=True)
    frame = backtest.prepare_frame(bars)
    if frame is None or frame.empty:
        return None, "no_bars"
    frame = frame.sort_index()
    last_open = frame.index[-1].to_pydatetime()
    if last_open.tzinfo is None:
        last_open = last_open.replace(tzinfo=UTC)
    age_min = (now - (last_open + timedelta(minutes=15))).total_seconds() / 60.0
    if age_min > STALE_AFTER_MINUTES:
        return None, f"stale_feed:{age_min:.0f}m"
    return features.compute_features(frame, params), "ok"


def _hold(symbol: str, reason: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    d = {"symbol": symbol, "action": "hold", "intent": "none", "reason": reason, "confidence": 0.0,
         "metrics": {}, "meta": {}}
    if extra:
        d["meta"].update(extra)
    return d


def decide(symbol: str, feats: pd.DataFrame | None, feed_status: str, ticker: dict[str, Any],
           funding_rate: float | None, now: datetime, params: PlaybookParams, ledger: DailyLedger,
           state: dict[str, Any]) -> dict[str, Any]:
    """Pure decision for one symbol.  Returns a dict consumed by execution.execute."""
    open_trade = state["open"].get(symbol)
    pending = state["pending"].get(symbol)

    # ---- 1. open position: exits first, then management ---------------------
    if open_trade:
        side = open_trade["side"]
        opened_at = risk.to_utc(datetime.fromisoformat(open_trade["opened_at"]))
        exit_reason = ""
        if risk.eod_flatten_due(now, params):
            exit_reason = "eod_flatten"
        elif ledger.halted and params.daily_cap_flatten:
            exit_reason = "daily_loss_cap"
        elif risk.funding_flatten_due(now, params):
            pays = risk.position_pays_funding(side, funding_rate)
            if not params.funding_direction_aware or pays or pays is None:
                exit_reason = "funding_window" if pays else "funding_window_rate_unknown"
        if not exit_reason and risk.time_stop_due(opened_at, now, params):
            exit_reason = "time_stop"
        if exit_reason:
            return {"symbol": symbol, "action": "close", "intent": "flatten", "reason": exit_reason, "confidence": 0.9,
                    "metrics": {"funding_rate": funding_rate}, "meta": {"signal_id": open_trade["signal_id"], "intent": "flatten"}}
        if feats is None:
            return _hold(symbol, f"manage_skipped:{feed_status}")
        row = feats.iloc[-1]
        decision = {"symbol": symbol, "action": side, "intent": "manage", "reason": "manage", "confidence": 0.5,
                    "metrics": {}, "meta": {"signal_id": open_trade["signal_id"], "intent": "manage"}}
        changed = False
        if open_trade["kind"] == "A" and math.isfinite(float(row["vwap_session"])):
            decision["new_target"] = float(row["vwap_session"])
            changed = abs(decision["new_target"] - float(open_trade["target"])) > 0
        if open_trade["kind"] == "B":
            best = float(open_trade.get("best_excursion") or open_trade["entry_price"])
            best = max(best, float(row["high"])) if side == "long" else min(best, float(row["low"]))
            decision["best_excursion"] = best
            new_stop = risk.trail_stop(side, float(open_trade["entry_price"]), best, float(open_trade["stop"]),
                                       float(open_trade["r_distance"]), params)
            if new_stop is not None:
                decision["new_stop"] = new_stop
                changed = True
            elif best != float(open_trade.get("best_excursion") or 0.0):
                changed = True  # persist the new excursion even without a stop move
        if not changed:
            return _hold(symbol, "position_open_no_change", {"signal_id": open_trade["signal_id"]})
        return decision

    # ---- 2. resting entry: expire or wait -----------------------------------
    if pending:
        expires_at = risk.to_utc(datetime.fromisoformat(pending["expires_at"]))
        if now >= expires_at:
            return {"symbol": symbol, "action": "close", "intent": "cancel_expired", "reason": "entry_expired",
                    "confidence": 0.9, "metrics": {}, "meta": {"signal_id": pending["signal_id"], "intent": "cancel_expired"}}
        return _hold(symbol, "pending_entry_active", {"signal_id": pending["signal_id"]})

    # ---- 3. flat: gates then signals ----------------------------------------
    if feats is None:
        return _hold(symbol, f"no_features:{feed_status}")
    row = feats.iloc[-1]
    ok, why = features.regime_ok(row, params)
    if not ok:
        return _hold(symbol, why, {"atr4h_pct": row.get("atr4h_pct")})
    ok, why = risk.can_open_new(
        now, params, ledger, symbol,
        open_positions=len(state["open"]), pending_entries=len(state["pending"]),
        has_exposure_on_symbol=False, reconcile_flags=len(state.get("reconcile_flags", [])),
        notional_24h=ticker.get("quote_volume_24h"), spread_bps=ticker.get("spread_bps"),
    )
    if not ok:
        return _hold(symbol, why, {"spread_bps": ticker.get("spread_bps"), "quote_volume_24h": ticker.get("quote_volume_24h")})
    candidates = features.detect_signals(row, params)
    if not candidates:
        return _hold(symbol, "no_signal", {"rsi": row.get("rsi"), "bias_slope_pct": row.get("bias_slope_pct")})
    cand = sorted(candidates, key=lambda c: 0 if c.kind == "B" else 1)[0]   # trend signal takes priority
    size = risk.size_from_risk(cand.limit_price, cand.stop_price, params, size_step=0.0, min_qty=0.0)
    if not size.ok:
        return _hold(symbol, f"sizing:{size.reason}", {"candidate": cand.as_dict()})
    bar_open = feats.index[-1]
    sid = signal_id(symbol, cand.kind, bar_open)
    expires_at = (now + timedelta(minutes=cand.expiry_minutes)).isoformat()
    return {
        "symbol": symbol, "action": cand.side, "intent": "open", "reason": f"signal_{cand.kind}",
        "signal_id": sid, "candidate": cand.as_dict(), "size": size.__dict__, "expires_at": expires_at,
        "confidence": 0.65 if cand.kind == "B" else 0.6,
        "metrics": {
            "limit_price": cand.limit_price, "stop_price": cand.stop_price, "target_price": cand.target_price,
            "r_distance": cand.r_distance, "risk_usdt": size.risk_usdt, "notional_usdt": size.notional_usdt,
            "min_open_notional_usdt": None, "sizing_ok": size.ok, "spread_bps": ticker.get("spread_bps"),
            "quote_volume_24h": ticker.get("quote_volume_24h"), "funding_rate": funding_rate,
        },
        "meta": {"signal_id": sid, "intent": "open", "kind": cand.kind, "reasons": list(cand.reasons),
                 "expires_at": expires_at, "bar_open_ts": bar_open.isoformat()},
    }


def run() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    params = PlaybookParams.from_config(cfg)
    now = datetime.now(UTC)
    state = journal_mod.load_state()
    ledger = DailyLedger.from_dict(state.get("ledger"))
    ledger.roll(now)
    journal = journal_mod.Journal()

    # ---- reconciliation (read-only trade queries) ---------------------------
    pos_records: list[dict[str, Any]] = []
    pending_payload: Any = None
    try:
        pos_records = trade.helpers.contract_position_records(trade.contract.current_position())
        pending_payload = trade.contract.pending_orders()
        journal_mod.reconcile(
            state=state, pos_records=pos_records, pending_payload=pending_payload,
            fills_lookup=lambda sym, oid: journal_mod.records_from(trade.contract.fills(symbol=sym, order_id=oid, limit=20)),
            now=now, params=params, ledger=ledger, journal=journal,
        )
    except Exception as exc:  # noqa: BLE001 - without exchange truth we must not open anything
        state["reconcile_flags"] = [{"type": "reconcile_failed", "error": str(exc), "seen_at": now.isoformat()}]
        journal.log(signal_id="", timestamp=now, symbol="", side="", event="reconcile_flag", note=f"reconcile failed: {exc}")

    decisions: list[dict[str, Any]] = []
    for symbol in params.trading_symbols:
        try:
            feats, feed_status = _fetch_features(symbol, params, now)
        except Exception as exc:  # noqa: BLE001
            feats, feed_status = None, f"kline_error:{exc}"
        ticker = _ticker_info(symbol)
        funding_rate = _current_funding_rate(symbol) if state["open"].get(symbol) else None
        decision = decide(symbol, feats, feed_status, ticker, funding_rate, now, params, ledger, state)
        decisions.append(decision)
        metrics = dict(decision.get("metrics") or {})
        metrics.update({"daily_pnl_usdt": ledger.realized_pnl_usdt, "reconcile_flags": len(state.get("reconcile_flags", [])),
                        "feed_status": feed_status})
        meta = dict(decision.get("meta") or {})
        meta.update({"reason": decision["reason"], "playbook_version": state.get("playbook_version"), "run_id": runtime.run_id})
        runtime.emit_signal_or_follow(
            action=decision["action"],
            symbol=symbol,
            confidence=float(decision.get("confidence", 0.0)),
            metrics=metrics,
            meta=meta,
            execute_trade=lambda d=decision: execution.execute(d, params, state, ledger, journal, now),
            reason_code=decision["reason"],
            reason_text=f"{decision['action']} {symbol}: {decision['reason']}",
            reason_locale="en",
        )

    state["ledger"] = ledger.as_dict()
    state["last_run"] = now.isoformat()
    journal.flush()
    journal_mod.save_state(state)
    journal_mod.write_run_outputs(decisions=decisions, journal=journal, state=state, run_id=str(runtime.run_id), now=now)
