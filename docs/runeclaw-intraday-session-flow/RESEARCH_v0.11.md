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

Pending.
