# Versioning & evaluation policy

**Current version: v0.9.0** — default configuration equals v0.5.0 behaviour (midpoint entry, stop-distance filter off); no strategy version is in progress (`src/params.py::PLAYBOOK_VERSION`, `manifest.yaml::version`).

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
| v0.5 | `time_stop_minutes` 120 → 180 | v0.4: Signal B alone break-even (PF 1.03, DD 5.9 %); 14 of 109 trades cut by the time stop |
| v0.6 | `signal_b_target_r` 2.0 → 1.5 **and** `volume_spike_mult` 2.5 → 3.0 (owner-approved two-variable exception) | v0.5: PF 1.07, DD 5.7 %; stops 51 vs targets 36 is the limiting ratio |
| v0.7 | out-of-sample check of v0.5 parameters on the preceding 90 days (no strategy change) | done: FAIL, PF 0.59, DD 21.5 % — see OOS_v0.5.md |
| v0.8 | Signal B entry: limit at breakout bar midpoint → limit at breakout bar close, on v0.5 parameters; evaluated in-sample and out-of-sample | done: FAIL in both windows (in-sample PF 1.01, DD 10.4 %; out-of-sample PF 0.52, DD 21.2 %) |
| v0.8.1 | repository default restored to `signal_b_entry_mode: midpoint` (v0.5 behaviour); `close` kept as an option | housekeeping, not a strategy version; no run |
| v0.9 | offline research: cost-aware minimum stop distance (`signal_b_min_r_pct`), three windows incl. a fresh holdout | done: passes in-sample, fails out-of-sample and holdout; not adopted — see RESEARCH_v0.9.md |

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
