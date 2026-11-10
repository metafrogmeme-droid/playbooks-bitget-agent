# Parameter table — RUNECLAW Intraday Session Flow v0.6

Generated from `src/params.py` by `tools/gen_params_table.py`; defaults are
identical in `manifest.yaml -> strategy_config`. *Tunable* marks the fields a
subscriber may override (`user_config_schema`); every other field changes only
through a new version (one variable per version).

| Parameter | Default | Allowed range | Unit | Tunable | Meaning |
|---|---|---|---|---|---|
| `trading_symbols` | BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT | subset of {BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, SOXLUSDT, SNDKUSDT, KORUUSDT}, 1–7 items | - | yes | Universe: contracts passing the liquidity scan; crypto on by default, RWA opt-in |
| `margin_budget` | 1,000 | 100 – 100000 | USDT | yes | Risk denominator and platform return basis; margin cap = budget × leverage |
| `leverage` | 3 | 1 – 10 | x | yes | Only changes margin usage; risk per trade is fixed by risk_pct_per_trade |
| `risk_pct_per_trade` | 0.5 | 0.1 – 1.0 | % of budget | yes | Loss between entry and initial stop per trade |
| `min_24h_notional_usdt` | 200,000,000 | 50e6 – 1e9 | USDT | no | Exclude symbol when 24h quote volume is below this (live: ticker; replay: 96-bar notional) |
| `max_spread_bps` | 3.0 | 1 – 10 | bps | no | Exclude symbol when (ask-bid)/mid exceeds this (live only) |
| `regime_atr_period` | 14 | 7 – 28 | 4H bars | no | Wilder ATR period for the regime filter |
| `regime_atr_pct_min` | 0.6 | 0.3 – 1.0 | % | no | Below = chop, no trades |
| `regime_atr_pct_max` | 3.0 | 2.0 – 5.0 | % | no | Above = event risk, no trades |
| `bias_ema_period` | 20 | 10 – 50 | 1H bars | no | EMA whose slope defines the 1H bias |
| `bias_flat_slope_pct` | 0.05 | 0.01 – 0.20 | % | no | abs(slope) below this counts as flat |
| `session_windows` | 07:00-10:00, 13:30-16:30 | list of HH:MM-HH:MM UTC, 1–3 windows | UTC | no | Entry windows; start inclusive, end exclusive |
| `enable_signal_a` | False | true / false | - | no | VWAP reversion on/off (off in v0.4 to isolate Signal B) |
| `vwap_anchor` | utc_day | utc_day | - | no | Session VWAP reset point (only utc_day implemented in v0.1) |
| `vwap_trigger_sigma` | 1.5 | 1.0 – 3.0 | σ | no | Distance from VWAP that arms Signal A |
| `vwap_limit_sigma` | 1.0 | 0.5 – trigger | σ | no | Entry limit band (worst acceptable entry) |
| `vwap_stop_sigma` | 2.0 | trigger – 3.5 | σ | no | Initial stop band for Signal A |
| `rsi_period` | 14 | 7 – 21 | 15m bars | no | RSI period |
| `rsi_overbought` | 70.0 | 60 – 85 | RSI | no | Short-side exhaustion threshold |
| `rsi_oversold` | 30.0 | 15 – 40 | RSI | no | Long-side exhaustion threshold |
| `signal_a_expiry_minutes` | 45 | 15 – 90 | min | no | Resting time of a Signal A limit order |
| `enable_signal_b` | True | true / false | - | no | Volume-spike breakout on/off |
| `volume_spike_mult` | 3.0 | 1.5 – 5.0 | × median | no | Bar volume vs median of previous bars |
| `volume_median_bars` | 20 | 10 – 50 | 15m bars | no | Median window (current bar excluded) |
| `breakout_lookback_bars` | 20 | 10 – 50 | 15m bars | no | Prior high/low window (current bar excluded) |
| `signal_b_expiry_minutes` | 30 | 15 – 60 | min | no | Resting time of a Signal B limit order |
| `signal_b_target_r` | 1.5 | 1.0 – 4.0 | R | no | Breakout target as multiple of initial risk |
| `signal_b_trail_r` | 1.0 | 0.5 – 2.0 | R | no | Trail distance once trade is that many R in profit |
| `funding_hours_utc` | 0, 8, 16 | subset of {0, 8, 16} | hour UTC | no | Bitget 8-hour funding settlement times |
| `funding_flatten_lead_minutes` | 10 | 5 – 30 | min | no | Flatten lead before funding; effective lead = max(lead, 15) at 15m cadence |
| `funding_direction_aware` | True | true / false | - | no | Live: flatten only when the position pays funding (replay: always flatten) |
| `max_concurrent_positions` | 2 | 1 – 3 | positions | yes | Open positions + resting entries across all symbols |
| `max_trades_per_day_symbol` | 3 | 1 – 6 | trades | no | Filled entries per symbol per UTC day |
| `daily_loss_cap_pct` | 1.5 | 0.5 – 3.0 | % of budget | yes | Realised loss that halts trading until next UTC day |
| `daily_cap_flatten` | True | true / false | - | no | Also flatten open positions when the cap is hit |
| `time_stop_minutes` | 180 | 30 – 240 | min | no | Close trades that have not reached target in time |
| `eod_flatten_time` | 23:45 | 23:00 – 23:45 | HH:MM UTC | no | Hard end-of-day flatten time |
| `reconcile_interval_minutes` | 5 | 5 – 15 | min | no | Requested reconciliation cadence (scheduler floor is 15 min) |
| `halt_on_reconcile_mismatch` | True | true / false | - | no | Block new entries while a position/fill mismatch is flagged |
| `backtest_days` | 90 | 30 – 180 | days | yes | Replay window length |
| `warmup_days` | 5 | 3 – 10 | days | no | Extra history fetched for indicator warm-up (excluded from the replay window) |
| `max_backtest_symbols` | 4 | 1 – 7 | symbols | yes | Symbols replayed per sandbox run (180 s budget); the rest are reported as skipped |
| `backtest_end_utc` | 2026-11-09T17:15:00+00:00 | ISO-8601 UTC or empty (= now) | timestamp | no | Pinned evaluation end so versions replay identical bars; move only with a new baseline |

## Derived values (not configurable)

| Name | Formula | v0.1 value |
|---|---|---|
| risk per trade | margin_budget × risk_pct_per_trade / 100 | 5 USDT |
| daily loss cap | margin_budget × daily_loss_cap_pct / 100 | 15 USDT |
| max notional per position | margin_budget × leverage | 3000 USDT |
| effective funding lead | max(funding_flatten_lead_minutes, 15) | 15 min |
| decision cadence | 15m bars / `*/15 * * * *` schedule | 15 min |

## Pre-registered pass criteria (fixed for v0.x)

| Criterion | Threshold | Verdict if not met |
|---|---|---|
| Round-trips | ≥ 60 | PENDING |
| Profit factor | ≥ 1.3 | FAIL |
| Max drawdown (% of margin budget) | < 6 % | FAIL |
