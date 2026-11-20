"""JSON views of engine state. Every Decimal is a string; the browser only renders."""

from __future__ import annotations

from .accounts import AccountView, Fill
from .candles import Candle
from .matching import Engine, Order, Trade
from .money import dstr

HISTORY_LIMIT = 200


def order_json(o: Order) -> dict:
    return {
        "order_id": o.order_id,
        "parent_id": o.parent_id,
        "side": o.side,
        "type": o.type,
        "role": o.role,
        "qty": dstr(o.qty),
        "quote_amount": dstr(o.quote_amount),
        "price": dstr(o.price),
        "stop_price": dstr(o.stop_price),
        "filled_qty": dstr(o.filled_qty),
        "reduce_only": bool(o.reduce_only),
        "armed": bool(o.armed),
        "status": o.status,
        "reason": o.reason,
        "created_ms": o.created_ms,
        "updated_ms": o.updated_ms,
    }


def trade_json(t: Trade) -> dict:
    return {
        "trade_id": t.trade_id,
        "ms": t.ms,
        "price": dstr(t.price),
        "qty": dstr(t.qty),
        "maker_side": t.maker_side,
    }


def fill_json(f: Fill, order: Order | None = None) -> dict:
    return {
        "trade_id": f.trade_id,
        "order_id": f.order_id,
        "side": f.side,
        "role": f.role,
        "price": dstr(f.price),
        "qty": dstr(f.qty),
        "fee": dstr(f.fee),
        "ms": f.ms,
    }


def candle_json(c: Candle) -> dict:
    return {
        "open_time_ms": c.open_time_ms,
        "open": dstr(c.open),
        "high": dstr(c.high),
        "low": dstr(c.low),
        "close": dstr(c.close),
        "volume": dstr(c.volume),
    }


def account_json(a: AccountView) -> dict:
    return {
        "usd": dstr(a.usd),
        "btc": dstr(a.btc),
        "usd_reserved": dstr(a.usd_reserved),
        "btc_reserved": dstr(a.btc_reserved),
        "available_usd": dstr(a.available_usd),
        "free_btc": dstr(a.free_btc),
        "equity": dstr(a.equity),
        "realized_pnl": dstr(a.realized_pnl),
        "unrealized_pnl": dstr(a.unrealized_pnl),
        "fees_paid": dstr(a.fees_paid),
        "return_pct": dstr(a.return_pct),
        "mark_price": dstr(a.mark_price),
    }


def state_body(engine: Engine, account_id: str) -> dict:
    """The ``/api/state`` body for one account (current epoch only)."""
    a = engine.account(account_id)
    orders = engine.orders(account_id, open_only=False)
    return {
        "account": account_json(a),
        "position": {
            "qty": dstr(a.btc),
            "avg_cost": dstr(a.avg_cost),
            "mark": dstr(a.mark_price),
            "unrealized": dstr(a.unrealized_pnl),
        },
        "open_orders": [order_json(o) for o in orders if o.status in ("new", "open", "partially_filled")],
        "history": [order_json(o) for o in reversed(orders[-HISTORY_LIMIT:])],
        "fills": [fill_json(f) for f in reversed(engine.fills(account_id))],
    }


def book_json(engine: Engine, depth: int, ts: int) -> dict:
    return {
        "bids": [[dstr(p), dstr(q)] for p, q in engine.book.levels("buy", depth)],
        "asks": [[dstr(p), dstr(q)] for p, q in engine.book.levels("sell", depth)],
        "ts": ts,
    }
