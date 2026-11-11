# Conclusion — RUNECLAW Intraday Session Flow (2026-11-11)

Credit: HUMANOID-TRADERS · RUNECLAW, Patrick Baur, CEO.

## Decision

**Directional signal work on this playbook is stopped under the current constraints.**
Owner decision of 2026-11-11, following the premise review and the last approved test.

Nothing in this repository is cleared for paper or live trading. No live or paper
order was ever placed by this work.

## What was tested

Bar throughout: at least 60 round-trips, profit factor (PF) at least 1.3 and maximum
drawdown under 6 % of a 1,000 USDT budget, after fees of 0.02 % maker and 0.06 % taker.

| Version | What changed | Result | Verdict |
|---|---|---|---|
| v0.1 – v0.3.1 | Signals A and B together; universe scan; funding rule made direction-aware | PF 0.78 – 0.88, drawdown 11 – 14 % | Fail |
| v0.4 | Signal A (VWAP reversion) switched off | PF 1.03, drawdown 5.9 % | Fail on PF. Signal A was the losing engine |
| v0.5 | Time stop 120 → 180 minutes | PF 1.07, drawdown 5.7 % | Fail on PF. Best configuration found |
| v0.6 | Target 2 R → 1.5 R and volume 2.5× → 3.0× | PF 1.02 | Fail |
| v0.7 | v0.5 on the preceding 90 days (out-of-sample) | PF 0.59, drawdown 21.5 % | Fail. The in-sample result did not hold |
| v0.8 | Signal B entry at the bar close instead of the midpoint | PF 1.01 in-sample, 0.52 out-of-sample | Fail on both |
| v0.9 | Cost-aware minimum stop distance | At the two levels with enough trades: PF 1.35 – 1.40 in-sample; 0.68 – 0.74 and 0.87 – 0.90 on the other two windows | Overfit. Not adopted |
| v0.10 | Signal C, session opening-range breakout | PF 0.70 / 0.65 / 0.83 on three windows | Fail on all three |
| v0.11 | Signal D, hourly trend persistence | PF 0.70 / 0.73 / 0.78 in discovery (18 months) | Killed at stage 1 |

v0.1 to v0.8 were replayed in the Bitget sandbox; v0.9 to v0.11 in a local replay on
public data that reproduces the sandbox closely in-sample.

## What we learned

1. **Fees are the binding constraint at this timeframe.** A round trip costs up to
   0.08 % of the position, which is a quarter to a third of a typical 15-minute move.
   Signal B earned before fees on every window (PF 1.57 / 1.14 / 1.27) and lost all of
   it to fees.
2. **Where fees were tamed, there was no edge underneath.** Signals C and D used
   stops about twice as wide, halving the fee burden, and their profit factor
   before fees was about 1.0.
3. **Tuning produced in-sample passes that did not generalise.** The v0.9 filter
   cleared the bar on the window it could have been fitted to and failed on the two it
   could not. The out-of-sample and holdout discipline is what caught this.
4. **Three different mechanisms agree.** A volume-spike breakout, an opening-range
   breakout and hourly trend persistence all fail after costs, consistently across
   periods and contracts.

The conclusion is limited to what was tested: intraday directional signals on BTC,
ETH, SOL and XRP USDT-M perpetuals, public price data from December 2022 to November
2026, retail fee tier, positions flat by midnight UTC with a 180-minute time stop.
It is not a statement about other venues, fee tiers, holding periods or data.

## State of the repository

* Package label `0.11.0`. **The default configuration is the v0.5 behaviour**: Signal B
  only, 2.5× volume, 2 R target, midpoint entry, 180-minute time stop. It fails the
  bar and is kept as the reference configuration, not as a tradable one.
* Research options, all off by default and pinned by tests: `signal_b_entry_mode:
  close`, `signal_b_min_r_pct`, `enable_signal_c`, `enable_signal_d`. Signal A is off.
* 55 unit tests pass. The validator mirror passes.
* No exchange key is stored in the repository or its history.
* Packages uploaded to the Bitget sandbox during v0.1 – v0.8 were temporary drafts.
  None was confirmed, published or subscribed.

## What would reopen the work

Only an explicit owner decision on one of these, followed by a new pre-registration
under the rules in `PREMISE_REVIEW.md`:

* a change to a constraint: fee tier, flat by midnight, the 180-minute time stop, or
  the four-contract universe;
* a policy decision to admit a keyed or third-party data source, which the
  liquidation and funding premises would need.

No new data source is added by this conclusion. Another variant of Signals A to D is
not a reason to reopen.

## Where to find the record

| Document | Content |
|---|---|
| `CHANGELOG.md` | Every version, its hypothesis, numbers and verdict |
| `PREMISE_REVIEW.md` | Cost hurdle, candidate premises, data split, kill criteria |
| `RESEARCH_v0.9.md`, `RESEARCH_v0.10.md`, `RESEARCH_v0.11.md` | The three offline studies, with pre-registration and results |
| `OOS_v0.5.md`, `CONFIRM_v0.8.1.md` | Out-of-sample check and confirmation of the default |
| `PARAMETERS.md`, `PSEUDOCODE.md` | Every parameter and every rule |
| `research/` | Public-data download, local replay and study scripts to reproduce the offline results |

## Housekeeping left with the owner

* Switch the GitHub default branch from `ccr-63044170-g9qjmk` to `main`.
