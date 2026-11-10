#!/usr/bin/env python3
"""Pre-registered study: cost-aware minimum stop distance for Signal B.

Thresholds were fixed from fee arithmetic BEFORE any run. Worst-case round-trip fee
is 0.08 % of notional (maker 0.02 % in, taker 0.06 % out), so the share of planned
risk R consumed by fees is  phi = 0.08 % / r_pct.  Tested levels:

    r_min = 0     (baseline, v0.5 behaviour)
    r_min = 0.20  (fees at most 40 % of R)
    r_min = 0.32  (fees at most 25 % of R)
    r_min = 0.50  (fees at most 16 % of R)

Windows: in-sample, the same out-of-sample split as the sandbox checks, and an
earlier holdout that no earlier version was evaluated on.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOWS = (("in-sample", "is", "2026-11-09T17:15"), ("out-of-sample", "oos", "2026-08-11T17:15"), ("holdout", "hold", "2026-05-13T17:15"))
LEVELS = (0.0, 0.20, 0.32, 0.50)


def main() -> None:
    table = {}
    for _, tag, end in WINDOWS:
        for level in LEVELS:
            label = f"minr_{str(level).replace('.', 'p')}_{tag}"
            subprocess.run([sys.executable, str(HERE / "local_backtest.py"), "--label", label, "--end", end,
                            "--set", f"signal_b_min_r_pct={level}"], check=True, stdout=subprocess.DEVNULL)
            table[(tag, level)] = json.loads((HERE / "out" / label / "result.json").read_text())
    lines = ["| r_min (% of price) | Window | Round-trips | Profit factor | Max DD (% budget) | Net USDT | Win rate | Expectancy (R) |",
             "|---|---|---|---|---|---|---|---|"]
    for level in LEVELS:
        for name, tag, _ in WINDOWS:
            r = table[(tag, level)]
            lines.append(f"| {level:.2f} | {name} | {r['round_trips']} | {r['profit_factor']:.2f} | {r['max_drawdown_pct_of_budget']:.1f} | "
                         f"{r['net_pnl_usdt']:+.1f} | {100 * r['win_rate']:.0f} % | {r['expectancy_nominal_r']:+.2f} |")
    text = "\n".join(lines)
    (HERE / "out" / "study_min_r.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
