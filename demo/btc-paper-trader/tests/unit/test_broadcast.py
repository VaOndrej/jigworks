"""Broadcaster and per-client bounded queues; a slow client never delays anyone (A6).

Contract: ``Broadcaster()``; ``q = b.register(account_id)``; ``b.unregister(q)``;
``b.publish(msg, account_id=None)`` is synchronous (never a coroutine). Account messages
(``fill``/``state``) go only to queues registered for that ``account_id``; other messages go to
everyone. ``q.drain()`` returns waiting messages, must-deliver (``fill``/``state``) first;
``q.closed`` / ``q.close_code`` report the 1013 overflow close.
"""

import asyncio
import inspect
import time
import uuid
from decimal import Decimal as D

A = "a" * 32
B = "b" * 32


def _b():
    from btc_paper_trader.broadcast import Broadcaster

    return Broadcaster()


def test_publish_is_synchronous():
    b = _b()
    assert not inspect.iscoroutinefunction(b.publish)
    assert b.publish({"type": "trade", "price": "1"}) is None


def test_book_and_reference_messages_coalesce_to_the_newest():
    b = _b()
    q = b.register(A)
    for i in range(5):
        b.publish({"type": "book", "seq": i})
        b.publish({"type": "reference", "price": str(100 + i)})
    msgs = q.drain()
    books = [m for m in msgs if m["type"] == "book"]
    refs = [m for m in msgs if m["type"] == "reference"]
    assert [m["seq"] for m in books] == [4]
    assert [m["price"] for m in refs] == ["104"]


def test_candles_coalesce_per_source_and_timeframe():
    b = _b()
    q = b.register(A)
    for i in range(3):
        b.publish({"type": "candle", "source": "internal", "tf": "1m", "i": i})
        b.publish({"type": "candle", "source": "reference", "tf": "1m", "i": i})
    candles = [m for m in q.drain() if m["type"] == "candle"]
    assert sorted((m["source"], m["i"]) for m in candles) == [("internal", 2), ("reference", 2)]


def test_trades_keep_only_the_newest_100():
    b = _b()
    q = b.register(A)
    for i in range(150):
        b.publish({"type": "trade", "trade_id": i})
    trades = [m["trade_id"] for m in q.drain() if m["type"] == "trade"]
    assert trades == list(range(50, 150))


def test_fill_and_state_are_never_dropped_and_come_first():
    b = _b()
    q = b.register(A)
    b.publish({"type": "book", "seq": 1})
    for i in range(600):
        b.publish({"type": "fill", "i": i}, account_id=A)
    b.publish({"type": "state", "n": 1}, account_id=A)
    msgs = q.drain()
    must = [m for m in msgs if m["type"] in ("fill", "state")]
    assert len(must) == 601
    assert [m["i"] for m in must if m["type"] == "fill"] == list(range(600))
    first_other = next(i for i, m in enumerate(msgs) if m["type"] not in ("fill", "state"))
    assert first_other == 601
    assert not q.closed


def test_more_than_1000_waiting_must_deliver_messages_close_the_socket_with_1013():
    b = _b()
    q = b.register(A)
    for i in range(1001):
        b.publish({"type": "state", "i": i}, account_id=A)
    assert q.closed
    assert q.close_code == 1013


def test_fill_and_state_go_only_to_their_account():
    b = _b()
    qa, qb = b.register(A), b.register(B)
    b.publish({"type": "fill", "x": 1}, account_id=A)
    b.publish({"type": "trade", "trade_id": 1})
    assert [m["type"] for m in qa.drain()] == ["fill", "trade"]
    assert [m["type"] for m in qb.drain()] == ["trade"]


def test_unregistered_queue_gets_nothing():
    b = _b()
    q = b.register(A)
    b.unregister(q)
    b.publish({"type": "trade", "trade_id": 1})
    assert q.drain() == []


def test_publish_to_many_clients_with_one_stuck_client_is_fast():
    b = _b()
    stuck = b.register(A)
    others = [b.register(uuid.uuid4().hex) for _ in range(1000)]
    start = time.perf_counter()
    for i in range(200):
        b.publish({"type": "trade", "trade_id": i})
        b.publish({"type": "book", "seq": i})
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0
    assert len([m for m in others[0].drain() if m["type"] == "trade"]) == 100
    assert stuck.drain()  # it still holds a bounded amount


async def test_a_client_that_never_reads_does_not_delay_others_or_the_exchange(service):
    """A6."""
    slow_id, fast_id = uuid.uuid4().hex, uuid.uuid4().hex
    await service.exchange.open_account(slow_id)
    await service.exchange.open_account(fast_id)
    slow = service.broadcaster.register(slow_id)
    fast = service.broadcaster.register(fast_id)
    await service.tick(D("100000"))

    from bpt_helpers import req

    for _ in range(1100):
        service.broadcaster.publish({"type": "state", "flood": True}, account_id=slow_id)
    assert slow.closed and slow.close_code == 1013

    await asyncio.wait_for(service.exchange.submit(req(fast_id, "buy", "market", quote_amount=D("10"))), 5)
    await asyncio.wait_for(service.exchange.idle(), 5)
    types = [m["type"] for m in fast.drain()]
    assert "fill" in types and "state" in types
