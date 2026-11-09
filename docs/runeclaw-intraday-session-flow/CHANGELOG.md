# Changelog — RUNECLAW Intraday Session Flow

## v0.2.0 — 2026-11-09
Change:      Universe BTC/ETH/SOL → every Bitget USDT-M crypto perpetual passing the
             liquidity scan (adds XRPUSDT; RWA stock-token perps opt-in). See UNIVERSE.md.
Hypothesis:  More qualifying symbols → more independent round-trips per window at the
             same per-trade risk, without touching signal or exit parameters.
Baseline:    v0.1.0 preliminary run pbrun-0e45cab71d7f (below).
Window:      to be run — last 90 days (+5 warm-up), BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
Result:      not yet run → verdict PENDING
Decision:    run sandbox evaluation; no live run before PASS
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
