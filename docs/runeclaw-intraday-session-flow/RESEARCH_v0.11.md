# v0.11 research — Signal D, hourly trend persistence (2026-11-11)

Credit: HUMANOID-TRADERS · RUNECLAW, Patrick Baur, CEO.

Offline backtest research only: public data, local replay, no exchange keys, no paper
or live orders. This is the single test approved after `PREMISE_REVIEW.md`. Signal D
is off by default; the default configuration is unchanged.

## Stage 0 — pre-registration (written and committed before any Signal D backtest)

**Mechanism: who pays, and why it might persist.** After an hour in which price moves
decisively in one direction, some participants still have to trade the same way:
leveraged positions on the losing side are stopped or liquidated in steps, larger
orders are worked over hours rather than minutes, and hedgers and momentum followers
react with a delay. If that follow-through exists, the counterparties paying for it
are the late and forced traders. It may not exist: the effect is widely known, the
contracts are liquid, and fees are a real hurdle. The working assumption is that it
does not (the null in the premise review); this test is designed to reject or confirm
that cheaply.

**Specification (frozen).**

| Element | Rule |
|---|---|
| Decision time | The close of a completed clock hour (the 15m bar opening at minute 45), inside a session window |
| Holding-period gate | Enter only if the full 180-minute time stop fits before the next pre-funding flatten and before the end-of-day flatten. In practice entries at 08:00, 09:00 and 16:00 UTC |
| Trigger | The completed hour's body (close − open) is at least 0.5 × ATR(14) of completed 1H bars |
| Trend agreement | The return over the last L completed hours has the same sign as the body |
| Entry | Limit at the trigger bar's close, 30-minute expiry |
| Stop | 1.0 × ATR(1H) from the entry |
| Exit | Target at 2 R; otherwise the playbook's 180-minute time stop. No trailing |
| Everything else | Unchanged, as the owner decided: fee tier 0.02 % / 0.06 %, flat by midnight, 180-minute time stop, four contracts (BTC, ETH, SOL, XRP), 4H ATR regime filter, session windows, 0.5 % risk per trade on a 1,000 USDT budget, max 2 concurrent, max 3 trades per contract per day, 1.5 % daily loss cap, 24h volume gate |
| Configuration under test | `enable_signal_d: true`; Signals A, B and C off |

**Variants (the three allowed, declared here; they differ only in L):**
L = 1 hour, L = 4 hours (base), L = 12 hours. No other variant will be run.

**Expected trade count.** Three decision points per contract per day gives about
1,080 opportunities per 90 days. A strong, trend-agreeing hour is expected at roughly
one decision point in five, before the concurrency and regime gates, so well above
the 60 round-trips per 90 days required. If the realised count is below 60 per
90 days the idea fails the stage-2 bar.

**Data and treatment (as accepted in the premise review).**

| Stage | Period | Runs |
|---|---|---|
| 1. Discovery | 2023-01-01 → 2024-07-01 | The three variants, once each |
| 2. Validation | 2024-07-01 → 2025-07-01 | One run of the selected variant, plus one at 1.5× fees |
| 3. Final test | 2025-07-01 → 2026-02-01 | One run, never repeated |
| 4. Recent check | The three 2026 windows used before | One run each |

* Public Bitget 15m candles, no key. Local replay (`research/local_backtest.py`).
* Funding rule in the conservative fallback mode on every window (flatten before
  every settlement), so all windows are treated alike.
* Costs: maker 0.02 %, taker 0.06 %.

**Kill criteria (from the premise review, unchanged).**

| Stage | Requirement | If not met |
|---|---|---|
| 1. Discovery | PF after fees ≥ 1.4 pooled; profitable in at least 4 of 6 quarters and on at least 3 of 4 contracts; no single quarter above half of net profit | Kill |
| 2. Validation | ≥ 60 round-trips per 90 days, PF ≥ 1.3, max drawdown < 6 % of budget, and PF ≥ 1.1 at 1.5× fees | Kill. No variants |
| 3. Final test | Same bar as stage 2 | Kill. No variants |
| 4. Recent check | PF ≥ 1.0 after fees on each of the three 2026 windows | Kill |

**Selection rule in discovery.** A variant qualifies only if it meets every stage-1
requirement. If several qualify, the one with the highest pooled profit factor after
fees is taken forward, frozen. If none qualifies, Signal D is killed, later stages are
not run, and this document records the negative result.

**Decision rule.** The default configuration changes only if Signal D passes stages
1 to 4. Nothing here authorises paper or live trading.

## Results

The specification, variants and criteria above were committed as `e3b0f90` (study
script `c70f7c2`) before these runs. Each variant was run once.

### Stage 1 — discovery, 2023-01-01 → 2024-07-01 (18 months)

