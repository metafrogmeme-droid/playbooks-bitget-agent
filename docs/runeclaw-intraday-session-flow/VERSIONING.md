# Versioning & evaluation policy

**Current version: v0.4.0** (`src/params.py::PLAYBOOK_VERSION`, `manifest.yaml::version`).

## Rules

0. **Same bars for every version.** `backtest_end_utc` pins the evaluation end so
   successive versions replay identical data; it moves only when a new baseline
   window is adopted, and that move is itself a changelog entry.

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
4. **Live-only rules are declared.** The spread gate needs an L1 quote and is
   live-only. Since v0.3 the funding rule is direction-aware in replay too,
   using historical funding rates; a symbol without funding coverage falls
   back to flattening before every settlement and is listed as degraded in
   `evaluation.json`. Drift is reported, never hidden.
5. **Journals are evidence.** Every order event is logged with `signal_id`,
   timestamp, limit/fill price, stop, target and exit reason. Live PnL in the
   ledger is tagged as estimate when derived from mark price rather than fills.

## Version roadmap (candidates, one per version)

| Version | Single change under test | Why |
|---|---|---|
| v0.2 | Universe → all liquid crypto USDT-M perps from the scan (adds XRPUSDT) | More independent round-trips |
| v0.3 | Direction-aware funding rule in replay (historical funding rates injected) | v0.2 had 29 funding exits of 148 round-trips |
| v0.4 | `enable_signal_a` true → false (isolate Signal B) | Attribute the loss to one engine |
| v0.5 | depending on v0.4: `vwap_trigger_sigma` 1.5 → 2.0, or `vwap_stop_sigma` 2.0 → 1.5, or `signal_b_target_r` 2.0 → 1.5 | Fix the engine v0.4 shows is losing |

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
