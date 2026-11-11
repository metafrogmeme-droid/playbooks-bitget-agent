#!/usr/bin/env python3
"""Staged, pre-registered evaluation of Signal D (docs/.../RESEARCH_v0.11.md).

  python3 research/study_signal_d.py discovery            # three declared variants
  python3 research/study_signal_d.py validation --lookback L
  python3 research/study_signal_d.py final --lookback L
  python3 research/study_signal_d.py recent --lookback L

Run a later stage only if the previous one passed. Funding rule in fallback mode
(flatten before every settlement) on every window.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

VARIANTS = (1, 4, 12)
PERIODS = {
    "discovery": [("discovery", "2023-01-01T00:00", "2024-07-01T00:00")],
    "validation": [("validation", "2024-07-01T00:00", "2025-07-01T00:00")],
    "final": [("final", "2025-07-01T00:00", "2026-02-01T00:00")],
    "recent": [("recent-holdout", "2026-02-12T17:15", "2026-05-13T17:15"),
               ("recent-oos", "2026-05-13T17:15", "2026-08-11T17:15"),
               ("recent-is", "2026-08-11T17:15", "2026-11-09T17:15")],
}


def run(label: str, start: str, end: str, lookback: int, fee_mult: float = 1.0) -> dict:
    days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
    cmd = [sys.executable, str(HERE / "local_backtest.py"), "--label", label, "--end", end, "--days", str(days), "--full-warmup",
           "--fee-mult", str(fee_mult),
           "--set", "enable_signal_d=true", "--set", "enable_signal_b=false", "--set", "funding_direction_aware=false",
           "--set", f"signal_d_lookback_hours={lookback}"]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = json.loads((HERE / "out" / label / "result.json").read_text())
    df = analyze.trades(label)
    r["days"] = days
    r["rt_per_90d"] = r["round_trips"] / days * 90.0
    r["pf_before_fees"] = analyze.pf(df.gross) if len(df) else float("nan")
    r["fee_r"] = (df.fees_est.sum() / len(df) / df.risk_usdt.mean()) if len(df) else float("nan")
    r["median_stop_pct"] = float(df.r_pct.median()) if len(df) else float("nan")
    if len(df):
        q = df.groupby(df.entry_ts.dt.tz_localize(None).dt.to_period("Q")).pnl.sum()
        s = df.groupby("symbol").pnl.sum()
        r["quarters"] = {str(k): round(float(v), 1) for k, v in q.items()}
        r["symbols"] = {k: round(float(v), 1) for k, v in s.items()}
        r["trades_by_symbol"] = df.groupby("symbol").size().to_dict()
    else:
        r["quarters"], r["symbols"], r["trades_by_symbol"] = {}, {}, {}
    return r


def row(name: str, r: dict) -> str:
    pf = r["profit_factor"] or 0.0
    return (f"| {name} | {r['round_trips']} | {r['rt_per_90d']:.0f} | {pf:.2f} | {r['max_drawdown_pct_of_budget']:.1f} | {r['net_pnl_usdt']:+.1f} | "
            f"{100 * (r['win_rate'] or 0):.0f} % | {r['expectancy_nominal_r'] or 0:+.2f} | {r['pf_before_fees']:.2f} | {r['fee_r']:.2f} |")


HEAD = ("| Run | Round-trips | Per 90 days | Profit factor | Max DD (% budget) | Net USDT | Win rate | Expectancy (R) | PF before fees | Fees (R per trade) |\n"
        "|---|---|---|---|---|---|---|---|---|---|")


def discovery() -> None:
    (_, start, end), = PERIODS["discovery"]
    lines, detail = [HEAD], []
    for lb in VARIANTS:
        r = run(f"sigd_disc_L{lb}", start, end, lb)
        net = r["net_pnl_from_positions"]
        q_pos = sum(1 for v in r["quarters"].values() if v > 0)
        s_pos = sum(1 for v in r["symbols"].values() if v > 0)
        top_share = (max(r["quarters"].values()) / net) if net > 0 and r["quarters"] else float("nan")
        checks = {
            "PF after fees >= 1.4": (r["profit_factor"] or 0) >= 1.4,
            "profitable quarters >= 4 of 6": q_pos >= 4 and len(r["quarters"]) == 6,
            "profitable contracts >= 3 of 4": s_pos >= 3,
            "no quarter above half of net profit": net > 0 and top_share <= 0.5,
        }
        lines.append(row(f"L = {lb} h", r))
        detail.append({"lookback": lb, "qualifies": all(checks.values()), "checks": checks, "quarters": r["quarters"],
                       "symbols": r["symbols"], "trades_by_symbol": r["trades_by_symbol"], "exit_reasons": r["exit_reasons"],
                       "profitable_quarters": q_pos, "profitable_contracts": s_pos, "median_stop_pct": r["median_stop_pct"]})
    print("\n".join(lines))
    print(json.dumps(detail, indent=1))
    (HERE / "out" / "study_signal_d_discovery.json").write_text(json.dumps({"table": lines, "detail": detail}, indent=1))


def later(stage: str, lookback: int) -> None:
    lines = [HEAD]
    for name, start, end in PERIODS[stage]:
        r = run(f"sigd_{name}_L{lookback}", start, end, lookback)
        lines.append(row(name, r))
        print(name, r["exit_reasons"], r["quarters"], r["symbols"], file=sys.stderr)
        if stage == "validation":
            s = run(f"sigd_{name}_L{lookback}_fees150", start, end, lookback, fee_mult=1.5)
            lines.append(row(f"{name}, fees x1.5", s))
    print("\n".join(lines))
    (HERE / "out" / f"study_signal_d_{stage}.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("discovery", "validation", "final", "recent"))
    ap.add_argument("--lookback", type=int)
    a = ap.parse_args()
    discovery() if a.stage == "discovery" else later(a.stage, a.lookback)
