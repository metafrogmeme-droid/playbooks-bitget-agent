"""NautilusTrader replay strategy for RUNECLAW Intraday Session Flow.

Rule logic is NOT re-implemented here.  Features are computed bar by bar with
``features.IncrementalFeatures`` (unit-tested to equal the vectorized
``features.compute_features`` the live path uses) and this class applies the
identical gates (``features.regime_ok``, ``risk.can_open_new``,
``features.detect_signals``, ``risk.size_from_risk``, ``risk.trail_stop`` ...).
The strategy therefore needs nothing but raw OHLCV bars, which is what the
platform's own evidence replay supplies.

Replay-specific simplifications (documented in docs/PSEUDOCODE.md):
* spread gate is live-only (no L1 history); the 24h volume gate uses the
  rolling 15m notional proxy ``notional_24h``
* funding rule is direction-agnostic in replay (flatten before every funding
  time) because historical funding is not injected in v0.1
* limit entries are GTD orders; stop = reduce-only stop-market, target =
  reduce-only limit; time-stop / funding / EOD exits use close_position
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from . import features, risk
from .params import PlaybookParams, signal_id

BAR_NS = 15 * 60 * 1_000_000_000
OUTPUT_DIR = Path("output")  # package-relative


class RuneclawSessionFlowConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[str, ...] = ()
    bar_types: tuple[str, ...] = ()
    strategy_params: Optional[dict] = None   # copy of manifest.strategy_config (injected by main_backtest)


class RuneclawSessionFlow(Strategy):
    def __init__(self, config: RuneclawSessionFlowConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self.params = PlaybookParams.from_config(config.strategy_params or {})
        self._features: dict[str, features.IncrementalFeatures] = {}
        self._instruments: dict[str, Instrument] = {}
        self._iid_by_symbol: dict[str, InstrumentId] = {}
        self.ledger = risk.DailyLedger()
        self.pending: dict[str, dict[str, Any]] = {}
        self.open: dict[str, dict[str, Any]] = {}
        self.journal: list[dict[str, Any]] = []
        self._closing_reason: dict[str, str] = {}
        self._last_fill_px: dict[str, float] = {}
        self.stats: dict[str, Any] = {
            "round_trips": 0, "wins": 0, "losses": 0, "gross_profit": 0.0, "gross_loss": 0.0,
            "exit_reasons": {}, "entries_placed": 0, "entries_expired": 0, "gate_blocks": {},
        }

    # ------------------------------------------------------------------ wiring
    def _feature_row(self, iid: InstrumentId, bar: Bar) -> tuple[dict[str, Any], int]:
        """Update the per-instrument incremental features with this closed bar.
        Nautilus EXTERNAL bars built from open-time-indexed frames carry the
        bar OPEN time in ts_event."""
        key = iid.value
        engine = self._features.get(key)
        if engine is None:
            engine = self._features[key] = features.IncrementalFeatures(self.params)
        open_ns = int(bar.ts_event)
        open_ts = unix_nanos_to_dt(open_ns).to_pydatetime()
        row = engine.update(open_ts, float(bar.open), float(bar.high), float(bar.low), float(bar.close), float(bar.volume))
        return row, open_ns

    def on_start(self) -> None:
        ids: list[InstrumentId] = []
        for raw in self.cfg.instrument_ids or ():
            ids.append(raw if isinstance(raw, InstrumentId) else InstrumentId.from_str(str(raw)))
        if not ids and self.cfg.instrument_id is not None:
            ids.append(self.cfg.instrument_id)
        if not ids:
            ids = [inst.id for inst in self.cache.instruments()]
        bar_types: list[BarType] = []
        for raw in self.cfg.bar_types or ():
            bar_types.append(raw if isinstance(raw, BarType) else BarType.from_str(str(raw)))
        if not bar_types and self.cfg.bar_type is not None:
            bar_types.append(self.cfg.bar_type)
        if not bar_types:
            bar_types = [BarType.from_str(f"{iid.value}-15-MINUTE-LAST-EXTERNAL") for iid in ids]
        if not ids:
            raise RuntimeError("no instruments resolved for RuneclawSessionFlow")
        for iid in ids:
            instrument = self.cache.instrument(iid)
            if instrument is None:
                raise RuntimeError(f"instrument {iid} not in cache")
            self._instruments[iid.value] = instrument
            self._iid_by_symbol[iid.symbol.value] = iid
        for bt in bar_types:
            self.subscribe_bars(bt)

    # ------------------------------------------------------------------ bars
    def on_bar(self, bar: Bar) -> None:
        iid = bar.bar_type.instrument_id
        symbol = iid.symbol.value
        row, open_ns = self._feature_row(iid, bar)
        now = unix_nanos_to_dt(open_ns + BAR_NS)   # decisions happen at bar close
        if self.ledger.roll(now):
            pass
        self._manage_pending(symbol, now)
        if symbol in self.open:
            self._manage_open(symbol, iid, bar, row, now)
        elif symbol not in self.pending:
            self._maybe_enter(symbol, iid, bar, row, now)

    def _block(self, reason: str) -> None:
        self.stats["gate_blocks"][reason] = self.stats["gate_blocks"].get(reason, 0) + 1

    def _maybe_enter(self, symbol: str, iid: InstrumentId, bar: Bar, row: dict[str, Any], now) -> None:
        params = self.params
        ok, why = features.regime_ok(row, params)
        if not ok:
            self._block(why)
            return
        ok, why = risk.can_open_new(
            now, params, self.ledger, symbol,
            open_positions=len(self.open), pending_entries=len(self.pending),
            has_exposure_on_symbol=False, reconcile_flags=0,
            notional_24h=row.get("notional_24h"), spread_bps=None,
        )
        if not ok:
            self._block(why)
            return
        candidates = features.detect_signals(row, params)
        if not candidates:
            return
        cand = sorted(candidates, key=lambda c: 0 if c.kind == "B" else 1)[0]
        instrument = self._instruments[iid.value]
        size_step = float(instrument.size_increment)
        min_qty = float(instrument.min_quantity) if instrument.min_quantity is not None else size_step
        size = risk.size_from_risk(cand.limit_price, cand.stop_price, params, size_step=size_step, min_qty=min_qty)
        if not size.ok:
            self._block(f"sizing:{size.reason}")
            return
        side = OrderSide.BUY if cand.side == "long" else OrderSide.SELL
        expire_at = pd.Timestamp(now) + pd.Timedelta(minutes=cand.expiry_minutes)
        order = self.order_factory.limit(
            instrument_id=iid,
            order_side=side,
            quantity=instrument.make_qty(size.qty),
            price=instrument.make_price(cand.limit_price),
            time_in_force=TimeInForce.GTD,
            expire_time=expire_at,
        )
        sid = signal_id(symbol, cand.kind, pd.Timestamp(now) - pd.Timedelta(minutes=15))
        self.pending[symbol] = {
            "signal_id": sid, "kind": cand.kind, "side": cand.side, "client_order_id": order.client_order_id.value,
            "limit_price": float(order.price), "stop": cand.stop_price, "target": cand.target_price,
            "r_distance": cand.r_distance, "qty": size.qty, "placed_at": now, "expires_at": expire_at.to_pydatetime(),
        }
        self.submit_order(order)
        self.stats["entries_placed"] += 1
        self._log(sid, now, symbol, cand.side, "entry_placed", order.client_order_id.value, limit_price=float(order.price),
                  stop=cand.stop_price, target=cand.target_price, qty=size.qty,
                  note=f"kind={cand.kind} expires_at={expire_at.isoformat()} reasons={list(cand.reasons)}")

    def _manage_pending(self, symbol: str, now) -> None:
        pend = self.pending.get(symbol)
        if not pend:
            return
        if now < risk.to_utc(pend["expires_at"]):
            return
        order = self.cache.order(ClientOrderId(pend["client_order_id"]))
        if order is not None and order.is_open:
            self.cancel_order(order)
        # removal is finalized in on_order_canceled / on_order_expired

    def _manage_open(self, symbol: str, iid: InstrumentId, bar: Bar, row: dict[str, Any], now) -> None:
        params = self.params
        trade = self.open[symbol]
        reason = ""
        if risk.eod_flatten_due(now, params):
            reason = "eod_flatten"
        elif self.ledger.halted and params.daily_cap_flatten:
            reason = "daily_loss_cap"
        elif risk.funding_flatten_due(now, params):
            reason = "funding_window"        # direction-agnostic in replay (no funding history in v0.1)
        elif risk.time_stop_due(risk.to_utc(trade["opened_at"]), now, params):
            reason = "time_stop"
        if reason:
            self._flatten(symbol, iid, reason, now)
            return
        instrument = self._instruments[iid.value]
        if trade["kind"] == "A":
            vwap = row.get("vwap_session")
            if vwap is not None and vwap == vwap:
                new_target = instrument.make_price(float(vwap))
                tp = self.cache.order(ClientOrderId(trade["tp_coid"])) if trade.get("tp_coid") else None
                if tp is not None and tp.is_open and float(tp.price) != float(new_target):
                    self.modify_order(tp, price=new_target)
                    trade["target"] = float(new_target)
                    self._log(trade["signal_id"], now, symbol, trade["side"], "target_modified", tp.client_order_id.value,
                              target=float(new_target), note="Signal A target follows session VWAP")
        else:
            best = trade.get("best_excursion", trade["entry_price"])
            best = max(best, float(bar.high)) if trade["side"] == "long" else min(best, float(bar.low))
            trade["best_excursion"] = best
            new_stop = risk.trail_stop(trade["side"], trade["entry_price"], best, trade["stop"], trade["r_distance"], params)
            if new_stop is not None:
                sl = self.cache.order(ClientOrderId(trade["sl_coid"])) if trade.get("sl_coid") else None
                if sl is not None and sl.is_open:
                    trigger = instrument.make_price(new_stop)
                    if float(trigger) == float(sl.trigger_price):
                        trade["stop"] = float(trigger)   # quantized to the same tick; nothing to send
                        return
                    self.modify_order(sl, trigger_price=trigger)
                    trade["stop"] = float(trigger)
                    self._log(trade["signal_id"], now, symbol, trade["side"], "stop_modified", sl.client_order_id.value,
                              stop=float(trigger), note="Signal B trailing stop")

    def _flatten(self, symbol: str, iid: InstrumentId, reason: str, now) -> None:
        trade = self.open.get(symbol, {})
        self._closing_reason[symbol] = reason
        self.cancel_all_orders(iid)
        for position in self.cache.positions_open(instrument_id=iid):
            self.close_position(position)
        self._log(trade.get("signal_id", ""), now, symbol, trade.get("side", ""), "flatten_requested", "",
                  exit_reason=reason, note="cancel_all_orders + close_position (reduce-only)")

    # ------------------------------------------------------------------ events
    def on_order_filled(self, event) -> None:
        coid = event.client_order_id.value
        symbol = event.instrument_id.symbol.value
        px = float(event.last_px)
        self._last_fill_px[symbol] = px
        pend = self.pending.get(symbol)
        if pend and pend["client_order_id"] == coid:
            self._on_entry_fill(symbol, event.instrument_id, pend, px, event.ts_event)
            return
        trade = self.open.get(symbol)
        if trade:
            if coid == trade.get("sl_coid"):
                self._closing_reason.setdefault(symbol, "stop_hit")
            elif coid == trade.get("tp_coid"):
                self._closing_reason.setdefault(symbol, "target_hit")

    def _on_entry_fill(self, symbol: str, iid: InstrumentId, pend: dict[str, Any], px: float, ts_ns: int) -> None:
        now = unix_nanos_to_dt(ts_ns)
        instrument = self._instruments[iid.value]
        positions = self.cache.positions_open(instrument_id=iid)
        qty = positions[0].quantity if positions else instrument.make_qty(pend["qty"])
        trade = self.open.get(symbol)
        if trade is None:
            exit_side = OrderSide.SELL if pend["side"] == "long" else OrderSide.BUY
            sl = self.order_factory.stop_market(
                instrument_id=iid, order_side=exit_side, quantity=qty,
                trigger_price=instrument.make_price(pend["stop"]), reduce_only=True,
            )
            tp = self.order_factory.limit(
                instrument_id=iid, order_side=exit_side, quantity=qty,
                price=instrument.make_price(pend["target"]), time_in_force=TimeInForce.GTC, reduce_only=True,
            )
            self.submit_order(sl)
            self.submit_order(tp)
            self.open[symbol] = {
                "signal_id": pend["signal_id"], "kind": pend["kind"], "side": pend["side"], "entry_price": px,
                "qty": float(qty), "stop": float(pend["stop"]), "target": float(pend["target"]),
                "r_distance": float(pend["r_distance"]), "opened_at": now, "best_excursion": px,
                "sl_coid": sl.client_order_id.value, "tp_coid": tp.client_order_id.value,
                "entry_coid": pend["client_order_id"],
            }
            self.ledger.record_entry(symbol)
            self._log(pend["signal_id"], now, symbol, pend["side"], "entry_filled", pend["client_order_id"],
                      limit_price=pend["limit_price"], fill_price=px, stop=pend["stop"], target=pend["target"], qty=float(qty))
            self._log(pend["signal_id"], now, symbol, pend["side"], "stop_set", sl.client_order_id.value, stop=pend["stop"],
                      note="reduce-only stop-market")
            self._log(pend["signal_id"], now, symbol, pend["side"], "target_set", tp.client_order_id.value, target=pend["target"],
                      note="reduce-only limit")
        else:
            # partial fill continuation: resize protective orders to the live position
            for key in ("sl_coid", "tp_coid"):
                order = self.cache.order(ClientOrderId(trade[key]))
                if order is not None and order.is_open and float(order.quantity) != float(qty):
                    self.modify_order(order, quantity=qty)
            trade["qty"] = float(qty)
        entry = self.cache.order(ClientOrderId(pend["client_order_id"]))
        if entry is None or not entry.is_open:
            self.pending.pop(symbol, None)

    def _drop_pending(self, event, event_name: str) -> None:
        symbol = event.instrument_id.symbol.value
        pend = self.pending.get(symbol)
        if pend and pend["client_order_id"] == event.client_order_id.value:
            self.pending.pop(symbol, None)
            if symbol not in self.open:
                self.stats["entries_expired"] += 1
                self._log(pend["signal_id"], unix_nanos_to_dt(event.ts_event), symbol, pend["side"], "entry_expired",
                          pend["client_order_id"], limit_price=pend["limit_price"], exit_reason=event_name)

    def on_order_canceled(self, event) -> None:
        self._drop_pending(event, "canceled")

    def on_order_expired(self, event) -> None:
        self._drop_pending(event, "expired")

    def on_order_rejected(self, event) -> None:
        self._drop_pending(event, "rejected")

    def on_order_denied(self, event) -> None:
        self._drop_pending(event, "denied")

    def on_position_closed(self, event) -> None:
        symbol = event.instrument_id.symbol.value
        trade = self.open.pop(symbol, None)
        reason = self._closing_reason.pop(symbol, "unknown")
        pnl_obj = event.realized_pnl
        try:
            pnl = float(pnl_obj.as_double()) if hasattr(pnl_obj, "as_double") else float(pnl_obj)
        except (TypeError, ValueError):
            pnl = 0.0
        self.ledger.record_pnl(pnl, self.params)
        st = self.stats
        st["round_trips"] += 1
        if pnl >= 0:
            st["wins"] += 1
            st["gross_profit"] += pnl
        else:
            st["losses"] += 1
            st["gross_loss"] += -pnl
        st["exit_reasons"][reason] = st["exit_reasons"].get(reason, 0) + 1
        self.cancel_all_orders(event.instrument_id)
        self._log((trade or {}).get("signal_id", ""), unix_nanos_to_dt(event.ts_event), symbol, (trade or {}).get("side", ""),
                  "exit", (trade or {}).get("entry_coid", ""), fill_price=self._last_fill_px.get(symbol),
                  stop=(trade or {}).get("stop"), target=(trade or {}).get("target"), qty=(trade or {}).get("qty"),
                  exit_reason=reason, note=f"realized_pnl_usdt={pnl:.6f}")

    # ------------------------------------------------------------------ journal
    def _log(self, sid: str, ts, symbol: str, side: str, event: str, order_id: str = "", **fields: Any) -> None:
        row = {"signal_id": sid, "timestamp": risk.to_utc(ts).isoformat(), "symbol": symbol, "side": side, "event": event,
               "order_id": order_id, "limit_price": None, "fill_price": None, "stop": None, "target": None, "qty": None,
               "exit_reason": "", "note": ""}
        row.update(fields)
        self.journal.append(row)

    def on_stop(self) -> None:
        for iid in self._iid_by_symbol.values():
            self.cancel_all_orders(iid)
            self.close_all_positions(iid)
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            gp, gl = self.stats["gross_profit"], self.stats["gross_loss"]
            self.stats["profit_factor"] = (gp / gl) if gl > 0 else None
            (OUTPUT_DIR / "replay_stats.json").write_text(json.dumps(self.stats, indent=2, default=str), encoding="utf-8")
            (OUTPUT_DIR / "trade_journal.json").write_text(json.dumps(self.journal, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass
