# Changelog — RUNECLAW Intraday Session Flow

## 2026-11-10 — premise review (no code or parameter change, no new signal)
Added:       PREMISE_REVIEW.md — what the evidence shows, the cost hurdle, candidate
             premises and who would pay for each, the data split for any future test, and
             kill criteria fixed in advance. No breakout variants will be tried.
Measured:    the funding fallback used on older windows lowers Signal B's in-sample PF
             from 1.09 to 0.94 and leaves Signal C unchanged (0.70 vs 0.71).
Status:      waiting for the owner's decision; default configuration unchanged.

## v0.10.0 — 2026-11-10 — offline research: Signal C, session opening-range breakout
Change:      New signal, off by default (enable_signal_c: false). Default behaviour is
             unchanged (v0.5 configuration).
Spec:        Fixed before any run, no parameter search: opening range = first 60 min of each
             session; entry on the first 15m close outside it (limit at that close, 30 min
             expiry); 1H bias not against; stop at the opposite side of the range; target 1 R.
Evaluation:  local replay, public data, same costs; one run on each of three 90-day windows.
Rule:        eligible as a default only if it passes the bar on all three windows.
Result:      Signal C only, one run per window (spec committed first as ff83307):
             in-sample     259 RTs PF 0.70 DD 17.0 % net −149.7 USDT (PF before fees 1.02)
             out-of-sample 231 RTs PF 0.65 DD 18.4 % net −148.7 USDT (PF before fees 0.95)
             holdout       259 RTs PF 0.83 DD  9.6 % net  −76.3 USDT (PF before fees 1.13)
             Fees fell to ~0.1 R per trade as intended, but there is no edge before fees.
Verdict:     FAIL on all three windows → not adopted; no parameter adjusted after the fact.
Decision:    Default stays v0.5 behaviour. No paper or live trading. See RESEARCH_v0.10.md.

## v0.9.0 — 2026-11-10 — offline research: cost-aware stop-distance filter (not adopted)
Change:      New opt-in option signal_b_min_r_pct (default 0 = off). Default behaviour is
             unchanged and replays identically to v0.5. Adds an offline research harness
             under research/ (public data, local NautilusTrader replay, no API key).
Question:    Can the profit factor be fixed without overfitting?
Finding:     Fees consume the edge: before fees PF is 1.57 in-sample but only 1.14
             out-of-sample and 1.27 on a fresh holdout — below 1.3 before any cost.
Test:        Skip entries whose stop distance is below r_min % of price (levels fixed in
             advance at 0.20 / 0.32 / 0.50). Local replay, three 90-day windows:
             r_min 0.00  in-sample 107 RTs PF 1.09 | out-of-sample 110 RTs PF 0.79 | holdout 145 RTs PF 0.89
             r_min 0.20  in-sample  87 RTs PF 1.35 | out-of-sample  97 RTs PF 0.74 | holdout 137 RTs PF 0.90
             r_min 0.32  in-sample  71 RTs PF 1.40 | out-of-sample  72 RTs PF 0.68 | holdout 116 RTs PF 0.87
             r_min 0.50  in-sample  41 RTs PF 1.56 | out-of-sample  34 RTs PF 1.28 | holdout  57 RTs PF 0.71
Verdict:     Passes the bar in-sample, fails on both other windows → overfit, NOT adopted.
Decision:    Default stays v0.5 behaviour. No paper or live trading. See RESEARCH_v0.9.md.

## 2026-11-10 — confirmation run of the restored default (no strategy change, no new version)
Run:         pbrun-44028019082f — v0.8.1 package at main (d2b4375), in-sample window
             2026-08-11 17:15 → 2026-11-09 17:15 UTC, historical replay only.
Result:      identical to the original v0.5.0 run pbrun-77fb5c12d8f8 to the last digit:
             RTs=109 PF=1.0664 DD=5.67 % net +21.83 USDT, 404 orders / 218 fills, exits
             stop 51 / target 36 / funding 13 / time stop 9 → FAIL on PF, as before.
Note:        funding coverage start slid from 2026-08-12 to 2026-08-13 (rolling ~90-day
             endpoint). No trade was affected this time, but exact reproduction of the
             in-sample numbers will degrade as the window ages. See CONFIRM_v0.8.1.md.

## v0.8.1 — 2026-11-10 — default restored (not a strategy version, no run)
Change:      Repository default signal_b_entry_mode close → midpoint. With that default the
             package behaves as v0.5.0 (2.5× volume, 2R target, 180 min time stop, Signal A
             off, midpoint entry). signal_b_entry_mode: close remains available as an option.
