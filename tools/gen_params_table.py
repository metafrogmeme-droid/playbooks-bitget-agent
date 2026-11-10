#!/usr/bin/env python3
"""Generate docs/runeclaw-intraday-session-flow/PARAMETERS.md from src/params.py.

Also fails when manifest.strategy_config defaults drift from PlaybookParams.
Usage: python3 tools/gen_params_table.py [--check]
"""
from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "playbooks" / "runeclaw-intraday-session-flow"
DOC = ROOT / "docs" / "runeclaw-intraday-session-flow" / "PARAMETERS.md"
sys.path.insert(0, str(PKG))
from src.params import PlaybookParams  # noqa: E402

# name -> (allowed range / options, unit, tunable by subscriber?, description)
SPEC: dict[str, tuple[str, str, bool, str]] = {
    "trading_symbols": ("subset of {BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, SOXLUSDT, SNDKUSDT, KORUUSDT}, 1–7 items", "-", True, "Universe: contracts passing the liquidity scan; crypto on by default, RWA opt-in"),
    "margin_budget": ("100 – 100000", "USDT", True, "Risk denominator and platform return basis; margin cap = budget × leverage"),
    "leverage": ("1 – 10", "x", True, "Only changes margin usage; risk per trade is fixed by risk_pct_per_trade"),
    "risk_pct_per_trade": ("0.1 – 1.0", "% of budget", True, "Loss between entry and initial stop per trade"),
    "min_24h_notional_usdt": ("50e6 – 1e9", "USDT", False, "Exclude symbol when 24h quote volume is below this (live: ticker; replay: 96-bar notional)"),
    "max_spread_bps": ("1 – 10", "bps", False, "Exclude symbol when (ask-bid)/mid exceeds this (live only)"),
    "regime_atr_period": ("7 – 28", "4H bars", False, "Wilder ATR period for the regime filter"),
    "regime_atr_pct_min": ("0.3 – 1.0", "%", False, "Below = chop, no trades"),
    "regime_atr_pct_max": ("2.0 – 5.0", "%", False, "Above = event risk, no trades"),
    "bias_ema_period": ("10 – 50", "1H bars", False, "EMA whose slope defines the 1H bias"),
    "bias_flat_slope_pct": ("0.01 – 0.20", "%", False, "abs(slope) below this counts as flat"),
    "session_windows": ("list of HH:MM-HH:MM UTC, 1–3 windows", "UTC", False, "Entry windows; start inclusive, end exclusive"),
    "enable_signal_a": ("true / false", "-", False, "VWAP reversion on/off (off in v0.4 to isolate Signal B)"),
    "vwap_anchor": ("utc_day", "-", False, "Session VWAP reset point (only utc_day implemented in v0.1)"),
    "vwap_trigger_sigma": ("1.0 – 3.0", "σ", False, "Distance from VWAP that arms Signal A"),
    "vwap_limit_sigma": ("0.5 – trigger", "σ", False, "Entry limit band (worst acceptable entry)"),
    "vwap_stop_sigma": ("trigger – 3.5", "σ", False, "Initial stop band for Signal A"),
    "rsi_period": ("7 – 21", "15m bars", False, "RSI period"),
    "rsi_overbought": ("60 – 85", "RSI", False, "Short-side exhaustion threshold"),
    "rsi_oversold": ("15 – 40", "RSI", False, "Long-side exhaustion threshold"),
    "signal_a_expiry_minutes": ("15 – 90", "min", False, "Resting time of a Signal A limit order"),
    "enable_signal_b": ("true / false", "-", False, "Volume-spike breakout on/off"),
    "volume_spike_mult": ("1.5 – 5.0", "× median", False, "Bar volume vs median of previous bars"),
    "volume_median_bars": ("10 – 50", "15m bars", False, "Median window (current bar excluded)"),
    "breakout_lookback_bars": ("10 – 50", "15m bars", False, "Prior high/low window (current bar excluded)"),
    "signal_b_expiry_minutes": ("15 – 60", "min", False, "Resting time of a Signal B limit order"),
    "signal_b_target_r": ("1.0 – 4.0", "R", False, "Breakout target as multiple of initial risk"),
    "signal_b_trail_r": ("0.5 – 2.0", "R", False, "Trail distance once trade is that many R in profit"),
    "funding_hours_utc": ("subset of {0, 8, 16}", "hour UTC", False, "Bitget 8-hour funding settlement times"),
    "funding_flatten_lead_minutes": ("5 – 30", "min", False, "Flatten lead before funding; effective lead = max(lead, 15) at 15m cadence"),
    "funding_direction_aware": ("true / false", "-", False, "Live: flatten only when the position pays funding (replay: always flatten)"),
    "max_concurrent_positions": ("1 – 3", "positions", True, "Open positions + resting entries across all symbols"),
    "max_trades_per_day_symbol": ("1 – 6", "trades", False, "Filled entries per symbol per UTC day"),
    "daily_loss_cap_pct": ("0.5 – 3.0", "% of budget", True, "Realised loss that halts trading until next UTC day"),
    "daily_cap_flatten": ("true / false", "-", False, "Also flatten open positions when the cap is hit"),
    "time_stop_minutes": ("30 – 240", "min", False, "Close trades that have not reached target in time"),
    "eod_flatten_time": ("23:00 – 23:45", "HH:MM UTC", False, "Hard end-of-day flatten time"),
    "reconcile_interval_minutes": ("5 – 15", "min", False, "Requested reconciliation cadence (scheduler floor is 15 min)"),
    "halt_on_reconcile_mismatch": ("true / false", "-", False, "Block new entries while a position/fill mismatch is flagged"),
    "backtest_days": ("30 – 180", "days", True, "Replay window length"),
    "warmup_days": ("3 – 10", "days", False, "Extra history fetched for indicator warm-up (excluded from the replay window)"),
    "max_backtest_symbols": ("1 – 7", "symbols", True, "Symbols replayed per sandbox run (180 s budget); the rest are reported as skipped"),
    "backtest_end_utc": ("ISO-8601 UTC or empty (= now)", "timestamp", False, "Pinned evaluation end so versions replay identical bars; move only with a new baseline"),
}


