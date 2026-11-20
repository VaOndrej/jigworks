"""Engine M3: stop orders on the internal last trade, cascades, SL/TP brackets, reduce-only, close."""

from decimal import Decimal as D

import pytest
from bpt_helpers import (
    MAKER,
    MAKER2,
    T0,
    USER_A,
    USER_B,
    USER_C,
    engine,
    limit,
    maker,
    market,
    order_by_id,
    req,
    stop,
    user,
)


@pytest.fixture
def eng():
    """USER_A holds 0.0005 BTC bought at 100000; the last trade is 100000."""
    e = engine()
    for a in (USER_A, USER_B, USER_C):
        user(e, a)
    maker(e, MAKER, btc=D("0.01"))
    maker(e, MAKER2, btc=D("0.01"))
    limit(e, MAKER, "sell", "0.0005", "100000")
    market(e, USER_A, "buy", "0.0005")
    assert e.last_trade_price == D("100000")
    return e


def _children(eng, account_id, parent_id):
    return {o.role: o for o in eng.orders(account_id, open_only=False) if o.parent_id == parent_id}


# --- stops ----------------------------------------------------------------------------------


def test_a_stop_rests_outside_the_book_and_reserves_nothing(eng):
    r = stop(eng, USER_A, "sell", "0.0005", "99500")
    assert r.order.status == "open"
    assert eng.book.levels("sell", 20) == []
    assert eng.account(USER_A).btc_reserved == 0


def test_stop_sell_triggers_when_the_last_trade_falls_to_its_stop_price(eng):
    s = stop(eng, USER_A, "sell", "0.0005", "99500").order
    limit(eng, MAKER2, "buy", "0.0009", "99500")
    r = market(eng, MAKER, "sell", "0.0001")
    assert s.order_id in r.triggered_order_ids
    stop_trades = [t for t in r.trades if t.sell_order_id == s.order_id]
    assert sum(t.qty for t in stop_trades) == D("0.0005")
    assert all(t.price == D("99500") for t in stop_trades)
    assert eng.account(USER_A).btc == 0
    assert order_by_id(eng, USER_A, s.order_id).status == "filled"


def test_stop_buy_triggers_when_the_last_trade_rises_to_its_stop_price(eng):
    s = stop(eng, USER_C, "buy", "0.0001", "100500").order
    limit(eng, MAKER, "sell", "0.0002", "100500")
    limit(eng, MAKER2, "sell", "0.0005", "100600")
    r = market(eng, USER_B, "buy", "0.0002")
    assert s.order_id in r.triggered_order_ids
    assert eng.account(USER_C).btc == D("0.0001")
    assert [t.price for t in r.trades if t.buy_order_id == s.order_id] == [D("100600")]


def test_a_stop_that_would_trigger_immediately_is_rejected_invalid_stop(eng):
    assert stop(eng, USER_A, "sell", "0.0001", "100500").reason == "invalid_stop"
    assert stop(eng, USER_B, "buy", "0.0001", "99000").reason == "invalid_stop"


def test_without_a_last_trade_the_reference_decides_whether_a_stop_triggers_immediately():
    e = engine()
    user(e, USER_A)
    assert stop(e, USER_A, "buy", "0.0001", "99000").reason == "invalid_stop"
    assert stop(e, USER_A, "buy", "0.0001", "101000").order.status == "open"


def test_stop_below_minimum_notional_is_rejected(eng):
    # 0.00001 * 99000 = 0.99 < $1
    assert stop(eng, USER_A, "sell", "0.00001", "99000").reason == "below_minimum"


def test_cascade_runs_sell_stops_highest_first_then_by_seq():
    e = engine()
    for a in (USER_A, USER_B, USER_C):
        user(e, a)
    maker(e, MAKER, btc=D("0.01"))
    maker(e, MAKER2, btc=D("0.01"))
    limit(e, MAKER, "sell", "0.001", "100000")
    for a in (USER_A, USER_B, USER_C):
        market(e, a, "buy", "0.0002")
    a = stop(e, USER_A, "sell", "0.0002", "99800").order
    b = stop(e, USER_B, "sell", "0.0002", "99600").order
    c = stop(e, USER_C, "sell", "0.0002", "99800").order
    limit(e, MAKER2, "buy", "0.0008", "99500")
    r = market(e, MAKER, "sell", "0.0001")
    stop_ids = {a.order_id, b.order_id, c.order_id}
    sequence = [t.sell_order_id for t in r.trades if t.sell_order_id in stop_ids]
    assert sequence == [a.order_id, c.order_id, b.order_id]


