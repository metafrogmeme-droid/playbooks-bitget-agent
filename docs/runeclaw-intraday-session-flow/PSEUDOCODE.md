# RUNECLAW Intraday Session Flow — rule pseudo-code (v0.2)

All times UTC. `now` is the close time of the last completed 15-minute bar
(replay) or the wall clock at the scheduled run (live, every 15 minutes).
Code references point at `playbooks/runeclaw-intraday-session-flow/src/`.

## 0. Run skeleton

```
LIVE RUN (main_live.run, every 15 min):
    params  = PlaybookParams.from_config(manifest.strategy_config)
    state   = load .state/runeclaw/state.json          # pending, open, ledger, flags
    ledger.roll(now)                                   # new UTC day → reset counters & halt
    RECONCILE(state, exchange positions, exchange pending orders)   # §9
    for symbol in params.trading_symbols:
        bars     = last 600 closed 15m bars (exchange=bitget); refuse if newest bar older than 30 min
        feats    = compute_features(bars)              # §1
        ticker   = 24h quote volume, best bid/ask → spread_bps
        funding  = latest funding rate (only needed when a position is open)
        decision = DECIDE(symbol, feats, ticker, funding, state, ledger)   # §2–§8
        emit_signal_or_follow(decision, execute_trade = execution.execute(decision))
    save state, write decisions.json / orders_log.json

REPLAY (main_backtest.run):
    for symbol (up to max_backtest_symbols): fetch [now-95d, now) raw 15m bars in 1000-bar pages
    inject manifest.strategy_config into the Nautilus strategy config
    backtest.run(); strategy.py feeds each bar to features.IncrementalFeatures (same formulas
    as §1, unit-tested equal to compute_features) and applies §2–§8 bar by bar
    write backtest_report.json, equity_curve.csv, evaluation.json (§10), emit watch signal
```

## 0b. Universe

```
candidates = manifest.trading_symbols   # from the liquidity scan in UNIVERSE.md
LIVE, every run: drop a candidate when 24h quote volume < min_24h_notional_usdt or spread > max_spread_bps
REPLAY: drop when the rolling 96-bar notional proxy < min_24h_notional_usdt (no L1 history)
```

## 1. Features (features.compute_features / features.IncrementalFeatures) — causal, per 15m bar

```
tp              = (high + low + close) / 3
vwap_session    = Σ(tp·vol) / Σ(vol)        cumulative since 00:00 UTC
vwap_sigma      = sqrt( Σ(tp²·vol)/Σ(vol) − vwap_session² )
rsi             = Wilder RSI(rsi_period) on 15m closes
bias_slope_pct  = pct change of EMA(bias_ema_period) on COMPLETED 1H closes
atr4h_pct       = Wilder ATR(regime_atr_period) / close ·100 on COMPLETED 4H bars
vol_median_prev = median(volume of previous volume_median_bars bars)       # current bar excluded
prior_high/low  = max/min(high/low of previous breakout_lookback_bars bars) # current bar excluded
notional_24h    = Σ(close·volume) over last 96 bars                        # replay proxy for 24h volume
```
Higher-timeframe values are mapped to a 15m bar only when the HTF bar's close
time ≤ the 15m bar's close time (no look-ahead).

## 2. Regime filter (features.regime_ok)

```
if atr4h_pct is NaN:                        → NO TRADE ("regime_unavailable")
if atr4h_pct < regime_atr_pct_min (0.6):    → NO TRADE ("regime_chop")
if atr4h_pct > regime_atr_pct_max (3.0):    → NO TRADE ("regime_event_risk")
else                                        → regime ok
```

## 3. Bias (features.bias_state)

```
slope = bias_slope_pct
if |slope| < bias_flat_slope_pct (0.05): bias = "flat"
elif slope > 0:                          bias = "up"
else:                                    bias = "down"
```

## 4. Entry gates (risk.can_open_new), evaluated in this order

```
ledger.halted (daily cap)                         → "halted:daily_loss_cap"
reconcile flags present and halt_on_mismatch      → "halted:reconcile_mismatch"
now not in any session window                     → "outside_session"
symbol already has a position or resting entry    → "symbol_already_exposed"
open_positions + pending_entries ≥ max_concurrent → "max_concurrent"
trades today for symbol ≥ max_trades_per_day      → "max_trades_per_day_symbol"
minutes_to_next_funding ≤ max(lead, 15)           → "pre_funding_window"
now ≥ eod_flatten_time                            → "eod"
24h notional < min_24h_notional_usdt              → "volume_below_min"     (live: ticker; replay: notional_24h)
spread_bps > max_spread_bps                       → "spread_above_max"     (live only)
```

## 5. Signal A — VWAP reversion (features.detect_signals)

