# Out-of-sample check — v0.5.0 parameters (2026-11-10)

No strategy change and no tuning. This is the v0.5.0 package exactly as merged at
commit `3ec6949` (package files identical to the ones behind the in-sample run),
replayed on the 90 days immediately before the original evaluation window.

## Setup

| | In-sample (original) | Out-of-sample (this check) |
|---|---|---|
| Package | commit `2a853e6` (= `3ec6949` for package files) | commit `3ec6949` |
| Only difference | `backtest_end_utc: 2026-11-09T17:15Z` | `backtest_end_utc: 2026-08-11T17:15Z` |
| Evaluated window (UTC) | 2026-08-11 17:15 → 2026-11-09 17:15 | 2026-05-13 17:15 → 2026-08-11 17:15 |
| Run | `pbrun-77fb5c12d8f8` | `pbrun-d8b8abbb3a69` |
| Symbols | BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT | same |
| Bars | 8,869 per symbol (97 % coverage) | 8,869 per symbol (97 % coverage) |
| Mode | sandbox backtest | sandbox backtest: no live orders, no trading permissions, no paid data |

Parameters in both runs: Signal A off, Signal B with 2.5× volume and 2R target,
180-minute time stop, 0.5 % risk per trade on a 1,000 USDT budget.

## Results against the pre-registered bar

| Metric | In-sample v0.5 | Out-of-sample v0.5 | Bar |
|---|---|---|---|
| Round-trips | 109 | 110 | ≥ 60 |
| Profit factor (per position, pre-registered) | 1.07 | **0.59** | ≥ 1.3 |
| Max drawdown (% of margin budget) | 5.7 % | **21.5 %** | < 6 % |
| Win rate | 51.4 % | 47.3 % | |
| Expectancy per trade (nominal R) | +0.04 R | **-0.30 R** | |
| Net P&L (1,000 USDT budget) | +21.8 USDT | −167.2 USDT | |
| Verdict | FAIL (PF) | **FAIL (PF and DD)** | |

Exit mix:

| Exit reason | In-sample | Out-of-sample |
|---|---|---|
| Stop hit | 51 | 53 |
| Target hit | 36 | 20 |
| Funding window, position pays | 13 | 0 |
| Funding window, rate unknown (forced flatten) | 0 | 34 |
| Time stop | 9 | 2 |
| Daily loss cap | 0 | 1 |
| Kept through funding (received funding) | 9 | 0 |

Definitions:

* **Profit factor** is gross profit ÷ gross loss per closed position, the
  pre-registered definition. The platform's own fill-based figure for the
  out-of-sample run is 1.09; it is not the pre-registered measure.
* **Expectancy in nominal R** is net P&L ÷ round-trips ÷ 5 USDT, where 5 USDT is the
  planned risk per trade (0.5 % of budget). The package does not log realised
  risk per trade, and position size is reduced when the margin cap binds, so
  true R-multiples are somewhat larger in magnitude than these. Both columns
  use the same formula.

## Known defect in this comparison: funding data

The managed funding-rate endpoint returned only the most recent ~90 days
(542 rows per symbol starting 2026-08-12) and ignored the requested earlier
range. The out-of-sample window therefore had **no funding rates**, and the
direction-aware funding rule fell back to its documented conservative mode:
flatten before every 00/08/16 UTC settlement. That produced the 34
"rate unknown" exits (31 % of trades) where the in-sample run flattened 13 and
kept 9.

Two consequences:

1. The two columns do not apply an identical funding rule, so this is not a
   perfectly like-for-like replication.
2. The package reported `funding_feature_degraded: []` because rows existed,
   just for the wrong period. The degradation check should compare the
   returned date range with the replay window. Not changed here (results-only PR).

Size of the effect, from existing evidence: with Signal A on, moving from
flatten-always (v0.2) to direction-aware (v0.3.1) on the in-sample window
changed profit factor by about 0.05. That is far smaller than the gap between
1.07 and 0.59. The exits that are unaffected by funding point the same way:
targets fell from 36 to 20 while stops stayed at 51–53.

## Reading

* The in-sample result (roughly break-even, drawdown just under the limit) did
  **not** hold on the preceding 90 days. Profit factor fell to 0.59 and
  drawdown was 21.5 %, more than three times the limit.
* The trade count is almost identical (110 vs 109), so the signal fires at the
  same rate; what changed is follow-through after entry.
* The funding defect makes the out-of-sample number somewhat worse than a
  like-for-like run would be, but on the evidence above it does not explain
  the failure.
* Together with v0.4–v0.6 clustering at PF 1.02–1.07 in-sample, this indicates
  Signal B as specified has no demonstrated edge; the in-sample window was the
  favourable one of the two.

## Status

FAIL. No further version has been started. The next step is the owner's choice.