def test_cascade_runs_buy_stops_lowest_first():
    e = engine()
    for x in (USER_A, USER_B, USER_C):
        user(e, x)
    maker(e, MAKER, btc=D("0.01"))
    maker(e, MAKER2, btc=D("0.01"))
    hi = stop(e, USER_A, "buy", "0.0001", "100400").order
    lo = stop(e, USER_B, "buy", "0.0001", "100200").order
    limit(e, MAKER, "sell", "0.0001", "100500")
    limit(e, MAKER2, "sell", "0.001", "100600")
    r = market(e, USER_C, "buy", "0.0001")
    sequence = [t.buy_order_id for t in r.trades if t.buy_order_id in {hi.order_id, lo.order_id}]
    assert sequence == [lo.order_id, hi.order_id]


def test_triggered_stop_is_clipped_to_the_free_btc(eng):
    s = stop(eng, USER_A, "sell", "0.0005", "99500").order
    limit(eng, USER_A, "sell", "0.0003", "101000")
    limit(eng, MAKER2, "buy", "0.0009", "99500")
    r = market(eng, MAKER, "sell", "0.0001")
    assert sum(t.qty for t in r.trades if t.sell_order_id == s.order_id) == D("0.0002")
    assert eng.account(USER_A).btc == D("0.0003")
    assert eng.account(USER_A).btc_reserved == D("0.0003")


def test_triggered_stop_with_nothing_available_is_cancelled_insufficient_funds(eng):
    s = stop(eng, USER_A, "sell", "0.0005", "99500").order
    limit(eng, USER_A, "sell", "0.0005", "101000")
    limit(eng, MAKER2, "buy", "0.0009", "99500")
    market(eng, MAKER, "sell", "0.0001")
    o = order_by_id(eng, USER_A, s.order_id)
    assert o.status == "cancelled"
    assert o.reason == "insufficient_funds"


# --- reduce-only ----------------------------------------------------------------------------


def test_reduce_only_buy_is_rejected(eng):
    r = limit(eng, USER_A, "buy", "0.0001", "99000", reduce_only=True)
    assert r.reason == "reduce_only_buy"


def test_reduce_only_sell_when_flat_is_rejected_nothing_to_reduce(eng):
    r = limit(eng, USER_B, "sell", "0.0001", "101000", reduce_only=True)
    assert r.reason == "nothing_to_reduce"


def test_reduce_only_sell_is_clipped_to_the_free_btc(eng):
    r = limit(eng, USER_A, "sell", "0.001", "101000", reduce_only=True)
    assert r.order.status == "open"
    assert r.order.qty == D("0.0005")
    assert eng.account(USER_A).btc_reserved == D("0.0005")


def test_becoming_flat_cancels_all_open_reduce_only_orders_with_flat(eng):
    ro = stop(eng, USER_A, "sell", "0.0005", "99000", reduce_only=True).order
    limit(eng, MAKER2, "buy", "0.0009", "99900")
    market(eng, USER_A, "sell", "0.0005")
    o = order_by_id(eng, USER_A, ro.order_id)
    assert o.status == "cancelled"
    assert o.reason == "flat"


# --- SL/TP ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(type="market", qty=D("0.0001"), sl=D("100000")),  # SL >= ref
        dict(type="market", qty=D("0.0001"), tp=D("99000")),  # TP <= ref
        dict(type="limit", qty=D("0.0001"), price=D("99900"), sl=D("99950")),  # SL >= limit
        dict(type="limit", qty=D("0.0001"), price=D("99900"), tp=D("99800")),  # TP <= limit
    ],
)
def test_sl_tp_on_the_wrong_side_is_rejected_invalid_sl_tp(eng, kwargs):
    r = eng.submit(req(USER_B, "buy", **kwargs), now_ms=T0)
    assert r.reason == "invalid_sl_tp"


def test_sl_tp_on_a_sell_entry_is_rejected_invalid_sl_tp(eng):
    r = limit(eng, USER_A, "sell", "0.0001", "101000", sl=D("99000"))
    assert r.reason == "invalid_sl_tp"


def test_sl_tp_children_start_unarmed_and_reserve_nothing(eng):
    entry = limit(eng, USER_B, "buy", "0.0005", "99900", sl=D("99000"), tp=D("101000")).order
    kids = _children(eng, USER_B, entry.order_id)
    assert set(kids) == {"sl", "tp"}
    for k in kids.values():
        assert k.status == "new"
        assert k.armed is False
        assert k.reduce_only is True
        assert k.side == "sell"
    assert kids["tp"].type == "limit" and kids["tp"].price == D("101000")
    assert kids["sl"].type == "stop" and kids["sl"].stop_price == D("99000")
    assert eng.account(USER_B).btc_reserved == 0
    assert eng.book.levels("sell", 20) == []


