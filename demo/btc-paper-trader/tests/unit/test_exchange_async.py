"""ExchangeTask async behaviour: single writer (A4), group commit (A5), back-pressure, shutdown (A7).

Contract: ``ExchangeTask(engine, store, clock=..., maxsize=10_000)``; ``await task.run()`` is the
group-commit loop; ``await task.open_account(id)`` / ``submit(req)`` / ... enqueue a command and
await its future; ``await task.idle()``.
"""

import asyncio
import uuid
from decimal import Decimal as D
from pathlib import Path

import pytest
from bpt_helpers import T0, req


class SpyStore:
    def __init__(self):
        self.commits = 0

    async def open(self):
        return None

    async def load(self):
        return None

    async def commit(self, batch):
        self.commits += 1

    async def close(self):
        return None


async def test_commands_enqueued_before_the_task_runs_are_committed_in_one_transaction():
    """A5."""
    from btc_paper_trader.exchange import ExchangeTask
    from btc_paper_trader.matching import Engine

    spy = SpyStore()
    ex = ExchangeTask(Engine(), spy, clock=lambda: T0)
    ids = [uuid.uuid4().hex for _ in range(50)]
    pending = [asyncio.ensure_future(ex.open_account(i)) for i in ids]
    await asyncio.sleep(0)
    runner = asyncio.create_task(ex.run())
    try:
        await asyncio.wait_for(asyncio.gather(*pending), 5)
        await asyncio.wait_for(ex.idle(), 5)
        assert spy.commits == 1
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


async def test_idle_returns_once_the_queue_is_empty_and_committed():
    from btc_paper_trader.exchange import ExchangeTask
    from btc_paper_trader.matching import Engine

    spy = SpyStore()
    eng = Engine()
    ex = ExchangeTask(eng, spy, clock=lambda: T0)
    runner = asyncio.create_task(ex.run())
    try:
        aid = uuid.uuid4().hex
        asyncio.ensure_future(ex.open_account(aid))
        await asyncio.sleep(0)
        await asyncio.wait_for(ex.idle(), 5)
        assert eng.account(aid) is not None
        assert spy.commits >= 1
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


def _requests(accounts):
    out = []
    for n, a in enumerate(accounts):
        for k in range(10):
            if k % 3 == 0:
                out.append(req(a, "buy", "market", quote_amount=D("5")))
            elif k % 3 == 1:
                out.append(req(a, "buy", "limit", qty=D("0.0001"), price=D(99_900 - 10 * ((n + k) % 7))))
            else:
                out.append(req(a, "buy", "limit", qty=D("0.00005"), price=D(100_100 + 10 * (k % 5))))
    return out


async def test_concurrent_submits_equal_sequential_application_in_enqueue_order(service, clock):
    """A4: 500 gathered submits from 50 accounts == the same commands applied one by one."""
    from btc_paper_trader.matching import Engine

    accounts = [uuid.uuid4().hex for _ in range(50)]
    await asyncio.gather(*(service.exchange.open_account(a) for a in accounts))
    await service.tick(D("100000"))
    snapshot = Engine.from_records(service.engine.to_records())

    reqs = _requests(accounts)
    results = await asyncio.gather(*(service.exchange.submit(r) for r in reqs))
    await service.exchange.idle()

    for r in reqs:
        snapshot.submit(r, now_ms=clock.now())
    assert service.engine.to_records() == snapshot.to_records()
    assert len(results) == 500
    assert any(res.trades for res in results), "some market buys must fill against the house"


def test_exchange_module_uses_no_asyncio_lock():
    import btc_paper_trader.exchange as exchange

    text = Path(exchange.__file__).read_text()
    assert "Lock(" not in text


async def test_a_full_command_queue_answers_503_overloaded(make_config, monkeypatch):
    import httpx

    from btc_paper_trader.api import create_app

    app = create_app(make_config(queue_maxsize=1, ack_timeout_s=0.3))
    async with app.router.lifespan_context(app):
        service = app.state.service
        await service.tick(D("100000"))
        gate = asyncio.Event()
        original = service.store.commit

        async def stalled(batch):
            await gate.wait()
            return await original(batch)

        monkeypatch.setattr(service.store, "commit", stalled)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            cookies={"account_id": uuid.uuid4().hex},
        ) as c:
            body = {"side": "buy", "type": "limit", "qty": "0.0001", "price": "90000.00"}
            responses = await asyncio.wait_for(
                asyncio.gather(*(c.post("/api/orders", json=body) for _ in range(4))), 10
            )
        gate.set()
        codes = [r.status_code for r in responses]
        assert 503 in codes, codes
        for r in responses:
            if r.status_code == 503:
                assert r.json()["reason"] == "overloaded"


async def test_leaving_running_commits_pending_commands_and_leaves_no_tasks(make_config):
    """A7."""
    from btc_paper_trader.service import Service

    cfg = make_config()
    baseline = asyncio.all_tasks()
    ids = [uuid.uuid4().hex for _ in range(25)]
    svc = Service(cfg)
    async with svc.running():
        pending = [asyncio.create_task(svc.exchange.open_account(i)) for i in ids]
        await asyncio.sleep(0)
    await asyncio.wait_for(asyncio.gather(*pending), 5)
    await asyncio.sleep(0)
    leftover = {t for t in asyncio.all_tasks() - baseline if not t.done()}
    assert not leftover, leftover

    again = Service(cfg)
    async with again.running():
        assert all(again.engine.account(i) is not None for i in ids)


async def test_a_failing_store_commit_stops_the_service_with_an_error(make_config, monkeypatch):
    from btc_paper_trader.service import Service

    svc = Service(make_config())

    async def broken(batch):
        raise RuntimeError("disk full (fake)")

    with pytest.raises((RuntimeError, BaseExceptionGroup)):
        async with asyncio.timeout(5):
            async with svc.running():
                monkeypatch.setattr(svc.store, "commit", broken)
                await svc.exchange.open_account(uuid.uuid4().hex)
                await asyncio.sleep(3)