```
upper = vwap + vwap_trigger_sigma·σ ;  lower = vwap − vwap_trigger_sigma·σ
SHORT if close ≥ upper and rsi > rsi_overbought and bias ∈ {flat, down}:
    limit  = vwap + vwap_limit_sigma·σ        # never enter closer to VWAP than 1.0σ
    stop   = vwap + vwap_stop_sigma·σ         # frozen at signal time
    target = vwap                              # re-pinned to live VWAP every bar
    expiry = signal_a_expiry_minutes (45)
LONG  mirrored: close ≤ lower and rsi < rsi_oversold and bias ∈ {flat, up}
R = |limit − stop|
```
Note: when price is already beyond the trigger band, the limit at the 1.0σ
band is marketable and fills at the better available price; if price has
already reverted past 1.0σ the order rests and may expire unfilled.

## 6. Signal B — volume-spike breakout (features.detect_signals)

```
spike = volume ≥ volume_spike_mult (2.5) · vol_median_prev
mid   = (high + low) / 2
LONG  if spike and close > prior_high and bias == "up":
    limit = mid ; stop = low  ; R = mid − low ; target = mid + signal_b_target_r·R ; expiry = 30 min
SHORT if spike and close < prior_low  and bias == "down":
    limit = mid ; stop = high ; R = high − mid ; target = mid − signal_b_target_r·R ; expiry = 30 min
```
If A and B fire on the same bar, B (trend) is taken.

## 7. Sizing (risk.size_from_risk) and order placement

```
risk_usdt = margin_budget · risk_pct_per_trade / 100           # 1000 · 0.5% = 5 USDT
qty       = risk_usdt / R
if qty·limit > margin_budget·leverage: qty = margin_budget·leverage / limit   # margin cap
qty       = floor(qty / size_step) · size_step ; reject if < min_qty
LIVE:  compute_qty(margin = qty·limit/leverage, price = limit) → exchange lot size
       prices quantized to contract_rules(symbol).price_step (buy limit rounds down, sell limit up)
       resolve_contract_tpsl(tp=target, sl=stop, reference=limit)
       open_{long|short}_limit(qty, price=limit, leverage, tp_trigger_price, sl_trigger_price)
       journal: entry_placed, stop_set, target_set   (signal_id, timestamp, limit, stop, target, qty)
REPLAY: GTD limit order expiring at now + expiry; on fill → reduce-only stop-market + reduce-only limit TP
```

## 8. Position management (every decision point)

```
for each open trade (checked in this order):
    now ≥ eod_flatten_time (23:45)                               → FLATTEN "eod_flatten"
    ledger.halted and daily_cap_flatten                          → FLATTEN "daily_loss_cap"
    minutes_to_next_funding ≤ max(funding_lead, 15):
        LIVE:   pays = (side==long and rate>0) or (side==short and rate<0)
                if pays or rate unknown                          → FLATTEN "funding_window[_rate_unknown]"
        REPLAY: always                                           → FLATTEN "funding_window"  (no funding history in v0.1)
    open for ≥ time_stop_minutes (120)                           → FLATTEN "time_stop"
    otherwise:
        kind A: target ← current vwap_session (modify TP plan order)
        kind B: best ← max(best, high) [long] / min(best, low) [short]
                if best − entry ≥ trail_r·R: new_stop = best − trail_r·R (long; mirrored short)
                if new_stop better than current stop → modify SL plan order
for each resting entry: if now ≥ expires_at → CANCEL (journal entry_cancelled, reason expiry)

FLATTEN(symbol, reason):
    cancel resting orders for symbol; read live position (PRE-CHECK)
    close_position(symbol, hold_side)   # reduce-only full close (EXECUTE)
    re-read position, record post-check; journal "exit" with reason and pnl estimate
```

## 9. Reconciliation (journal.reconcile) — every run (requested 5 min; scheduler floor 15 min)

```
live_pending = ids of exchange pending orders ; positions = exchange positions
for symbol in state.pending:
    if order id still in live_pending: keep
    elif a position on the same side exists: entry FILLED → fill price from fills(order_id) → state.open, ledger.record_entry
    else: entry EXPIRED/cancelled externally → journal entry_expired
for symbol in state.open:
    if position still exists: sync size
    else: exchange closed it → fill price from fills() → reason = nearer of stop/target → journal exit, ledger.record_pnl
exchange position with no journal entry       → FLAG untracked_position
journal pending id missing on exchange        → FLAG pending_mismatch
any FLAG → no new entries (halt_on_reconcile_mismatch), exits still run
```

## 10. Pre-registered evaluation (main_backtest.evaluate)

```
round_trips  = closed positions in the replay window
profit_factor = gross_profit / gross_loss
dd_pct        = max peak-to-trough of real equity points / margin_budget · 100
if round_trips < 60:                       verdict = PENDING
elif pf or dd not measurable:              verdict = PENDING
elif pf ≥ 1.3 and dd_pct < 6.0:            verdict = PASS
else:                                      verdict = FAIL
```
