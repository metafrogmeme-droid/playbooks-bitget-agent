"""Live order execution for RUNECLAW Intraday Session Flow.

Every function here performs Bitget USDT-M contract mutations through
``getagent.trade`` and is ONLY reachable from the ``execute_trade`` callback
passed to ``runtime.emit_signal_or_follow`` in ``main_live.py``.  The managed
runtime decides whether that callback runs.

reduceOnly contract: the Trade SDK exposes no explicit ``reduce_only`` flag.
Exits are therefore implemented only through mechanisms that can never add
exposure: position-bound TP/SL plan orders (set on the entry order, adjusted
with ``modify_take_profit`` / ``modify_stop_loss``) and
``trade.contract.close_position`` (full flash close).  No exit ever uses
``place_order``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Any

from getagent import trade

from . import journal as journal_mod
from .params import PlaybookParams
from .risk import DailyLedger

UTC = timezone.utc


def _step(symbol: str) -> Decimal:
    rules = trade.helpers.contract_rules(symbol)
    step = getattr(rules, "price_step", None) or getattr(rules, "price_increment", None) or "0.01"
    return Decimal(str(step))


def quantize_price(price: float, step: Decimal, mode: str = "nearest") -> Decimal:
    rounding = {"down": ROUND_DOWN, "up": ROUND_UP}.get(mode, ROUND_HALF_UP)
    value = Decimal(str(price))
    return (value / step).to_integral_value(rounding=rounding) * step


def _selection_order_id(selection: Any) -> str:
    for attr in ("order_id", "orderId", "plan_order_id"):
        value = getattr(selection, attr, None)
        if value:
            return str(value)
    return journal_mod.extract_order_id(getattr(selection, "raw", None))


def _require(result: Any, what: str) -> Any:
    if not trade.is_success(result):
        raise RuntimeError(f"{what} failed: {result}")
    return result


# --------------------------------------------------------------------------- #
# entry
# --------------------------------------------------------------------------- #
def place_entry(decision: dict[str, Any], params: PlaybookParams, state: dict[str, Any],
                journal: journal_mod.Journal, now: datetime) -> dict[str, Any]:
    symbol = decision["symbol"]
    cand = decision["candidate"]
    size = decision["size"]
    side = cand["side"]
    step = _step(symbol)

    # Limit: for a buy never round up (don't pay more); for a sell never round down.
    limit_q = quantize_price(cand["limit_price"], step, "down" if side == "long" else "up")
    stop_q = quantize_price(cand["stop_price"], step, "nearest")
    target_q = quantize_price(cand["target_price"], step, "nearest")

    qty_plan = trade.helpers.compute_qty(
        symbol=symbol,
        market="contract",
        budget_amount=str(Decimal(str(size["margin_usdt"])).quantize(Decimal("0.0001"))),
        leverage=params.leverage,
        price=str(limit_q),
    )
    tpsl = trade.helpers.resolve_contract_tpsl(
        symbol=symbol,
        side=side,
        leverage=params.leverage,
        tp_trigger_price=str(target_q),
        sl_trigger_price=str(stop_q),
        reference_price=str(limit_q),
    )
    opener = trade.contract.open_long_limit if side == "long" else trade.contract.open_short_limit
    result = _require(
        opener(
            symbol=symbol,
            qty=qty_plan.qty,
            price=str(limit_q),
            leverage=params.leverage,
            tp_trigger_price=tpsl.tp_trigger_price,
            sl_trigger_price=tpsl.sl_trigger_price,
        ),
        f"open_{side}_limit {symbol}",
    )
    order_id = journal_mod.extract_order_id(result)
    expires_at = decision["expires_at"]
    state["pending"][symbol] = {
        "signal_id": decision["signal_id"],
        "kind": cand["kind"],
        "side": side,
        "order_id": order_id,
        "limit_price": float(limit_q),
        "stop": float(tpsl.sl_trigger_price or stop_q),
        "target": float(tpsl.tp_trigger_price or target_q),
        "r_distance": abs(float(limit_q) - float(stop_q)),
        "qty": str(qty_plan.qty),
        "placed_at": now.isoformat(),
        "expires_at": expires_at,
    }
    journal.log(signal_id=decision["signal_id"], timestamp=now, symbol=symbol, side=side, event="entry_placed",
                order_id=order_id, limit_price=float(limit_q), stop=float(stop_q), target=float(target_q),
                qty=str(qty_plan.qty), note=f"kind={cand['kind']} expires_at={expires_at} reasons={cand['reasons']}")
    journal.log(signal_id=decision["signal_id"], timestamp=now, symbol=symbol, side=side, event="stop_set",
                order_id=order_id, stop=float(stop_q), note="position SL plan order attached to entry (reduce-only by construction)")
    journal.log(signal_id=decision["signal_id"], timestamp=now, symbol=symbol, side=side, event="target_set",
                order_id=order_id, target=float(target_q), note="position TP plan order attached to entry (reduce-only by construction)")
    return {"status": "entry_placed", "order_id": order_id, "qty": str(qty_plan.qty), "price": str(limit_q)}


# --------------------------------------------------------------------------- #
# cancel expired entry
# --------------------------------------------------------------------------- #
def cancel_expired(decision: dict[str, Any], state: dict[str, Any], journal: journal_mod.Journal,
                   now: datetime) -> dict[str, Any]:
    symbol = decision["symbol"]
    pend = state["pending"].get(symbol)
    if not pend:
        return {"status": "nothing_pending"}
    order_id = pend.get("order_id", "")
    pending_now = trade.contract.pending_orders(symbol=symbol)
    if order_id and order_id in journal_mod.pending_order_ids(pending_now, symbol):
        _require(trade.contract.cancel_order(symbol=symbol, order_id=order_id), f"cancel_order {symbol} {order_id}")
        after = trade.contract.pending_orders(symbol=symbol)
        still_there = order_id in journal_mod.pending_order_ids(after, symbol)
        note = "cancelled (post-check ok)" if not still_there else "cancel sent but order still listed"
    else:
        note = "order no longer pending at cancel time"
    journal.log(signal_id=pend["signal_id"], timestamp=now, symbol=symbol, side=pend["side"], event="entry_cancelled",
                order_id=order_id, limit_price=pend.get("limit_price"), exit_reason="expiry", note=note)
    del state["pending"][symbol]
    return {"status": "cancelled", "order_id": order_id}


# --------------------------------------------------------------------------- #
# flatten
# --------------------------------------------------------------------------- #
def flatten(decision: dict[str, Any], params: PlaybookParams, state: dict[str, Any], ledger: DailyLedger,
            journal: journal_mod.Journal, now: datetime) -> dict[str, Any]:
    symbol = decision["symbol"]
    reason = decision["reason"]
    trade_rec = state["open"].get(symbol)

    # PRE-CHECK: cancel resting entry orders for the symbol first, then read live position.
    for order_id in journal_mod.pending_order_ids(trade.contract.pending_orders(symbol=symbol), symbol):
        _require(trade.contract.cancel_order(symbol=symbol, order_id=order_id), f"cancel_order {symbol} {order_id}")
    current = trade.contract.current_position(symbol=symbol)
    position = trade.helpers.find_contract_position(current, symbol=symbol)
    if position is None:
        journal.log(signal_id=(trade_rec or {}).get("signal_id", ""), timestamp=now, symbol=symbol,
                    side=(trade_rec or {}).get("side", ""), event="flatten_requested", exit_reason=reason,
                    note="no live position at flatten time")
        state["open"].pop(symbol, None)
        state["pending"].pop(symbol, None)
        return {"status": "already_flat"}

    hold_side = position.hold_side
    mark = None
    try:
        mark = float(trade.helpers.contract_price(symbol))
    except Exception:  # noqa: BLE001 - price is only for the pnl estimate
        mark = None

    # EXECUTE: full close is reduce-only by construction.
    _require(trade.contract.close_position(symbol=symbol, hold_side=hold_side), f"close_position {symbol} {hold_side}")

    # POST-CHECK
    after = trade.helpers.find_contract_position(trade.contract.current_position(symbol=symbol), symbol=symbol)
    post = "flat" if after is None else f"position still open size={after.size}"

    pnl = None
    if trade_rec and mark is not None:
        sign = 1.0 if trade_rec["side"] == "long" else -1.0
        pnl = sign * (mark - float(trade_rec["entry_price"])) * float(trade_rec["qty"])
        ledger.record_pnl(pnl, params)
    journal.log(signal_id=(trade_rec or {}).get("signal_id", ""), timestamp=now, symbol=symbol, side=str(hold_side),
                event="exit", order_id=(trade_rec or {}).get("entry_order_id", ""), fill_price=mark,
                stop=(trade_rec or {}).get("stop"), target=(trade_rec or {}).get("target"),
                qty=float(position.size), exit_reason=reason,
                note=f"close_position; post_check={post}; pnl_estimate_usdt={pnl} (mark-based estimate)")
    state["open"].pop(symbol, None)
    state["pending"].pop(symbol, None)
    return {"status": "flattened", "post_check": post, "pnl_estimate_usdt": pnl}


# --------------------------------------------------------------------------- #
# manage exits on an open position
# --------------------------------------------------------------------------- #
def update_exits(decision: dict[str, Any], state: dict[str, Any], journal: journal_mod.Journal,
                 now: datetime) -> dict[str, Any]:
    symbol = decision["symbol"]
    trade_rec = state["open"].get(symbol)
    if not trade_rec:
        return {"status": "no_open_trade"}
    step = _step(symbol)
    plan_orders = trade.contract.plan_pending_orders(symbol=symbol)
    out: dict[str, Any] = {"status": "managed"}

    new_target = decision.get("new_target")
    if new_target is not None:
        tq = quantize_price(float(new_target), step, "nearest")
        if float(tq) != float(trade_rec["target"]):
            sel = trade.helpers.select_tp_plan_order(plan_orders, symbol=symbol, prefer_first=True)
            oid = _selection_order_id(sel)
            _require(trade.contract.modify_take_profit(symbol=symbol, order_id=oid, trigger_price=str(tq)),
                     f"modify_take_profit {symbol}")
            trade_rec["target"] = float(tq)
            journal.log(signal_id=trade_rec["signal_id"], timestamp=now, symbol=symbol, side=trade_rec["side"],
                        event="target_modified", order_id=oid, target=float(tq), note="Signal A target follows session VWAP")
            out["target"] = float(tq)

    new_stop = decision.get("new_stop")
    if new_stop is not None:
        sq = quantize_price(float(new_stop), step, "nearest")
        if float(sq) != float(trade_rec["stop"]):
            sel = trade.helpers.select_sl_plan_order(plan_orders, symbol=symbol, prefer_first=True)
            oid = _selection_order_id(sel)
            _require(trade.contract.modify_stop_loss(symbol=symbol, order_id=oid, trigger_price=str(sq)),
                     f"modify_stop_loss {symbol}")
            trade_rec["stop"] = float(sq)
            journal.log(signal_id=trade_rec["signal_id"], timestamp=now, symbol=symbol, side=trade_rec["side"],
                        event="stop_modified", order_id=oid, stop=float(sq), note="Signal B trailing stop")
            out["stop"] = float(sq)
    if "best_excursion" in decision:
        trade_rec["best_excursion"] = decision["best_excursion"]
    return out


# --------------------------------------------------------------------------- #
# dispatcher used by the execute_trade callback
# --------------------------------------------------------------------------- #
def execute(decision: dict[str, Any], params: PlaybookParams, state: dict[str, Any], ledger: DailyLedger,
            journal: journal_mod.Journal, now: datetime) -> dict[str, Any]:
    intent = decision.get("intent")
    if intent == "open":
        return place_entry(decision, params, state, journal, now)
    if intent == "cancel_expired":
        return cancel_expired(decision, state, journal, now)
    if intent == "flatten":
        return flatten(decision, params, state, ledger, journal, now)
    if intent == "manage":
        return update_exits(decision, state, journal, now)
    return {"status": "noop", "intent": intent}
