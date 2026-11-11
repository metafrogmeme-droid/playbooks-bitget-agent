# RUNECLAW Intraday Session Flow (v0.11)

> **Status: research concluded, not for trading.** No tested configuration passes the
> evaluation bar after costs. The default below is kept as a reference only. See
> `docs/runeclaw-intraday-session-flow/CONCLUSION.md` in the repository.

Day-trading Playbook for the most liquid Bitget USDT-M perpetuals. The universe
is every contract that passed the liquidity scan (24h volume ≥ 200M USDT,
spread ≤ 3 bps): BTCUSDT, ETHUSDT, SOLUSDT and XRPUSDT by default, with the
three RWA stock-token perpetuals that also passed (SOXLUSDT, SNDKUSDT, KORUUSDT)
available as opt-in symbols.
Every position is flat before 00:00 UTC. Two signals, one regime filter, two
session windows, hard risk limits, and a full order journal with reconciliation.

Full specification, parameter table, pseudo-code and versioning policy live in
`docs/runeclaw-intraday-session-flow/` at the repository root.

## 策略 / Strategy

The Playbook trades the two most reliable intraday behaviours of liquid crypto
perpetuals during the European open (07:00–10:00 UTC) and the US open
(13:30–16:30 UTC): over-extension away from the session VWAP that mean-reverts,
and volume-backed range breakouts that continue. 15-minute bars drive
execution, the 1-hour EMA slope sets directional bias, and a 4-hour ATR
regime filter decides whether the market is tradable at all (too quiet is chop,
too wild is event risk; both are skipped).

## 开仓 / Entry

* **Signal A, VWAP reversion (counter-trend) — disabled in v0.4** (kept in the
  code, `enable_signal_a: false`) to measure Signal B on its own. When enabled: when price is at least 1.5
  standard deviations from the session VWAP and RSI(14) is overbought (short)
  or oversold (long), and the 1H bias is flat or on the trade's side, a limit
  order is placed at the 1.0σ band and expires after 45 minutes.
* **Signal B, volume-spike breakout (trend).** When a bar prints at least 2.5×
  the 20-bar median volume, closes beyond the prior 20-bar high/low, and the 1H
  bias points the same way, a limit order is placed at the breakout bar's
  midpoint and expires after 30 minutes. Entering at the bar's close is
  available as `signal_b_entry_mode: close`; it was tested as v0.8.0 and failed
  both evaluation windows, so it is not the default.

Position size risks 0.5 % of the margin budget between entry and stop. At most
two positions are open at once and at most three trades per symbol per day.
Entries are refused outside the session windows, in the pre-funding window,
when 24h volume is below 200M USDT, or when the spread exceeds 3 bps, so a
symbol that loses liquidity drops out of the universe automatically.

## 平仓 / Exit

All exits are reduce-only: position-bound TP/SL plan orders or a full
close-position call.

* Signal A: stop at the 2.0σ band, target at the session VWAP (re-pinned to the
  live VWAP every bar).
* Signal B: stop at the breakout bar's opposite extreme, target at 2R, stop
  trailed 1R behind the best price once the trade is 1R in profit.
* Time stop: any trade open longer than 180 minutes without reaching its target
  is closed (120 minutes in v0.1–v0.4).
* Funding rule: 10 minutes before the 00:00 / 08:00 / 16:00 UTC settlements
  (effectively the last 15-minute decision point) a position that would pay
  funding is flattened; re-entry only on a fresh signal.
* End of day: everything is flat by 23:45 UTC.
* Daily loss cap: once realised losses reach 1.5 % of the margin budget, open
  positions are flattened and no new trades are taken until the next UTC day.

## Parameters

Subscribers may tune: trading symbols, margin budget, leverage, risk per trade,
daily loss cap, maximum concurrent positions, the backtest window and the
number of symbols replayed per backtest run. Signal
parameters are fixed per version; one variable changes per version.

## How To Read Backtest Metrics

`total_return_pct` and `max_drawdown_pct` are expressed on the margin-budget
basis; account-level numbers are kept under `account_*`. The replay also writes
`evaluation.json` with the pre-registered verdict: PASS requires at least 60
round-trips, profit factor ≥ 1.3 and max drawdown < 6 % of budget. Fewer than 60
round-trips is PENDING, never PASS. Trade-level detail is in
`trade_journal.json`; blocked-entry reasons are in `replay_stats.json`.

## 风险 / Risk

Counter-trend entries lose in sessions that keep trending; breakout entries lose
in fake-outs around macro releases that fall inside the US window. Resting limit
orders can miss fills in thin liquidity, leaving the strategy flat while the
move happens. The spread gate is live-only (no historical L1 data), and the
direction-aware funding rule in replay depends on historical funding-rate
coverage; where it is missing the replay flattens before every settlement and
reports that degradation, so live behaviour can differ slightly from replay. Past performance is not a guarantee of future
results; do not run this with leverage or budget you cannot afford to lose.
