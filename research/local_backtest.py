#!/usr/bin/env python3
"""Offline replay of the Playbook's own strategy code. No API key, no orders.

Runs `playbooks/runeclaw-intraday-session-flow/src/strategy.py` (the same class
the Bitget sandbox replays) inside a local NautilusTrader BacktestEngine on
public 15m candles downloaded by research/fetch_data.py.

Cost model (same as backtest.yaml): maker 0.02 %, taker 0.06 %, limit entries,
reduce-only stop-market and limit exits, NETTING margin account, 10,000 USDT.

Usage:
  python3 research/local_backtest.py --label v05_is  --end 2026-11-09T17:15
  python3 research/local_backtest.py --label v05_oos --end 2026-08-11T17:15
  python3 research/local_backtest.py --label x --end ... --set min_r_pct=0.3 --set signal_b_target_r=1.5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "playbooks" / "runeclaw-intraday-session-flow"
DATA = Path(__file__).resolve().parent / "data"
OUT = Path(__file__).resolve().parent / "out"
sys.path.insert(0, str(PKG))

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig  # noqa: E402
from nautilus_trader.config import LoggingConfig  # noqa: E402
from nautilus_trader.model.currencies import USDT  # noqa: E402
from nautilus_trader.model.data import BarType  # noqa: E402
from nautilus_trader.model.enums import AccountType, OmsType  # noqa: E402
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue  # noqa: E402
from nautilus_trader.model.instruments import CryptoPerpetual  # noqa: E402
from nautilus_trader.model.objects import Currency, Money, Price, Quantity  # noqa: E402
from nautilus_trader.persistence.wranglers import BarDataWrangler  # noqa: E402

from src.params import PlaybookParams  # noqa: E402
from src.strategy import RuneclawSessionFlow, RuneclawSessionFlowConfig  # noqa: E402

UTC = timezone.utc
BAR = timedelta(minutes=15)


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def load_bars(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{symbol}_15m.csv")
    df.index = pd.to_datetime(df["time_ms"], unit="ms", utc=True)
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))]


def load_funding(symbol: str) -> list[list[float]]:
    path = DATA / f"{symbol}_funding.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    return [[int(t), float(r)] for t, r in zip(df["time_ms"], df["funding_rate"])]


def make_instrument(spec: dict, venue: Venue, fee_mult: float = 1.0) -> CryptoPerpetual:
    sym = spec["raw_symbol"]
    return CryptoPerpetual(
        instrument_id=InstrumentId(Symbol(sym), venue),
        raw_symbol=Symbol(sym),
        base_currency=Currency.from_str(spec["base_currency"]),
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=int(spec["price_precision"]),
        size_precision=int(spec["size_precision"]),
        price_increment=Price.from_str(str(spec["price_increment"])),
        size_increment=Quantity.from_str(str(spec["size_increment"])),
        ts_event=0,
        ts_init=0,
        maker_fee=Decimal(str(spec["maker_fee"])) * Decimal(str(fee_mult)),
        taker_fee=Decimal(str(spec["taker_fee"])) * Decimal(str(fee_mult)),
        min_quantity=Quantity.from_str(str(spec["lot_size"])),
    )


def run(label: str, end: datetime, overrides: dict, days: int, sandbox_like_start: bool, fee_mult: float = 1.0) -> dict:
    manifest = yaml.safe_load((PKG / "manifest.yaml").read_text(encoding="utf-8"))
    spec = yaml.safe_load((PKG / "backtest.yaml").read_text(encoding="utf-8"))
    cfg = dict(manifest["strategy_config"])
    cfg.update(overrides)
    cfg["backtest_end_utc"] = end.isoformat()
    params = PlaybookParams.from_config(cfg)

    start = end - timedelta(days=days + params.warmup_days)
    replay_start = start + timedelta(days=params.warmup_days)
    # The sandbox data path returned bars from ~20.75 h after `start`; mirror that so
    # indicator warm-up sees the same bars as the recorded sandbox runs.
    data_start = start + timedelta(hours=20, minutes=45) if sandbox_like_start else start

    out_dir = OUT / label
    out_dir.mkdir(parents=True, exist_ok=True)
    venue = Venue(spec["venue"]["name"])
    engine = BacktestEngine(config=BacktestEngineConfig(trader_id=TraderId("RESEARCH-001"), logging=LoggingConfig(log_level="ERROR")))
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=None,
        starting_balances=[Money(float(spec["venue"]["starting_balances"][0]["amount"]), USDT)],
    )
    ids, bar_types, funding, rows = [], [], {}, {}
    for inst_spec in spec["instruments"]:
        symbol = inst_spec["raw_symbol"]
        if symbol not in params.trading_symbols:
            continue
        df = load_bars(symbol, data_start, end)
        if df.empty:
            continue
        instrument = make_instrument(inst_spec, venue, fee_mult)
        engine.add_instrument(instrument)
        bar_type = BarType.from_str(inst_spec["bar_type"])
        engine.add_data(BarDataWrangler(bar_type, instrument).process(df))
        ids.append(str(instrument.id))
        bar_types.append(inst_spec["bar_type"])
        rows[symbol] = (len(df), df.index[0].isoformat(), df.index[-1].isoformat())
        if params.funding_direction_aware:
            f = load_funding(symbol)
            if f:
                funding[symbol] = f

    strategy = RuneclawSessionFlow(RuneclawSessionFlowConfig(
        order_id_tag="RC01",
        strategy_params=params.as_dict(),
        instrument_ids=tuple(ids),
        bar_types=tuple(bar_types),
        funding_history=funding,
        trade_start=replay_start.isoformat(),
    ))
    engine.add_strategy(strategy)
    cwd = os.getcwd()
    os.chdir(out_dir)           # the strategy writes output/replay_stats.json relative to cwd
    try:
        engine.run()
        fills = engine.trader.generate_order_fills_report()
        positions = engine.trader.generate_positions_report()
        account = engine.trader.generate_account_report(venue)
        engine.dispose()
    finally:
        os.chdir(cwd)

    stats = json.loads((out_dir / "output" / "replay_stats.json").read_text())
    journal = json.loads((out_dir / "output" / "trade_journal.json").read_text())
    starting = float(spec["venue"]["starting_balances"][0]["amount"])

    # Realised-balance drawdown (account total after each fill), as % of margin budget.
    dd_usdt, net = None, None
    if account is not None and len(account):
        total = account["total"].astype(float)
        peak = total.cummax().clip(lower=starting)
        dd_usdt = float((peak - total).max())
        net = float(total.iloc[-1] - starting)
    gp, gl = stats["gross_profit"], stats["gross_loss"]
    n = stats["round_trips"]
    risk = params.risk_usdt_per_trade
    result = {
        "label": label,
        "window": [replay_start.isoformat(), end.isoformat()],
        "overrides": overrides,
        "fee_mult": fee_mult,
        "round_trips": n,
        "profit_factor": (gp / gl) if gl > 0 else None,
        "max_drawdown_pct_of_budget": (dd_usdt / params.margin_budget * 100.0) if dd_usdt is not None else None,
        "net_pnl_usdt": net,
        "net_pnl_from_positions": gp - gl,
        "win_rate": (stats["wins"] / n) if n else None,
        "expectancy_nominal_r": ((gp - gl) / n / risk) if n else None,
        "exit_reasons": stats["exit_reasons"],
        "entries_placed": stats["entries_placed"],
        "entries_expired": stats["entries_expired"],
        "funding_kept_positions": stats.get("funding_kept_positions"),
        "fills": int(len(fills)) if fills is not None else None,
        "positions": int(len(positions)) if positions is not None else None,
        "bars": rows,
        "funding_rows": {k: len(v) for k, v in funding.items()},
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    if positions is not None and len(positions):
        positions.to_csv(out_dir / "positions.csv")
    (out_dir / "journal.json").write_text(json.dumps(journal, default=str))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--end", required=True, help="evaluation end, UTC, e.g. 2026-11-09T17:15")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--set", action="append", default=[], help="override strategy_config, e.g. --set time_stop_minutes=120")
    ap.add_argument("--full-warmup", action="store_true", help="use all warm-up bars instead of mirroring the sandbox data start")
    ap.add_argument("--fee-mult", type=float, default=1.0, help="multiply maker and taker fees (cost stress test)")
    args = ap.parse_args()
    overrides = {}
    for item in args.set:
        key, value = item.split("=", 1)
        overrides[key] = yaml.safe_load(value)
    result = run(args.label, _dt(args.end), overrides, args.days, not args.full_warmup, args.fee_mult)
    print(json.dumps({k: result[k] for k in ("label", "round_trips", "profit_factor", "max_drawdown_pct_of_budget", "net_pnl_usdt",
                                             "win_rate", "expectancy_nominal_r", "exit_reasons", "entries_placed", "entries_expired",
                                             "fills", "bars", "funding_rows")}, indent=1, default=str))


if __name__ == "__main__":
    main()
