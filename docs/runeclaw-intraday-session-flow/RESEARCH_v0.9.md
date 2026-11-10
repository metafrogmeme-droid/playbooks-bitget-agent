# v0.9 research — can the profit factor be fixed without overfitting? (2026-11-10)

Offline backtest research only. No API key, no paper or live orders, no paid data.
Result in one line: **a cost-aware fix passes the bar in-sample and fails on both
windows it was not tuned on, so it is not adopted; the default stays v0.5 behaviour.**

## Method

* **Local replay, no key.** `research/local_backtest.py` runs the Playbook's own
  strategy class (`src/strategy.py`) in a local NautilusTrader 1.231.0 engine on public
  Bitget 15m candles (`research/fetch_data.py`, unauthenticated endpoints).
* **Same cost model** as `backtest.yaml`: maker 0.02 %, taker 0.06 %, limit entries,
  reduce-only stop-market and limit exits, 10,000 USDT margin account, 0.5 % risk per
  trade on a 1,000 USDT budget.
* **Three windows** of 90 days each, four symbols (BTC, ETH, SOL, XRP):
  in-sample 2026-08-11 → 2026-11-09; out-of-sample 2026-05-13 → 2026-08-11 (the same
  split as the sandbox checks); holdout 2026-02-12 → 2026-05-13, which no earlier
  version was evaluated on.
* **Bar:** ≥ 60 round-trips, profit factor ≥ 1.3, max drawdown < 6 % of budget.

## Calibration of the local replay against recorded sandbox runs

| Configuration, window | Sandbox: RTs / PF / DD | Local: RTs / PF / DD |
|---|---|---|
| v0.5 midpoint, in-sample | 109 / 1.07 / 5.7 % | 107 / 1.09 / 6.5 % |
| v0.8 close entry, in-sample | 159 / 1.01 / 10.4 % | 158 / 1.00 / 10.7 % |
| v0.5 midpoint, out-of-sample | 110 / 0.59 / 21.5 % | 110 / 0.79 / 12.1 % |

In-sample agreement is close. Out-of-sample the trade count and exit mix agree
(stops 53 vs 51, targets 20 vs 23) but the local profit factor is higher. Known
differences: the sandbox data path delivered 8,869 bars per symbol where the public
feed has 9,037 (168 bars missing inside each window), and the local drawdown is
measured on the realised balance after each fill while the sandbox used its engine
equity curve. Both replays fail the bar on that window. All comparisons below are
local-to-local.

## Diagnosis: fees consume the edge

| Window | Round-trips | Before fees: PF | Fees paid | After fees: PF |
|---|---|---|---|---|
| In-sample | 107 | 1.57 | 115 USDT (0.23 R per trade) | 1.09 |
| Out-of-sample | 110 | 1.14 | 115 USDT (0.22 R per trade) | 0.79 |
| Holdout | 145 | 1.27 | 137 USDT (0.20 R per trade) | 0.89 |

The median stop is only 0.33–0.40 % of price. Position size is risk ÷ stop distance,
so a tight stop means a large notional, and fees of 0.04–0.08 % of notional cost
about a fifth of the planned risk on every trade.

Just as important: **before fees the profit factor is already below 1.3 on both
windows outside the in-sample period (1.14 and 1.27).** No reduction in fees can lift
this strategy over the bar there.

## Pre-registered test: cost-aware minimum stop distance

One change: skip a Signal B entry when its stop distance is below `r_min` percent of
the entry price (`signal_b_min_r_pct`). The levels were fixed from fee arithmetic
before any run: worst-case round-trip fees are 0.08 % of notional, so the share of
risk they consume is 0.08 % ÷ stop distance. `r_min` 0.20 / 0.32 / 0.50 cap that
share at 40 % / 25 % / 16 %.

| r_min (% of price) | Window | Round-trips | Profit factor | Max DD (% budget) | Net USDT | Win rate | Expectancy (R) |
|---|---|---|---|---|---|---|---|
| 0.00 | in-sample | 107 | 1.09 | 6.5 | +27.7 | 46 % | +0.05 |
| 0.00 | out-of-sample | 110 | 0.79 | 12.1 | -75.4 | 45 % | -0.14 |
| 0.00 | holdout | 145 | 0.89 | 15.5 | -47.1 | 45 % | -0.06 |
| 0.20 | in-sample | 87 | 1.35 | 4.4 | +80.6 | 49 % | +0.19 |
| 0.20 | out-of-sample | 97 | 0.74 | 12.0 | -84.5 | 45 % | -0.17 |
| 0.20 | holdout | 137 | 0.90 | 14.4 | -46.3 | 45 % | -0.06 |
| 0.32 | in-sample | 71 | 1.40 | 5.6 | +68.6 | 52 % | +0.19 |
| 0.32 | out-of-sample | 72 | 0.68 | 7.3 | -73.0 | 46 % | -0.20 |
| 0.32 | holdout | 116 | 0.87 | 12.9 | -44.9 | 47 % | -0.08 |
| 0.50 | in-sample | 41 | 1.56 | 3.4 | +53.6 | 54 % | +0.26 |
| 0.50 | out-of-sample | 34 | 1.28 | 1.8 | +18.4 | 56 % | +0.11 |
| 0.50 | holdout | 57 | 0.71 | 7.2 | -42.5 | 42 % | -0.15 |

Reading:

* **In-sample the filter clears the bar** at 0.20 and 0.32 (PF 1.35 and 1.40,
  drawdown 4.4 % and 5.6 %, more than 60 round-trips).
* **Out-of-sample it gets worse** at those levels (0.74 and 0.68 against 0.79), and
  **on the holdout nothing changes** (0.90 and 0.87 against 0.89).
* At 0.50 the out-of-sample figure looks better (1.28) but rests on 34 trades, under
  the 60 minimum, and the holdout falls to 0.71.
* No level passes on any window other than in-sample. Judged on in-sample alone this
  would have shipped as a fix; the other two windows show it is fitted to that period.

Other in-sample asymmetries were seen and deliberately **not** acted on, because they
are the kind of pattern that does not survive a change of market regime: US session
better than EU, shorts better than longs, XRP worse than the other three.

## Conclusion

* The profit factor cannot be fixed by cost reduction: before-fee profit factor is
  under 1.3 on both windows outside the in-sample period.
* `signal_b_min_r_pct` is kept as an opt-in research option, **default 0 (off)**. The
  default configuration is unchanged and replays identically to v0.5 (verified: the
  `r_min = 0` runs equal the baseline runs on all three windows).
* Nothing is cleared for paper or live trading.
* Further threshold work on Signal B is not recommended. A credible next step would
  be a different signal hypothesis evaluated on these same three windows from the
  start, with the holdout touched once.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install nautilus_trader==1.231.0 pandas pyyaml
.venv/bin/python research/fetch_data.py --start 2026-02-07T00:00 --end 2026-11-09T17:15
.venv/bin/python research/study_min_r.py          # prints the table above
.venv/bin/python research/analyze.py minr_0p0_is  # fee and trade breakdown
```

Public funding history only reaches back about 90 days, so the out-of-sample and
holdout windows run with the flatten-before-every-settlement fallback, as the
sandbox out-of-sample runs did.