def _fmt(value) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, float) and value.is_integer() and abs(value) >= 1000:
        return f"{int(value):,}"
    return str(value)


def main(check_only: bool) -> int:
    defaults = PlaybookParams()
    manifest = yaml.safe_load((PKG / "manifest.yaml").read_text(encoding="utf-8"))
    cfg = manifest.get("strategy_config", {})
    errors = []
    for f in fields(PlaybookParams):
        if f.name not in SPEC:
            errors.append(f"params.py field {f.name} missing from SPEC table")
        if f.name not in cfg:
            errors.append(f"manifest.strategy_config missing {f.name}")
            continue
        want = getattr(defaults, f.name)
        got = cfg[f.name]
        if isinstance(want, tuple):
            ok = list(want) == [type(want[0])(x) if want else x for x in got]
        elif isinstance(want, bool):
            ok = bool(got) == want
        elif isinstance(want, float):
            ok = abs(float(got) - want) < 1e-12
        else:
            ok = type(want)(got) == want
        if not ok:
            errors.append(f"default mismatch {f.name}: params.py={want!r} manifest={got!r}")
    for name in cfg:
        if name not in {f.name for f in fields(PlaybookParams)}:
            errors.append(f"manifest.strategy_config has unknown field {name}")
    if errors:
        print("\n".join(errors))
        return 1

    lines = [
        "# Parameter table — RUNECLAW Intraday Session Flow v0.5",
        "",
        "Generated from `src/params.py` by `tools/gen_params_table.py`; defaults are",
        "identical in `manifest.yaml -> strategy_config`. *Tunable* marks the fields a",
        "subscriber may override (`user_config_schema`); every other field changes only",
        "through a new version (one variable per version).",
        "",
        "| Parameter | Default | Allowed range | Unit | Tunable | Meaning |",
        "|---|---|---|---|---|---|",
    ]
    for f in fields(PlaybookParams):
        rng, unit, tunable, desc = SPEC[f.name]
        lines.append(f"| `{f.name}` | {_fmt(getattr(defaults, f.name))} | {rng} | {unit} | {'yes' if tunable else 'no'} | {desc} |")
    lines += [
        "",
        "## Derived values (not configurable)",
        "",
        "| Name | Formula | v0.1 value |",
        "|---|---|---|",
        f"| risk per trade | margin_budget × risk_pct_per_trade / 100 | {defaults.risk_usdt_per_trade:g} USDT |",
        f"| daily loss cap | margin_budget × daily_loss_cap_pct / 100 | {defaults.daily_loss_cap_usdt:g} USDT |",
        f"| max notional per position | margin_budget × leverage | {defaults.margin_budget * defaults.leverage:g} USDT |",
        f"| effective funding lead | max(funding_flatten_lead_minutes, 15) | {defaults.effective_funding_lead_minutes} min |",
        "| decision cadence | 15m bars / `*/15 * * * *` schedule | 15 min |",
        "",
        "## Pre-registered pass criteria (fixed for v0.x)",
        "",
        "| Criterion | Threshold | Verdict if not met |",
        "|---|---|---|",
        "| Round-trips | ≥ 60 | PENDING |",
        "| Profit factor | ≥ 1.3 | FAIL |",
        "| Max drawdown (% of margin budget) | < 6 % | FAIL |",
        "",
    ]
    text = "\n".join(lines)
    if check_only:
        if not DOC.exists() or DOC.read_text(encoding="utf-8") != text:
            print("PARAMETERS.md is stale; run tools/gen_params_table.py")
            return 1
        print("PARAMETERS.md up to date")
        return 0
    DOC.write_text(text, encoding="utf-8")
    print(f"wrote {DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
