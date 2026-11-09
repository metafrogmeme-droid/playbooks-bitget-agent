# Changelog — RUNECLAW Intraday Session Flow

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
