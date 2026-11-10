# Premise review — before any new signal (2026-11-10)

Status: for the owner's decision. No new signal is started by this document. The
default configuration is unchanged (v0.5 behaviour) and nothing is cleared for paper
or live trading.

## 1. What the evidence says

| Tested | Result after costs | What it showed |
|---|---|---|
| Signal A, VWAP reversion | Removing it lifted in-sample PF 0.83 → 1.03 | The losing engine of v0.1–v0.3 |
| Signal B, volume-spike breakout | PF 1.09 / 0.79 / 0.89 on three 90-day windows | Earns before fees (PF 1.57 / 1.14 / 1.27), fees take it all |
| Five changes to Signal B (time stop, target, volume, entry price, minimum stop) | None passed outside the in-sample window | Tuning fitted one period |
| Signal C, opening-range breakout | PF 0.70 / 0.65 / 0.83 | Fees halved, but no edge before fees (PF ≈ 1.0) |

Pooled over nine months and four contracts: Signal B made +273 USDT before fees on
362 trades and paid 368 USDT in fees. Signal C made +40 USDT before fees on 749
trades and paid 410 USDT.

## 2. The hurdle any intraday idea must clear

Round-trip fees are 0.04 % of notional (maker both sides) to 0.08 % (maker in, taker
out). Against the median price range of one bar:

| Contract | 15 min | 1 hour | 4 hours | 1 day |
|---|---|---|---|---|
| BTCUSDT | 0.23 % | 0.48 % | 1.04 % | 2.79 % |
| ETHUSDT | 0.30 % | 0.64 % | 1.37 % | 3.81 % |
| SOLUSDT | 0.36 % | 0.76 % | 1.57 % | 4.33 % |
| XRPUSDT | 0.33 % | 0.69 % | 1.43 % | 4.01 % |

* A trade sized on a 15-minute move pays a quarter to a third of that move in fees.
  The same fees are about 6 % of a 4-hour move.
* At Signal B's cost level, a before-fee profit factor of 1.57 became 1.09. Reaching
  the 1.3 bar after fees would have needed about 1.85 before fees. Nothing tested
  came close outside its fitting window.
* The playbook's own rules also cost money: pooled, the funding-flatten and time-stop
  exits lost 209 USDT for Signal B and 448 USDT for Signal C.

**Implication:** an idea is only worth testing if its expected move per trade is
several times 0.08 % of price and it does not rely on being cut by the clock.

## 3. What edge could we actually expect, and who pays for it

| Premise | Who would pay us | Data needed | Testable now (public, no key) | Prior |
|---|---|---|---|---|
| A. Hourly trend persistence: hold for hours with a wide stop | Traders forced to chase or cover a move | 15m candles | Yes | Low to moderate. Signal B's before-fee profit on all three windows is the only supporting evidence, and it is small |
| B. Reversal after forced liquidations | Liquidated leveraged traders | Liquidation and open-interest history | No. Not in public candle data | Plausible mechanism, cannot be tested cleanly under current rules |
| C. Funding carry or funding extremes | Leveraged crowd paying funding | Funding history beyond 90 days | No. Bitget's public history stops at about 90 days | Not viable intraday: one settlement pays about 0.01 %, a round trip costs up to 0.08 % |
| D. Relative strength between contracts, market-neutral | Laggard holders | 15m candles for a wider universe | Partly. Only 4 to 7 contracts pass the liquidity rule, and costs double | Low |
| E. Null: no exploitable edge for a taker-fee strategy that is flat by midnight on these four contracts | n/a | n/a | n/a | Leading hypothesis after two failed mechanisms |

My recommendation: treat E as the working assumption. Give premise A one clean test
under the rules below. If it fails, stop the programme or change a constraint rather
than try a further signal.

Constraints that cap any edge and are the owner's to change, not mine: the fee tier
(0.02 % / 0.06 %), flat by midnight UTC, the 180-minute time stop, and the
four-contract universe.

## 4. On which data

* **Source.** Public Bitget 15m candles, no key. Probed back to December 2020 for BTC
  and XRP. The download used so far had no gaps: 26,469 bars for each of four
  contracts.
* **Used up.** February to November 2026 has been examined for two breakout signals.
  It can serve as a recent-period check only, not as an untouched test.
* **Proposed split for a new premise.**

  | Role | Period | Use |
  |---|---|---|
  | Discovery | 2023-01 → 2024-06 | Shape the idea; limited iteration |
  | Validation | 2024-07 → 2025-06 | One run of the frozen specification |
  | Final test | 2025-07 → 2026-01 | One run, never repeated |
  | Recent check | 2026-02 → 2026-11 | Already seen; confirmation only |

* **Funding rule.** Funding history is public for about 90 days only, so older
  windows cannot apply the direction-aware rule. Measured on the one window where
  both are possible, the fallback (flatten before every settlement) lowers Signal B's
  PF from 1.09 to 0.94 and leaves Signal C unchanged (0.70 vs 0.71). The older-window
  results for Signal B are therefore understated by roughly that much; the verdicts
  do not change. From now on every window is evaluated in the fallback mode, so all
  windows are treated alike and the result is conservative.
* **Costs.** Maker 0.02 %, taker 0.06 %, as before, plus a stress run at 1.5× fees.
* **Engine.** The local replay in `research/`, which reproduces the sandbox closely
  in-sample.

## 5. Kill criteria (fixed before any work starts)

| Stage | Requirement | If not met |
|---|---|---|
| 0. Before code | One paragraph naming who pays and why it persists; one written specification; at least 60 round-trips expected per 90 days | Do not test |
| 1. Discovery | PF after fees ≥ 1.4 pooled; profitable in at least 4 of 6 quarters and on at least 3 of 4 contracts; no single quarter above half of net profit; at most 3 variants, declared up front | Kill |
| 2. Validation | One run: ≥ 60 round-trips per 90 days, PF ≥ 1.3, max drawdown < 6 % of budget, and PF ≥ 1.1 at 1.5× fees | Kill. No variants |
| 3. Final test | One run, same bar | Kill. No variants |
| 4. Recent check | PF ≥ 1.0 after fees on each of the three 2026 windows | Kill |
| 5. Paper | Only after stages 1 to 4. At least 60 round-trips or 8 weeks. Kill if PF < 1.0, drawdown ≥ 6 %, or realised costs exceed modelled costs by more than half | Kill |

Programme-level rules:

* A change to a frozen specification after stage 1 counts as a new premise.
* At most two further premises. If both are killed, conclude the null hypothesis and
  stop, or reopen the constraints in section 3.
* The default configuration changes only for an idea that has passed stages 1 to 4.
* Negative results are documented and kept, as with PR #10.

## 6. Decisions needed from the owner

1. Accept the null as the working assumption, with premise A as the one test to run?
2. Accept the data split and the kill criteria as written?
3. Are any constraints in section 3 open for change (fee tier, flat by midnight, time
   stop, universe)?
4. For premises B and C: is a keyed or third-party data source acceptable later? Under
   the current no-key rule they cannot be tested.