def test_children_arm_on_the_first_fill_and_grow_with_the_parent(eng):
    entry = limit(eng, USER_B, "buy", "0.0005", "99900", sl=D("99000"), tp=D("101000")).order
    market(eng, MAKER, "sell", "0.0002")
    kids = _children(eng, USER_B, entry.order_id)
    for k in kids.values():
        assert k.armed is True and k.status == "open"
        assert k.qty == D("0.0002")
    assert eng.book.levels("sell", 20) == [(D("101000"), D("0.0002"))]
    assert eng.account(USER_B).btc_reserved == D("0.0002")

    market(eng, MAKER, "sell", "0.0001")
    kids = _children(eng, USER_B, entry.order_id)
    assert kids["tp"].qty == D("0.0003") and kids["sl"].qty == D("0.0003")
    assert eng.account(USER_B).btc_reserved == D("0.0003")


def test_a_growing_tp_goes_to_the_back_of_its_level(eng):
    entry = limit(eng, USER_B, "buy", "0.0005", "99900", sl=D("99000"), tp=D("101000")).order
    market(eng, MAKER, "sell", "0.0002")
    other = limit(eng, MAKER2, "sell", "0.0001", "101000").order
    market(eng, MAKER, "sell", "0.0001")  # TP grows -> loses its place
    r = market(eng, USER_C, "buy", "0.0001")
    assert [t.sell_order_id for t in r.trades] == [other.order_id]
    assert _children(eng, USER_B, entry.order_id)["tp"].filled_qty == 0


def test_cancelling_a_parent_without_fills_cancels_its_children(eng):
    entry = limit(eng, USER_B, "buy", "0.0005", "99900", sl=D("99000"), tp=D("101000")).order
    eng.cancel(USER_B, entry.order_id, now_ms=T0)
    for k in _children(eng, USER_B, entry.order_id).values():
        assert k.status == "cancelled"
        assert k.reason == "parent_cancelled"


def test_tp_filling_to_flat_cancels_the_sl_with_flat(eng):
    entry = limit(eng, USER_B, "buy", "0.0005", "99900", sl=D("99000"), tp=D("101000")).order
    market(eng, MAKER, "sell", "0.0005")
    market(eng, USER_C, "buy", "0.0005")
    kids = _children(eng, USER_B, entry.order_id)
    assert kids["tp"].status == "filled"
    assert kids["sl"].status == "cancelled" and kids["sl"].reason == "flat"
    assert eng.account(USER_B).btc == 0


def test_sl_trigger_cancels_the_tp_and_market_sells_the_position(eng):
    entry = limit(eng, USER_B, "buy", "0.0005", "99900", sl=D("99000"), tp=D("101000")).order
    market(eng, MAKER, "sell", "0.0005")
    limit(eng, MAKER2, "buy", "0.0009", "99000")
    r = market(eng, MAKER, "sell", "0.0001")
    kids = _children(eng, USER_B, entry.order_id)
    assert kids["sl"].order_id in r.triggered_order_ids
    assert kids["tp"].status == "cancelled" and kids["tp"].reason == "sl_triggered"
    assert kids["sl"].status == "filled"
    assert eng.account(USER_B).btc == 0
    assert eng.account(USER_B).btc_reserved == 0


def test_partial_tp_fill_leaves_the_sl_following_the_remaining_position(eng):
    entry = limit(eng, USER_B, "buy", "0.0005", "99900", sl=D("99000"), tp=D("101000")).order
    market(eng, MAKER, "sell", "0.0005")
    market(eng, USER_C, "buy", "0.0002")  # TP fills 0.0002 of 0.0005
    limit(eng, MAKER2, "buy", "0.0009", "99000")
    market(eng, MAKER, "sell", "0.0001")  # SL triggers
    kids = _children(eng, USER_B, entry.order_id)
    assert kids["tp"].status == "cancelled" and kids["tp"].reason == "sl_triggered"
    assert kids["sl"].filled_qty == D("0.0003")
    assert eng.account(USER_B).btc == 0


# --- close position -------------------------------------------------------------------------


def test_close_position_cancels_sell_orders_then_market_sells_everything_reduce_only(eng):
    sell = limit(eng, USER_A, "sell", "0.0002", "101000").order
    buy = limit(eng, USER_A, "buy", "0.0001", "98000").order
    limit(eng, MAKER2, "buy", "0.0009", "99900")
    r = eng.close_position(USER_A, now_ms=T0 + 1)
    assert r.order.role == "close"
    assert r.order.reduce_only is True
    assert sum(t.qty for t in r.trades) == D("0.0005")
    assert eng.account(USER_A).btc == 0
    s = order_by_id(eng, USER_A, sell.order_id)
    assert s.status == "cancelled" and s.reason == "close_position"
    assert order_by_id(eng, USER_A, buy.order_id).status == "open"


def test_close_position_when_flat_is_nothing_to_reduce(eng):
    assert eng.close_position(USER_B, now_ms=T0).reason == "nothing_to_reduce"
