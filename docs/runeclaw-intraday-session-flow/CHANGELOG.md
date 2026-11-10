# Changelog — RUNECLAW Intraday Session Flow

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
Result:      not yet run → verdict PENDING
Decision:    run sandbox evaluation; report and stop for the owner's next decision

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
