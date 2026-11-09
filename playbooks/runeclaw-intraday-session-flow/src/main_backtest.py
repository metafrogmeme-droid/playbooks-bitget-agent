"""Historical replay driver (never imports getagent.trade).

1. fetch closed 15m Bitget bars per symbol in <=1000-bar pages
2. hand raw OHLCV to the replay engine; ``strategy.py`` computes the same
   features incrementally (``features.IncrementalFeatures``) so the platform's
   own evidence replay with raw bars produces identical decisions
3. inject manifest.strategy_config into the Nautilus strategy config
4. fetch historical funding rates per symbol (direction-aware funding rule;
   missing data is reported as degraded, never replaced by a constant)
5. run the managed replay, write the output contract files, evaluate the
   pre-registered pass criteria and emit one ``watch`` summary signal
"""
from __future__ import annotations

import copy
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from getagent import backtest, data, runtime

from .params import PLAYBOOK_VERSION, PlaybookParams

UTC = timezone.utc
OUTPUT_DIR = Path("output")  # package-relative; the Runner collects <package>/output/*
PAGE_BARS = 1000
BAR = timedelta(minutes=15)

# Pre-registered pass criteria for v0.1 (see docs/VERSIONING.md). Do not edit after the first live run.
PASS_CRITERIA = {"min_round_trips": 60, "min_profit_factor": 1.3, "max_drawdown_pct_of_budget": 6.0}