Why:         v0.8.0 (close entry) failed both evaluation windows but was merged, which left
             the failing configuration as the default. The v0.8.0 results below stay on record.
Evidence:    for this default, the existing v0.5 runs apply: in-sample pbrun-77fb5c12d8f8
             (PF 1.07, DD 5.7 %, 109 RTs) and out-of-sample pbrun-d8b8abbb3a69 (PF 0.59,
             DD 21.5 %, 110 RTs). Both FAIL the bar; nothing is cleared for live trading.
Tests:       defaults pinned in tests (params default, manifest default, and midpoint
             geometry); close mode still covered by its own tests.
Decision:    no further strategy version until the owner decides.

## v0.8.0 — 2026-11-10
Change:      Structural: Signal B entry limit price moves from the breakout bar's midpoint to
             the breakout bar's close (signal_b_entry_mode midpoint → close). Order type
             (limit), expiry (30 min), stop (bar's opposite extreme), target (2R) unchanged.
Baseline:    v0.5.0 parameters — the only configuration with both an in-sample and an
             out-of-sample result. volume_spike_mult and signal_b_target_r therefore return
             from the v0.6 values (3.0, 1.5) to the v0.5 values (2.5, 2.0). The package
             differs from v0.5.0 (commit 3ec6949) only by the entry mode.
Hypothesis:  A limit at the midpoint only fills when price pulls back half the breakout
             bar, which may select failing breakouts and miss those that run. Entering at
             the close should improve the target/stop mix.
Side effect: R is measured from the entry, so with the close entry R is larger, size is
             smaller for the same 5 USDT risk, and the 2R target is further away.
Baselines:   in-sample v0.5 pbrun-77fb5c12d8f8 (RTs=109 PF=1.07 DD=5.7 %);
             out-of-sample v0.5 pbrun-d8b8abbb3a69 (RTs=110 PF=0.59 DD=21.5 %).
Windows:     in-sample 2026-08-11 17:15 → 2026-11-09 17:15 UTC;
             out-of-sample 2026-05-13 17:15 → 2026-08-11 17:15 UTC (same split as v0.7).
             The out-of-sample window still runs with the funding fallback (no funding
             history served for it), exactly as its v0.5 baseline did.
Mode:        backtest only — no live orders, no trade permissions, no paid data calls
Result:      both runs completed on the same bars as their v0.5 baselines (8,869 per symbol).

             |                          | In-sample            | Out-of-sample        |
             | Run                      | pbrun-09cb4e435830   | pbrun-510927f72ccd   |
             | v0.5 midpoint  PF/DD/RTs | 1.07 / 5.7 % / 109   | 0.59 / 21.5 % / 110  |
             | v0.8 close     PF/DD/RTs | 1.01 / 10.4 % / 159  | 0.52 / 21.2 % / 136  |
             | v0.8 win rate, net       | 55 %, +3.3 USDT      | 43 %, −186.4 USDT    |
             | v0.8 expectancy (nominal)| +0.00 R              | −0.27 R              |
             | Verdict                  | FAIL (PF and DD)     | FAIL (PF and DD)     |

             v0.8 exits in-sample: stop 74, target 35, funding 28, time stop 22 (19 kept
             through funding). Out-of-sample: stop 60, funding rate-unknown 41, time stop 18,
             target 17.
Reading:     The close entry fills far more often (159 vs 109 and 136 vs 110 round-trips),
             so the midpoint limit was indeed skipping many breakouts. But the added trades
             are not profitable: profit factor is slightly lower in both windows, and
             in-sample drawdown rose from 5.7 % to 10.4 %, now failing that criterion too.
             The adverse-selection hypothesis is not supported.
Decision:    FAIL in both windows. Not recommended as a baseline. Parameter tuning
             (v0.4–v0.6), an out-of-sample check (v0.7) and this structural entry change
             have all failed the bar; Signal B has no demonstrated edge. Stopped for the
             owner's decision.

## v0.7 — 2026-11-10 — out-of-sample check (no strategy change, no new package version)
Change:      None. v0.5.0 package exactly as merged (commit 3ec6949) replayed on the 90 days
             immediately before the original window; only backtest_end_utc differs
             (2026-08-11T17:15Z). Repository parameters are untouched (main still holds v0.6.0).
Baseline:    in-sample v0.5.0 run pbrun-77fb5c12d8f8 (RTs=109 PF=1.07 DD=5.7 %, +21.8 USDT).
Window:      2026-05-13 17:15 → 2026-08-11 17:15 UTC, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
             (8,869 bars per symbol, 97 % coverage; run pbrun-d8b8abbb3a69, status completed)
Mode:        backtest only — no live orders, no trade permissions, no paid data calls
Result:      RTs=110 PF=0.59 (engine fill-based PF 1.09) DD=21.5 % of budget, win rate 47 %,
             net −167.2 USDT, expectancy -0.30 R nominal (in-sample +0.04 R)
             → FAIL on PF and DD.
             Exits: stop 53, target 20, funding rate-unknown 34, time stop 2, daily cap 1.
Defect:      the funding endpoint served only the latest ~90 days, so this window ran with
             the conservative flatten-before-every-settlement fallback (34 exits) instead of
             the direction-aware rule; the package's degraded flag did not catch it.
             Estimated effect on PF ≈ 0.05 (v0.2 vs v0.3.1), not enough to explain the gap.
Decision:    FAIL. The in-sample result did not generalise. Full write-up in OOS_v0.5.md.
             No further version started; next step is the owner's choice.

## v0.6.0 — 2026-11-10
Change:      TWO variables (owner-approved exception to the one-variable rule):
             signal_b_target_r 2.0 → 1.5 and volume_spike_mult 2.5 → 3.0.
             Signal A stays disabled; time stop stays 180 min; everything else unchanged.
Hypothesis:  v0.5 had 51 stops vs 36 targets at 2R. A nearer target should convert some
             stops and time/funding exits into wins; a stricter volume threshold should
             remove the weakest breakouts. Risks: smaller winners lower the payoff ratio,
             and fewer signals may push round-trips toward the 60 minimum.
Caveat:      With two changes the result cannot be attributed to either alone. If the
             version passes or looks promising, a follow-up should isolate each change.
Baseline:    v0.5.0 run pbrun-77fb5c12d8f8 (RTs=109 PF=1.07 DD=5.7 %, +21.8 USDT).
Window:      pinned (backtest_end_utc = 2026-11-09T17:15Z), BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
Mode:        backtest only — no live orders, no trade permissions, no paid data calls
Result:      run pbrun-a1ad37d733c6 (platform status completed, 377 orders / 102 positions,
             identical bars to v0.5: 8,869 per symbol).
             RTs=102 PF=1.02 (engine fill-based PF 1.45) DD=5.8 % of budget, win rate 58 %,
             net +6.0 USDT on 1,000 USDT, Sharpe 0.16 → FAIL on PF (≥ 1.3); DD criterion met.
             Exits: target 42, stop 40, funding (pays) 12, time stop 8; 6 kept through funding.
Effect:      vs v0.5 on the same bars: win rate 51 % → 58 % and targets now outnumber stops
             (42 vs 40, was 36 vs 51), but each winner is smaller, so PF fell 1.07 → 1.02 and
             net +21.8 → +6.0 USDT. Round-trips fell only 109 → 102. Not attributable to
             either change alone (two variables).
Reading:     v0.4, v0.5 and v0.6 all land at PF 1.02–1.07 with DD 5.7–5.9 %. Parameter
             changes move the win rate and payoff ratio against each other without lifting
             expectancy: Signal B as specified is roughly break-even after fees on this window.
Decision:    FAIL. Stopped for the owner's decision. Recommendation: do not adopt v0.6 as
             the baseline (v0.5 is better on PF and net). Further threshold nudges on one
             90-day window risk curve-fitting; the next step should be structural (entry
             mechanics) or an out-of-sample check, not another target/threshold tweak.

## v0.5.0 — 2026-11-10
Change:      time_stop_minutes 120 → 180. Signal A stays disabled; everything else unchanged.
Hypothesis:  In v0.4, 14 of 109 Signal B trades were closed by the two-hour time stop before
             reaching stop or 2R target. A 2R breakout on 15m bars often needs more than two
             hours; giving it three should convert some time-stops into targets without
             changing entry quality. Risk: more time in market → more stops and funding exits.
Baseline:    v0.4.0 run pbrun-3e8aac580d17 (RTs=109 PF=1.03 DD=5.9 %, +8.5 USDT).
Window:      pinned (backtest_end_utc = 2026-11-09T17:15Z), BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
Mode:        backtest only — no live orders, no trade permissions, no paid data calls
Result:      run pbrun-77fb5c12d8f8 (platform status completed, 404 orders / 109 positions,
             identical bars to v0.3.1 / v0.4: 8,869 per symbol).
             RTs=109 PF=1.07 (engine fill-based PF 1.47) DD=5.7 % of budget, win rate 51 %,
             net +21.8 USDT on 1,000 USDT, Sharpe 0.45 → FAIL on PF (≥ 1.3); DD criterion met.
             Exits: stop 51, target 36, funding (pays) 13, time stop 9; 9 kept through funding.
Effect:      vs v0.4 on the same bars: time stops 14 → 9; of the 5 freed trades 1 reached
             target and 4 stopped out. PF 1.03 → 1.07, DD 5.9 % → 5.7 %, net +8.5 → +21.8 USDT.
             A small improvement in the right direction; the time stop was not the binding
             constraint. Stops (51) vs targets (36) at 2R remains the limiting ratio.
Decision:    FAIL. Keep 180 min (better than 120 on every measured metric). Stopped for the
             owner's decision. Candidates for v0.6 (one each): signal_b_target_r 2.0 → 1.5;
             volume_spike_mult 2.5 → 3.0 (stricter breakout entry); Signal A back on with
             vwap_trigger_sigma 2.0 as a separately measured version.

## v0.4.0 — 2026-11-10
Change:      enable_signal_a true → false. Signal A (VWAP reversion) is disabled for one
             version; Signal B, regime filter, sessions, funding rule, risk limits and
             exits are unchanged.
Hypothesis:  Across v0.1–v0.3.1 stops (~60) outnumbered targets (~39) with ~30 time stops.
             Signal A's geometry (entry 1.0σ, stop 2.0σ, target at VWAP) needs well above
             50 % wins and got 46 %. Isolating Signal B attributes the loss to one engine.
Baseline:    v0.3.1 run pbrun-16e2dea33de4 (RTs=149 PF=0.83 DD=11.4 %).
Window:      pinned to the v0.3.1 window via backtest_end_utc = 2026-11-09T17:15Z,
             last 90 days (+5 warm-up), BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
Mode:        backtest only — no live orders, no trade permissions, no paid data calls
Result:      run pbrun-3e8aac580d17 (platform status completed, 409 orders / 109 positions,
             identical bars to v0.3.1: 8,869 per symbol, 2026-08-07 14:00 → 2026-11-09 17:00).
             RTs=109 PF=1.03 (engine fill-based PF 1.44) DD=5.9 % of budget, win rate 50 %,
             net +8.5 USDT on 1,000 USDT, Sharpe 0.18 → FAIL on PF (≥ 1.3); DD criterion met.
             Exits: stop 47, target 35, time stop 14, funding (pays) 13; 8 kept through funding.
Attribution: removing Signal A moved PF 0.83 → 1.03 and DD 11.4 % → 5.9 % on the same bars,
             so the ~40 Signal A round-trips were the net-losing engine; Signal B alone is
             roughly break-even after fees (47 stops vs 35 targets at 2R, 14 time stops).
Decision:    FAIL. Stopped for the owner's decision. Candidates for v0.5 (one each):
             signal_b_target_r 2.0 → 1.5; time_stop_minutes 120 → 180 (14 time stops cut
             trades before 2R); re-enable Signal A with vwap_trigger_sigma 2.0 as a
             separately measured version.

## v0.3.0 — 2026-11-09
Change:      Funding rule in replay becomes direction-aware (as live): a position is
             flattened before the 00/08/16 UTC settlement only when it would PAY funding
             (long & rate > 0, short & rate < 0). Historical funding rates are fetched per
             symbol; where unavailable the replay falls back to flattening before every
             settlement and reports the symbol as degraded.
Hypothesis:  v0.2 had 29 funding-window exits (20 % of round-trips) cut before target or
             stop; keeping the positions that receive funding should lift PF without
             changing entries, stops or targets.
Baseline:    v0.2.0 run pbrun-9ec1a7d1d9e0 (RTs=148 PF=0.78 DD=14.0 %).
Window:      2026-08-11 17:15 → 2026-11-09 17:15 UTC, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
             (run pbrun-57c1bdab4a5e, platform status completed, 556 orders / 150 positions)
Result:      RTs=150 PF=0.84 (engine fill-based PF 1.27) DD=11.4 % of budget, win rate 49 %,
             net −68.4 USDT on 1,000 USDT → FAIL on PF and DD.
             Exits: stop 59, target 38, time stop 30, funding (pays) 11, funding (rate
             unknown) 11, daily cap 1; 9 positions kept through a settlement they would
             have received funding on.
             Data defect: hourly funding rows hit the 1000-row cap, covering only the last
             ~42 days → the 11 "rate unknown" exits. Fixed in v0.3.1 (4h aggregation).
Decision:    FAIL. Complete the funding fix (v0.3.1) and re-run before any other change.

## v0.3.1 — 2026-11-09
Change:      None to strategy rules. Funding history fetched at 4h aggregation so the
             whole 90-day window is covered in one page (was truncated to ~42 days).
Hypothesis:  Removes the 11 "funding_window_rate_unknown" exits; everything else equal.
Baseline:    v0.3.0 run pbrun-57c1bdab4a5e.
Window:      2026-08-11 17:15 → 2026-11-09 17:15 UTC, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
             (run pbrun-16e2dea33de4, platform status completed; funding coverage 539 rows
             per symbol from 2026-08-12, no degraded symbols)
Result:      RTs=149 PF=0.83 (engine fill-based PF 1.25) DD=11.4 % of budget, win rate 46 %,
             net −77.9 USDT on 1,000 USDT → FAIL on PF and DD.
             Exits: stop 60, target 39, time stop 33, funding (pays) 16, daily cap 1;
             15 positions kept through a settlement they received funding on.
Decision:    FAIL. Funding rule is now fully specified and evidenced; it is not the main
             cost. Stops (60) vs targets (39) and 33 time stops point at entry quality:
             next single change = Signal A trigger band (v0.4), pending owner go-ahead.

Pipeline correction shipped with v0.3.0: warm-up bars are now fed to the
strategy (entries blocked until the replay window starts) so the 4H regime
filter is available from the first evaluated bar; v0.2 lost ~2.3 days of
entries per symbol to "regime unavailable".

## v0.2.0 — 2026-11-09
Change:      Universe BTC/ETH/SOL → every Bitget USDT-M crypto perpetual passing the
             liquidity scan (adds XRPUSDT; RWA stock-token perps opt-in). See UNIVERSE.md.
Hypothesis:  More qualifying symbols → more independent round-trips per window at the
             same per-trade risk, without touching signal or exit parameters.
Baseline:    v0.1.0 preliminary run pbrun-0e45cab71d7f (below).
Window:      2026-08-11 17:15 → 2026-11-09 17:15 UTC, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
             (35,476 bars, 97 % coverage; run pbrun-9ec1a7d1d9e0, platform status completed)
Result:      RTs=148 PF=0.78 (engine fill-based PF 1.17) DD=14.0 % of budget, win rate 47 %,
             net −97.7 USDT on 1,000 USDT → FAIL on PF and DD.
             Exits: stop 59, target 36, funding window 29, time stop 23, daily cap 1.
             Entry blocks: regime unavailable 872 (warm-up bars were dropped before the
             strategy saw them — fixed in v0.3), event-risk regime 960, volume gate 1,526,
             pre-funding 611, daily-cap halt 468, max-concurrent 282.
Decision:    FAIL. Next single change: direction-aware funding rule in replay (v0.3).
Non-strategy fixes shipped with this version (no effect on rules):
  * replay strategy computes features incrementally from raw OHLCV (no injected
    columns), so the platform's evidence replay runs the same code path
  * artifacts written to the package-relative output/ path the Runner collects
  * no-op ModifyOrder calls suppressed (Nautilus logged them as errors)
  * max_backtest_symbols added for the 180 s sandbox budget

## v0.1.0 — 2026-11-09
Change:      Initial specification and implementation.
Hypothesis:  Session-window VWAP reversion + volume breakouts on BTC/ETH/SOL perps,
             with hard intraday risk limits, achieve PF ≥ 1.3 at < 6 % budget drawdown.
Baseline:    none (first version)
Window:      2026-08-11 17:00 → 2026-11-09 17:00 UTC, BTCUSDT, ETHUSDT, SOLUSDT (26,604 bars, 97 % coverage)
Result:      PRELIMINARY (platform marked the run failed: report path + evidence replay,
             see v0.2.0 fixes) RTs=145 PF=0.88 DD=11.4 % of budget, win rate 48 %,
             net −47.4 USDT on a 1,000 USDT budget → FAIL on PF and DD.
             Exits: stop 55, target 38, funding window 28, time stop 23, daily cap 1.
             Entry blocks: daily-cap halt 409 bars, pre-funding 469, volume gate 691,
             regime chop 288 / event risk 144, max-concurrent 129.
Decision:    Do not tune on this run. Fix the pipeline, re-run as v0.2.0 with the
             scanned universe, then evaluate one signal/exit variable per version.
