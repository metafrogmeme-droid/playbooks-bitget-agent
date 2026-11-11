#!/usr/bin/env python3
"""Pre-registered evaluation of Signal C (docs/.../RESEARCH_v0.10.md).

One run per window with the fixed specification, plus the unchanged default
(Signal B, v0.5 behaviour) on the same windows for reference.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
WINDOWS = (("in-sample", "is", "2026-11-09T17:15"), ("out-of-sample", "oos", "2026-08-11T17:15"), ("holdout", "hold", "2026-05-13T17:15"))
CONFIGS = (
    ("Default (Signal B, v0.5)", "default", []),
    ("Signal C only", "sigc", ["--set", "enable_signal_c=true", "--set", "enable_signal_b=false"]),
)


def main() -> None:
    import analyze  # local module; needs the run outputs

    lines = ["| Configuration | Window | Round-trips | Profit factor | Max DD (% budget) | Net USDT | Win rate | Expectancy (R) | PF before fees | Fees (R per trade) | Passes bar |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, key, extra in CONFIGS:
        for wname, tag, end in WINDOWS:
            label = f"{key}_{tag}"
            subprocess.run([sys.executable, str(HERE / "local_backtest.py"), "--label", label, "--end", end, *extra],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            r = json.loads((HERE / "out" / label / "result.json").read_text())
            df = analyze.trades(label)
            gross_pf = analyze.pf(df.gross) if len(df) else float("nan")
            fee_r = (df.fees_est.sum() / len(df) / df.risk_usdt.mean()) if len(df) else float("nan")
            pf = r["profit_factor"] or 0.0
            ok = r["round_trips"] >= 60 and pf >= 1.3 and r["max_drawdown_pct_of_budget"] < 6.0
            lines.append(f"| {name} | {wname} | {r['round_trips']} | {pf:.2f} | {r['max_drawdown_pct_of_budget']:.1f} | {r['net_pnl_usdt']:+.1f} | "
                         f"{100 * (r['win_rate'] or 0):.0f} % | {r['expectancy_nominal_r'] or 0:+.2f} | {gross_pf:.2f} | {fee_r:.2f} | {'yes' if ok else 'no'} |")
            print(label, r["exit_reasons"], "placed", r["entries_placed"], "expired", r["entries_expired"], file=sys.stderr)
    text = "\n".join(lines)
    (HERE / "out" / "study_signal_c.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
