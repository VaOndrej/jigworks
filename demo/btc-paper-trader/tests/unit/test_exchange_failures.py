"""F1/F2: a command whose caller gave up never executes; an engine failure is never committed."""

import asyncio
import uuid
from decimal import Decimal as D

import pytest
from bpt_helpers import T0, req


class SpyStore:
    def __init__(self):
        self.commits = 0

    async def commit(self, batch):
        self.commits += 1


async def test_a_command_whose_future_was_cancelled_is_not_applied():
    from btc_paper_trader.exchange import ExchangeTask
    from btc_paper_trader.matching import Engine

    eng = Engine()
    ex = ExchangeTask(eng, SpyStore(), clock=lambda: T0)
    aid = uuid.uuid4().hex
    waiting = asyncio.ensure_future(ex.open_account(aid))
    await asyncio.sleep(0)
    waiting.cancel()  # the ack timeout of the HTTP handler
    await asyncio.gather(waiting, return_exceptions=True)
    runner = asyncio.create_task(ex.run())
    try:
        await asyncio.wait_for(ex.idle(), 5)
        assert eng.account(aid) is None
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


async def test_an_engine_exception_stops_the_task_and_nothing_is_committed():
    from btc_paper_trader.exchange import ExchangeTask
    from btc_paper_trader.matching import Engine

    eng = Engine()
    store = SpyStore()
    ex = ExchangeTask(eng, store, clock=lambda: T0)

    def boom(*a, **k):
        raise RuntimeError("engine bug (fake)")

    eng.submit = boom
    runner = asyncio.create_task(ex.run())
    pending = asyncio.ensure_future(ex.submit(req("a" * 32, "buy", "market", quote_amount=D("5"))))
    with pytest.raises(RuntimeError):
        await asyncio.wait_for(runner, 5)
    with pytest.raises(RuntimeError):
        await pending
    assert store.commits == 0
