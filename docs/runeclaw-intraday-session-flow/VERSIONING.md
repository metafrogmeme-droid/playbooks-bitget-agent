# Versioning & evaluation policy

**Current version: v0.1.0** (`src/params.py::PLAYBOOK_VERSION`, `manifest.yaml::version`).

## Rules

1. **One variable per version.** A new version changes exactly one parameter
   or one rule. The change, the hypothesis and the comparison baseline are
   recorded in `CHANGELOG.md` *before* the run.
2. **Pre-registered pass criteria** (fixed for v0.x, encoded in
   `src/main_backtest.py::PASS_CRITERIA`):

   | Criterion | Threshold |
   |---|---|
   | Round-trips in the evaluation window | ≥ 60 |
   | Profit factor (gross profit / gross loss) | ≥ 1.3 |
   | Max drawdown (peak-to-trough, % of margin budget) | < 6 % |

   Verdicts: **PASS** only when all three hold. **PENDING** when round-trips
   < 60 or a metric is not measurable. **FAIL** otherwise. PENDING is never
   reported as PASS; a PENDING version may be extended with a longer window,
   not relaxed.
3. **No live run before PASS.** `follow_trade` subscriptions are opened only
   for a version whose `evaluation.json` says PASS on a window that ends no
   more than 7 days before the go-live date.
4. **Live-only rules are declared.** v0.1 knows two: the spread gate (needs an
   L1 quote) and direction-aware funding flattening (needs the live funding
   rate). Replay flattens before every funding time instead. Both are listed
   in the manifest meta and README so live/replay drift is expected, not hidden.
5. **Journals are evidence.** Every order event is logged with `signal_id`,
   timestamp, limit/fill price, stop, target and exit reason. Live PnL in the
   ledger is tagged as estimate when derived from mark price rather than fills.

## Version roadmap (candidates, one per version)

| Version | Single change under test | Why |
|---|---|---|
| v0.2 | Direction-aware funding rule in replay (inject historical funding as a feature) | Remove the biggest live/replay drift |
| v0.3 | `vwap_trigger_sigma` 1.5 → 2.0 | Fewer, cleaner reversion entries |
| v0.4 | `signal_b_target_r` 2.0 → 1.5 | Higher hit rate on breakouts |
| v0.5 | Add 1H ADX or range-width gate for Signal A only | Avoid fading real trends |

## Changelog entry template

```
## vX.Y.Z — YYYY-MM-DD
Change:      <one parameter/rule, old → new>
Hypothesis:  <what should improve and why>
Baseline:    <previous version + window>
Window:      <start → end, symbols>
Result:      RTs=<n> PF=<x> DD=<y%> → <PASS|PENDING|FAIL>
Decision:    <adopt | revert | extend window>
```
