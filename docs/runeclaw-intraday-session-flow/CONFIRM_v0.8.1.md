# Confirmation run — restored default (v0.8.1) vs original v0.5.0, in-sample (2026-11-10)

Purpose: check by an actual replay, not only by tests and a manifest diff, that the
restored repository default (midpoint entry, v0.5 parameters, package label 0.8.1)
behaves exactly like the original v0.5.0 package. No strategy change, no new version.

## Setup

| | Original | Confirmation |
|---|---|---|
| Package | v0.5.0, commit `2a853e6` | v0.8.1, `main` at `d2b4375`, unmodified |
| Run | `pbrun-77fb5c12d8f8` | `pbrun-44028019082f` |
| Window (UTC) | 2026-08-11 17:15 → 2026-11-09 17:15 | same (pinned by `backtest_end_utc`) |
| Symbols / bars | BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT; 8,869 bars each | same |
| Mode | sandbox historical replay | sandbox historical replay; no paper or live orders, no trading permissions, no paid data |

## Result: identical

| Metric | Original v0.5.0 | Confirmation v0.8.1 | Bar |
|---|---|---|---|
| Round-trips | 109 | 109 | ≥ 60 |
| Profit factor (per position) | 1.0664208213977922 | 1.0664208213977922 | ≥ 1.3 |
| Max drawdown (% of budget) | 5.671252921999985 | 5.671252921999985 | < 6 % |
| Net P&L (1,000 USDT budget) | +21.8278992 USDT | +21.8278992 USDT | |
| Win rate | 51.3761 % | 51.3761 % | |
| Orders / fills / positions | 404 / 218 / 109 | 404 / 218 / 109 | |
| Exits: stop / target / funding / time stop | 51 / 36 / 13 / 9 | 51 / 36 / 13 / 9 | |
| Kept through funding | 9 | 9 | |
| Verdict | FAIL (PF) | FAIL (PF) | |

Every reported figure matches to the last digit, including the per-reason entry
block counts. The restored default is confirmed to be the v0.5.0 behaviour.

## One thing that did differ: funding coverage start

The managed funding-rate endpoint serves a rolling window of roughly the latest
90 days. In the original run its first row was 2026-08-12 00:00 UTC; in this run,
a day later, it was 2026-08-13 00:00 UTC. No trade happened to depend on the lost
day, so the results are unchanged.

This matters for future reruns: as the calendar moves on, more of the pinned
in-sample window will lose funding history and fall back to flattening before
every settlement, exactly as the out-of-sample window already does (see
`OOS_v0.5.md`). An exact reproduction of these numbers will therefore stop being
possible on the current data path within days to weeks. The package's
degraded-data flag still does not detect this case.

## Status

The default configuration fails the pre-registered bar (profit factor 1.07 against
1.3). Nothing is cleared for paper or live trading. No further strategy version
has been started.