def _sanitize(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def fetch_15m(symbol: str, start: datetime, end: datetime) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Page through [start, end) in 1000-bar windows; de-duplicate by open time."""
    frames: list[pd.DataFrame] = []
    pages = empty_pages = 0
    cursor = start
    while cursor < end:
        page_end = min(cursor + PAGE_BARS * BAR, end)
        bars = data.crypto.futures.kline(
            symbol=symbol, interval="15m", exchange="bitget", limit=PAGE_BARS,
            start_time=_ms(cursor), end_time=_ms(page_end), closed_only=True,
        )
        frame = backtest.prepare_frame(bars)
        pages += 1
        if frame is None or frame.empty:
            empty_pages += 1
        else:
            frames.append(frame)
        cursor = page_end
    if not frames:
        return pd.DataFrame(), {"pages": pages, "empty_pages": empty_pages, "rows": 0}
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out[(out.index >= pd.Timestamp(start)) & (out.index < pd.Timestamp(end))]
    expected = int((end - start) / BAR)
    meta = {
        "pages": pages, "empty_pages": empty_pages, "rows": int(len(out)), "expected_rows": expected,
        "coverage": round(len(out) / expected, 4) if expected else None,
        "first": out.index.min().isoformat() if len(out) else None,
        "last": out.index.max().isoformat() if len(out) else None,
    }
    return out, meta


def fetch_funding(symbol: str, start: datetime, end: datetime) -> tuple[list[list[float]], str]:
    """Historical funding rates as [[ts_ms, rate], ...] for the replay window.

    Tries the exchange-native pair first, then the base asset (the managed
    funding endpoint is documented to accept base-asset symbols for some
    providers).  Returns an empty list when nothing usable comes back; the
    strategy then falls back to flattening before every settlement and reports
    the degradation instead of inventing a rate."""
    window_start = max(start, end - timedelta(days=89))
    for sym in (symbol, symbol.replace("USDT", "")):
        try:
            payload = data.crypto.futures.funding_rate(
                symbol=sym, exchange="bitget", interval="1h", limit=1000,
                start_time=_ms(window_start), end_time=_ms(end),
            )
            rows = data.to_records(payload)
        except Exception as exc:  # noqa: BLE001 - try the next symbol spelling
            rows = []
            last_error = str(exc)
        out: list[list[float]] = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            rate = r.get("funding_rate")
            ts = r.get("timestamp") or r.get("date") or r.get("time")
            if rate is None or ts is None:
                continue
            try:
                ts_ms = int(pd.Timestamp(ts).tz_localize("UTC").timestamp() * 1000) if pd.Timestamp(ts).tzinfo is None else int(pd.Timestamp(ts).timestamp() * 1000)
                out.append([ts_ms, float(rate)])
            except (TypeError, ValueError):
                continue
        if out:
            out.sort(key=lambda x: x[0])
            return out, f"ok:{sym}:{len(out)}"
    return [], "unavailable"


def _equity_curve_points(raw: dict[str, Any], starting_balance: float) -> tuple[list[dict[str, Any]], str]:
    """Return real equity points from the engine report; never forward-fill or fabricate."""
    reports = raw.get("reports") or {}
    curve = reports.get("equity_curve")
    points: list[dict[str, Any]] = []
    if isinstance(curve, list) and curve:
        for p in curve:
            if not isinstance(p, dict):
                continue
            ts = p.get("timestamp") or p.get("ts") or p.get("time")
            val = p.get("value") if p.get("value") is not None else p.get("equity", p.get("balance"))
            if ts is None or val is None:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            points.append({"timestamp": str(ts), "value": v, "nav": v / starting_balance if starting_balance else None})
        if points:
            return points, "engine_equity_curve"
    positions = reports.get("positions")
    if isinstance(positions, list) and positions:
        rows = []
        for p in positions:
            if not isinstance(p, dict):
                continue
            ts = p.get("ts_closed") or p.get("closed_time") or p.get("ts_event")
            pnl = p.get("realized_pnl")
            if ts is None or pnl is None:
                continue
            try:
                rows.append((str(ts), float(str(pnl).split()[0])))
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda r: r[0])
        equity = starting_balance
        for ts, pnl in rows:
            equity += pnl
            points.append({"timestamp": ts, "value": equity, "nav": equity / starting_balance if starting_balance else None})
        if points:
            return points, "positions_realized_pnl"
    return [], "unavailable"


def _max_drawdown_usdt(points: list[dict[str, Any]], starting_balance: float) -> float | None:
    if not points:
        return None
    peak = starting_balance
    worst = 0.0
    for p in points:
        v = float(p["value"])
        peak = max(peak, v)
        worst = max(worst, peak - v)
    return worst


def _write_csv(points: list[dict[str, Any]]) -> None:
    lines = ["timestamp,value,nav"]
    for p in points:
        lines.append(f"{p.get('timestamp', '')},{p.get('value', '')},{p.get('nav', '')}")
    (OUTPUT_DIR / "equity_curve.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(round_trips: int | None, profit_factor: float | None, dd_pct_of_budget: float | None) -> dict[str, Any]:
    crit = PASS_CRITERIA
    measured = {"round_trips": round_trips, "profit_factor": profit_factor, "max_drawdown_pct_of_budget": dd_pct_of_budget}
    if round_trips is None or round_trips < crit["min_round_trips"]:
        verdict, why = "PENDING", "fewer round-trips than the pre-registered minimum"
    elif profit_factor is None or dd_pct_of_budget is None:
        verdict, why = "PENDING", "profit factor or drawdown not measurable from this run"
    elif profit_factor >= crit["min_profit_factor"] and dd_pct_of_budget < crit["max_drawdown_pct_of_budget"]:
        verdict, why = "PASS", "all pre-registered criteria met"
    else:
        verdict, why = "FAIL", "pre-registered criteria not met"
    return {"version": PLAYBOOK_VERSION, "criteria": crit, "measured": measured, "verdict": verdict, "reason": why}


def run() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    params = PlaybookParams.from_config(cfg)
    spec = copy.deepcopy(dict(runtime.backtest_spec or {}))
    venue = str((spec.get("venue") or {}).get("name") or "BITGET")
    balances = (spec.get("venue") or {}).get("starting_balances") or []
    starting_balance = float((balances[0] or {}).get("amount", 0) or 0) if balances and isinstance(balances[0], dict) else 0.0

    now = datetime.now(UTC).replace(second=0, microsecond=0)
    end = now - timedelta(minutes=now.minute % 15)
    start = end - timedelta(days=params.backtest_days + params.warmup_days)
    replay_start = start + timedelta(days=params.warmup_days)

    ohlcv: dict[str, pd.DataFrame] = {}
    loaded: list[str] = []
    skipped: dict[str, str] = {}
    data_meta: dict[str, Any] = {}
    for symbol in params.trading_symbols:
        frame, meta = fetch_15m(symbol, start, end)
        data_meta[symbol] = meta
        if frame.empty or (meta.get("coverage") or 0) < 0.7:
            skipped[symbol] = f"insufficient bars (coverage={meta.get('coverage')})"
            continue
        key = f"{symbol}.{venue}"
        ohlcv[key] = frame[["open", "high", "low", "close", "volume"]]
        loaded.append(symbol)
        if len(loaded) >= params.max_backtest_symbols:
            for rest in params.trading_symbols[params.trading_symbols.index(symbol) + 1:]:
                skipped[rest] = f"beyond max_backtest_symbols={params.max_backtest_symbols}"
            break

    funding_history: dict[str, list[list[float]]] = {}
    funding_meta: dict[str, str] = {}
    if params.funding_direction_aware:
        for symbol in loaded:
            rows, status = fetch_funding(symbol, replay_start - timedelta(days=1), end)
            funding_meta[symbol] = status
            if rows:
                funding_history[symbol] = rows

    primary = params.trading_symbols[0] if params.trading_symbols else "BTCUSDT"
    if not ohlcv:
        runtime.emit_signal(action="watch", symbol=primary, confidence=0.0, metrics={"rows": 0},
                            meta={"reason": "no replayable bars for any symbol", "data": data_meta, "skipped": skipped})
        return

    instruments = spec.get("instruments")
    if isinstance(instruments, list):
        spec["instruments"] = [inst for inst in instruments if str(inst.get("id", "")) in ohlcv]
    strategy_cfg = dict((spec.get("strategy") or {}).get("config") or {})
    strategy_cfg["strategy_params"] = params.as_dict()
    strategy_cfg["instrument_ids"] = list(ohlcv.keys())
    strategy_cfg["bar_types"] = [f"{k}-15-MINUTE-LAST-EXTERNAL" for k in ohlcv.keys()]
    strategy_cfg["funding_history"] = funding_history
    strategy_cfg["trade_start"] = replay_start.isoformat()
    spec.setdefault("strategy", {})["config"] = strategy_cfg
    # Feed the warm-up bars too (indicators need ~3 days of 4H bars); the strategy
    # blocks entries before trade_start, so the evaluated window is unchanged.
    spec["execution"] = {"start": start.isoformat(), "end": end.isoformat()}

    result = backtest.run(ohlcv_data=ohlcv, spec=spec)
    chart_path = backtest.generate_chart(result)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = dict(result.raw or {})
    summary = result.summary or {}
    try:
        net_pnl = float(summary.get("net_pnl") or 0.0)
    except (TypeError, ValueError):
        net_pnl = 0.0

    points, curve_source = _equity_curve_points(raw, starting_balance)
    if points:
        _write_csv(points)
    reports = raw.get("reports")
    if isinstance(reports, dict):
        reports.pop("equity_curve", None)
    dd_usdt = _max_drawdown_usdt(points, starting_balance)
    dd_pct_of_budget = (dd_usdt / params.margin_budget * 100.0) if dd_usdt is not None and params.margin_budget > 0 else None

    replay_stats: dict[str, Any] = {}
    stats_path = OUTPUT_DIR / "replay_stats.json"
    if stats_path.exists():
        try:
            replay_stats = json.loads(stats_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            replay_stats = {}
    round_trips = replay_stats.get("round_trips")
    if round_trips is None:
        round_trips = result.position_count
    profit_factor = replay_stats.get("profit_factor")
    if profit_factor is None:
        profit_factor = _sanitize(result.profit_factor)

    raw["net_pnl"] = round(net_pnl, 6)
    raw["starting_balance"] = starting_balance
    raw["total_return_pct"] = round(net_pnl / params.margin_budget * 100.0, 6) if params.margin_budget else None
    raw["account_total_return_pct"] = round(net_pnl / starting_balance * 100.0, 6) if starting_balance else None
    raw["max_drawdown_pct"] = round(dd_pct_of_budget, 6) if dd_pct_of_budget is not None else _sanitize(result.max_drawdown_pct)
    raw["account_max_drawdown_pct"] = _sanitize(result.max_drawdown_pct)
    raw["metrics_basis"] = "strategy"
    (OUTPUT_DIR / "backtest_report.json").write_text(json.dumps(raw, default=str), encoding="utf-8")

    evaluation = evaluate(int(round_trips) if round_trips is not None else None,
                          float(profit_factor) if profit_factor is not None else None, dd_pct_of_budget)
    evaluation.update({"window": {"start": replay_start.isoformat(), "end": end.isoformat()},
                       "symbols_loaded": loaded, "symbols_skipped": skipped, "equity_curve_source": curve_source,
                       "exit_reasons": replay_stats.get("exit_reasons"), "gate_blocks": replay_stats.get("gate_blocks"),
                       "funding_data": funding_meta, "funding_kept_positions": replay_stats.get("funding_kept_positions"),
                       "funding_feature_degraded": sorted(s for s in loaded if s not in funding_history)})
    (OUTPUT_DIR / "evaluation.json").write_text(json.dumps(evaluation, indent=2, default=str), encoding="utf-8")

    metrics = {k: _sanitize(v) for k, v in {
        "total_return_pct": raw["total_return_pct"],
        "account_return_pct": raw["account_total_return_pct"],
        "net_pnl": net_pnl,
        "starting_balance": starting_balance,
        "margin_budget": params.margin_budget,
        "sharpe_ratio": result.sharpe_ratio if round_trips else None,
        "max_drawdown_pct": raw["max_drawdown_pct"],
        "account_max_drawdown_pct": raw["account_max_drawdown_pct"],
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "round_trips": round_trips,
        "profit_factor": profit_factor,
        "verdict": evaluation["verdict"],
        "symbols_requested": len(params.trading_symbols),
        "symbols_loaded": len(loaded),
        "rows": int(sum(len(f) for f in ohlcv.values())),
        "equity_points": len(points),
        "metrics_basis": "strategy",
    }.items()}
    runtime.emit_signal(
        action="watch",
        symbol=primary,
        confidence=_sanitize(result.win_rate) or 0.0,
        metrics=metrics,
        meta={"chart_path": chart_path, "evaluation": evaluation, "data": data_meta, "playbook_version": PLAYBOOK_VERSION,
              "funding_rule_mode": "direction_aware" if funding_history else "direction_agnostic_fallback",
              "funding_data": funding_meta, "spread_gate": "live_only"},
    )