| Run | Round-trips | Per 90 days | Profit factor | Max DD (% budget) | Net USDT | Win rate | Expectancy (R) | PF before fees | Fees (R per trade) |
|---|---|---|---|---|---|---|---|---|---|
| L = 1 h | 1025 | 169 | 0.70 | 82.3 | -788.2 | 35 % | -0.15 | 0.92 | 0.12 |
| L = 4 h | 846 | 139 | 0.73 | 61.2 | -577.4 | 35 % | -0.14 | 0.96 | 0.12 |
| L = 12 h | 749 | 123 | 0.78 | 45.3 | -417.8 | 37 % | -0.11 | 1.02 | 0.12 |

| Stage-1 requirement | L = 1 h | L = 4 h | L = 12 h |
|---|---|---|---|
| PF after fees ≥ 1.4 | no (0.70) | no (0.73) | no (0.78) |
| Profitable in at least 4 of 6 quarters | no (0 of 6) | no (0 of 6) | no (1 of 6) |
| Profitable on at least 3 of 4 contracts | no (0) | no (0) | no (1) |
| No quarter above half of net profit | not applicable, net is negative | not applicable | not applicable |
| **Qualifies** | **no** | **no** | **no** |

Net USDT by quarter (2023 Q1 → 2024 Q2):

* L = 1 h: -76 / -122 / -128 / -190 / -50 / -222
* L = 4 h: -62 / -84 / -89 / -155 / -40 / -147
* L = 12 h: -39 / -23 / -53 / -124 / +5 / -184

Net USDT by contract:

* L = 1 h: BTC -433 (507 trades), ETH -327 (498 trades), SOL -15 (13 trades), XRP -13 (7 trades)
* L = 4 h: BTC -331 (419 trades), ETH -232 (413 trades), SOL -0 (8 trades), XRP -13 (6 trades)
* L = 12 h: BTC -239 (362 trades), ETH -176 (375 trades), SOL +10 (7 trades), XRP -12 (5 trades)

**Verdict: no variant qualifies. Signal D is killed at stage 1.** Per the selection
rule, validation, the final test and the recent check were not run, and no further
variant will be tried.

### Reading

* **There is no persistence to harvest.** Before fees the profit factor is 0.92,
  0.96 and 1.02. The trades that simply ran to the 180-minute time stop, which is the
  purest measure of follow-through, averaged about zero before fees (+0.04, −0.01 and
  0.00 USDT per trade). A strong hour that agrees with the recent trend told us
  nothing about the next three hours.
* **Costs then decide it.** With a stop one hourly ATR away (median 0.66–0.67 % of
  price), fees are about 0.12 R per trade, as planned. On no edge, that gives
  −0.11 to −0.15 R per trade.
* **It is consistent.** Every quarter loses for L = 1 and L = 4; one quarter of six is
  marginally positive for L = 12. BTC and ETH, with 360 to 510 trades each, lose under
  every variant. This is not a borderline miss.
* **Trade count was not the issue**: 123 to 169 round-trips per 90 days against the
  60 required.
* **Drawdown** over the 18 months was 45 % to 82 % of the 1,000 USDT budget.

### A limitation noticed before the runs, and why it does not change the verdict

In 2023, SOL and XRP averaged about 58M and 77M USDT of daily volume on Bitget, below
the playbook's 200M volume gate, so they traded only 5 to 13 times each in discovery.
The "3 of 4 contracts" requirement could therefore not have been met in a meaningful
way in this period. It did not matter: the two contracts that did trade lose clearly,
and the other requirements fail on their own. For any future discovery on this period
the per-contract requirement should be restated by the owner.

### Checks

* The default configuration replays identically with the Signal D code present, on
  all three 2026 windows.
* The download has no gaps (138,213 bars per contract) and its 2026 portion is
  identical to the data used for v0.9 and v0.10.
* All 846 entries of the L = 4 run were re-derived from raw hourly bars: every one
  satisfies the trigger and trend conditions and falls at 08:00, 09:00 or 16:00 UTC.
  For 12 of them (SOL and XRP) the stop differs from the hand calculation by less
  than one tick, because historical prices carry more decimals than today's tick.

## Conclusion

* Signal D is not adopted. `enable_signal_d` stays `false`; the default configuration
  is the v0.5 behaviour. Nothing is cleared for paper or live trading.
* Three mechanisms have now been tested against costs: a volume-spike breakout, a
  session opening-range breakout and hourly trend persistence. None shows an edge.
  The null hypothesis in the premise review stands: under the current constraints
  (0.02 % / 0.06 % fees, flat by midnight, 180-minute time stop, four contracts)
  there is no demonstrated intraday directional edge on public price data.
* Recommendation: stop directional signal work under these constraints. The remaining
  routes are the owner's policy calls recorded in the premise review: changing a
  constraint, or admitting a data source for the liquidation and funding premises.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install nautilus_trader==1.231.0 pandas pyyaml
.venv/bin/python research/fetch_data.py --start 2022-12-01T00:00 --end 2026-11-09T17:15
.venv/bin/python research/study_signal_d.py discovery
```
