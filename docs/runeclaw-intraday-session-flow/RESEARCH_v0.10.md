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

Pending — to be filled in after the three runs.
