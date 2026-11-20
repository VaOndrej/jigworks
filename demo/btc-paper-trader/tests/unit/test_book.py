"""OrderBook, observed through the engine's ``book`` (price levels with FIFO queues)."""

from decimal import Decimal as D

from bpt_helpers import MAKER, MAKER2, USER_A, USER_B, engine, limit, maker, user


def _setup():
    eng = engine()
    user(eng, USER_A)
    user(eng, USER_B)
    maker(eng, MAKER)
    maker(eng, MAKER2)
    return eng


def test_empty_book_has_no_best_prices_and_is_not_crossed():
    eng = engine()
    assert eng.book.best_bid() is None
    assert eng.book.best_ask() is None
    assert eng.book.levels("buy", 20) == []
    assert eng.book.is_crossed() is False


def test_levels_aggregate_qty_per_price_best_first():
    eng = _setup()
    limit(eng, USER_A, "buy", "0.0001", "99000")
    limit(eng, USER_B, "buy", "0.0002", "99000")
    limit(eng, USER_A, "buy", "0.0001", "99500")
    limit(eng, MAKER, "sell", "0.0003", "100500")
    limit(eng, MAKER2, "sell", "0.0001", "100200")
    assert eng.book.levels("buy", 20) == [(D("99500"), D("0.0001")), (D("99000"), D("0.0003"))]
    assert eng.book.levels("sell", 20) == [(D("100200"), D("0.0001")), (D("100500"), D("0.0003"))]
    assert eng.book.best_bid() == D("99500")
    assert eng.book.best_ask() == D("100200")


def test_levels_respects_depth():
    eng = _setup()
    for i in range(5):
        limit(eng, USER_A, "buy", "0.0001", str(99000 + i * 10))
    assert len(eng.book.levels("buy", 3)) == 3
    assert eng.book.levels("buy", 3)[0][0] == D("99040")


def test_iter_makers_yields_best_price_then_time_order():
    eng = _setup()
    first = limit(eng, MAKER, "sell", "0.0001", "100300").order
    second = limit(eng, MAKER2, "sell", "0.0001", "100300").order
    better = limit(eng, MAKER2, "sell", "0.0001", "100100").order
    ids = [o.order_id for o in eng.book.iter_makers("sell")]
    assert ids == [better.order_id, first.order_id, second.order_id]


def test_cancel_removes_the_order_from_its_level():
    eng = _setup()
    a = limit(eng, USER_A, "buy", "0.0001", "99000").order
    limit(eng, USER_B, "buy", "0.0002", "99000")
    eng.cancel(USER_A, a.order_id, now_ms=a.created_ms)
    assert eng.book.levels("buy", 20) == [(D("99000"), D("0.0002"))]


def test_emptied_level_disappears():
    eng = _setup()
    a = limit(eng, USER_A, "buy", "0.0001", "99000").order
    eng.cancel(USER_A, a.order_id, now_ms=a.created_ms)
    assert eng.book.levels("buy", 20) == []
    assert eng.book.best_bid() is None
