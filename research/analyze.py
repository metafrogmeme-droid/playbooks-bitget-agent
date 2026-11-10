#!/usr/bin/env python3
"""Trade-level breakdown of a local replay (research/out/<label>/journal.json)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "out"
FEE_MAKER, FEE_TAKER = 0.0002, 0.0006


def trades(label: str) -> pd.DataFrame:
    rows = json.loads((OUT / label / "journal.json").read_text())
    fills = {r["signal_id"]: r for r in rows if r["event"] == "entry_filled"}
    out = []
    for r in rows:
        if r["event"] != "exit" or r["signal_id"] not in fills:
            continue
        f = fills[r["signal_id"]]
        m = re.search(r"realized_pnl_usdt=(-?[0-9.]+)", r.get("note", ""))
        entry, stop, qty = float(f["fill_price"]), float(f["stop"]), float(f["qty"])
        ts = pd.Timestamp(f["timestamp"])
        risk = abs(entry - stop) * qty
        notional = entry * qty
        taker_exit = r["exit_reason"] != "target_hit"
        fees = notional * (FEE_MAKER + (FEE_TAKER if taker_exit else FEE_MAKER))
        pnl = float(m.group(1)) if m else float("nan")
        out.append({
            "symbol": r["symbol"], "side": f["side"], "kind": r["signal_id"].split("-")[2],
            "session": "EU" if ts.hour < 12 else "US", "hour": ts.hour, "exit": r["exit_reason"],
            "r_pct": abs(entry - stop) / entry * 100.0, "risk_usdt": risk, "notional": notional,
            "pnl": pnl, "fees_est": fees, "gross": pnl + fees, "r_mult": pnl / risk if risk else float("nan"),
            "held_min": (pd.Timestamp(r["timestamp"]) - ts).total_seconds() / 60.0, "entry_ts": ts,
        })
    return pd.DataFrame(out)


def pf(s: pd.Series) -> float:
    gp, gl = s[s > 0].sum(), -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def summary(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by, observed=True)
    return pd.DataFrame({
        "n": g.size(), "net": g["pnl"].sum().round(1), "pf_net": g["pnl"].apply(pf).round(2),
        "gross": g["gross"].sum().round(1), "pf_gross": g["gross"].apply(pf).round(2), "fees": g["fees_est"].sum().round(1),
        "win%": (g["pnl"].apply(lambda s: (s > 0).mean()) * 100).round(0), "avg_r_pct": g["r_pct"].mean().round(3),
        "risk_avg": g["risk_usdt"].mean().round(2),
    })


if __name__ == "__main__":
    label = sys.argv[1]
    df = trades(label)
    pd.set_option("display.width", 200)
    print(f"== {label}: n={len(df)} net={df.pnl.sum():.1f} PF_net={pf(df.pnl):.3f} | gross={df.gross.sum():.1f} PF_gross={pf(df.gross):.3f} | fees={df.fees_est.sum():.1f}"
          f" | avg risk {df.risk_usdt.mean():.2f} USDT | median r_pct {df.r_pct.median():.3f}%")
    df["r_bucket"] = pd.cut(df.r_pct, [0, 0.1, 0.15, 0.2, 0.3, 0.5, 5], labels=["<0.10", "0.10-0.15", "0.15-0.20", "0.20-0.30", "0.30-0.50", ">0.50"])
    for by in sys.argv[2:] or ["r_bucket", "symbol", "session", "side", "exit"]:
        print(f"-- by {by}"); print(summary(df, by).to_string())
