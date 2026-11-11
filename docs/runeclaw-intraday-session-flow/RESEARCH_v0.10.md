# v0.10 research — Signal C, session opening-range breakout (2026-11-10)

Offline backtest research only: public data, local replay, no API key, no paper or
live orders. Signal C is off by default; the default configuration is unchanged.

## Pre-registration (written and committed before any Signal C backtest was run)

**Why a different signal.** v0.9 showed the volume-spike breakout (Signal B) pays
about 0.2 R in fees per trade because its stops are tight (median 0.33–0.40 % of
price), and that its before-fee profit factor is under 1.3 outside the in-sample
window. Tuning it further is curve-fitting. Signal C is a different mechanism with a
structurally wider stop.

**Specification (single, fixed; no parameter search).**

| Element | Rule |
|---|---|
| Opening range | High and low of the first 60 minutes of each session window (07:00–08:00 and 13:30–14:30 UTC), from 15m bars. Unused if any range bar is missing. |
| Trigger | The first 15m bar of that session that closes above the range high (long) or below the range low (short). One attempt per symbol per session; later bars do not re-trigger. |
| Bias gate | The completed-1H EMA slope must not point against the breakout (same direction or flat). |
| Entry | Limit at the trigger bar's close, 30-minute expiry. |
| Stop | Opposite side of the opening range. |
| Target | 1 R beyond the entry (R = entry to stop). No trailing. |
| Everything else | Unchanged playbook rules: 4H ATR regime filter, session windows, funding rule, 180-minute time stop, flat by 23:45 UTC, 0.5 % risk per trade on a 1,000 USDT budget, max 2 concurrent, max 3 trades per symbol per day, 1.5 % daily loss cap, 24h volume gate. |
| Configuration under test | `enable_signal_c: true`, `enable_signal_b: false`, `enable_signal_a: false`. |

All four numbers (60 minutes, 1 R, 30 minutes, first break only) are conventional
choices fixed here; none was selected by looking at results.

**Evaluation.**

* Local replay (`research/local_backtest.py`), same cost model as before: maker
  0.02 %, taker 0.06 %, limit entry, reduce-only stop-market and limit exits.
* Three 90-day windows, BTC / ETH / SOL / XRP, one run each, all from the start:
  in-sample 2026-08-11 → 2026-11-09, out-of-sample 2026-05-13 → 2026-08-11,
  holdout 2026-02-12 → 2026-05-13. For a new signal none of the three is a tuning
  window; the labels are kept only for continuity.
* **Pass bar on every window:** ≥ 60 round-trips, profit factor ≥ 1.3, max drawdown
  < 6 % of budget.
* **Decision rule:** Signal C becomes eligible to be a default only if it passes on
  all three windows. Otherwise it stays an off-by-default research option and no
  parameter is adjusted after seeing the results.

**Known limits, stated in advance.** Public funding history reaches back about 90
days, so the two older windows flatten before every funding settlement. The 16:00
UTC settlement falls inside the US session, which will cut many US trades short.
Three windows of 90 days are a small sample.

## Results

The specification above was committed as `ff83307` before these runs. Each
configuration was run once per window; nothing was adjusted afterwards.

| Configuration | Window | Round-trips | Profit factor | Max DD (% budget) | Net USDT | Win rate | Expectancy (R) | PF before fees | Fees (R per trade) | Passes bar |
|---|---|---|---|---|---|---|---|---|---|---|
| Default (Signal B, v0.5) | in-sample | 107 | 1.09 | 6.5 | +27.7 | 46 % | +0.05 | 1.57 | 0.23 | no |
| Default (Signal B, v0.5) | out-of-sample | 110 | 0.79 | 12.1 | -75.4 | 45 % | -0.14 | 1.14 | 0.22 | no |
| Default (Signal B, v0.5) | holdout | 145 | 0.89 | 15.5 | -47.1 | 45 % | -0.06 | 1.27 | 0.20 | no |
| Signal C only | in-sample | 259 | 0.70 | 17.0 | -149.7 | 45 % | -0.11 | 1.02 | 0.12 | no |
| Signal C only | out-of-sample | 231 | 0.65 | 18.4 | -148.7 | 42 % | -0.13 | 0.95 | 0.12 | no |
| Signal C only | holdout | 259 | 0.83 | 9.6 | -76.3 | 46 % | -0.06 | 1.13 | 0.10 | no |

"PF before fees" adds the estimated fees back to each trade. "Fees (R per trade)"
is average fees divided by average planned risk.

**Verdict: Signal C fails the bar on all three windows. It stays off by default and
no parameter is changed.**

Reading:

* **The cost problem was solved, the edge was not there.** The stop is wider (median
  0.75 % of price in-sample against 0.33 % for Signal B), so fees fall from about
  0.2 R to about 0.1 R per trade, as intended. But before fees the profit factor is
  about 1.0 on all three windows (1.02, 0.95, 1.13): the breakouts have no directional
  edge to protect.
* **Most trades never reach either exit.** In-sample only 115 of 259 trades end at the
  target (71) or the stop (44). 96 are closed by the 180-minute time stop and 47 by
  the funding rule, and both groups lose on balance. A full opening range is a long
  way for price to travel inside a session.
* **Consistent across windows.** Unlike Signal B, there is no window where Signal C
  looks good, so this is not a case of an unlucky test window.
* It is worse than the unchanged default on the in-sample and out-of-sample windows
  and similar on the holdout. The default also fails all three.

Checks made on the runs:

* The default configuration replays identically to the runs made before Signal C
  existed, on all three windows (same trades, fills, profit factor and drawdown).
* All 260 in-sample Signal C entries were re-derived from the raw bars and match the
  specification: full four-bar range, first close outside it, stop at the opposite
  side, target 1 R from the entry.

## Conclusion

* Signal C is not adopted. `enable_signal_c` stays `false`; the default configuration
  is the v0.5 behaviour.
* Two independent breakout mechanisms (volume-spike bar and session opening range)
  now show no usable edge after costs on this universe and timeframe over nine
  months. Nothing is cleared for paper or live trading.
* Per the pre-registration, no variant of Signal C (different range length, target or
  stop) is tested here; doing so after seeing these results would be tuning.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install nautilus_trader==1.231.0 pandas pyyaml
.venv/bin/python research/fetch_data.py --start 2026-02-07T00:00 --end 2026-11-09T17:15
.venv/bin/python research/study_signal_c.py     # prints the table above
```
