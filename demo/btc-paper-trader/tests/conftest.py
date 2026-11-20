"""Shared test setup for btc-paper-trader (written by write_tests, read-only afterwards).

Interface contract the tests rely on (beyond what docs/design names verbatim):

* ``btc_paper_trader.config.Config`` is a dataclass accepting keyword arguments
  ``feed, seed, db, bots, port, open_browser, binance_base, sim_tick_ms, sim_manual,
  clock, sleep, queue_maxsize, ack_timeout_s, house_usd, house_btc, house_levels,
  house_spread_bps``. ``clock()`` returns epoch milliseconds (int); ``sleep(seconds)`` is a
  coroutine. ``sim_manual=True`` means the sim feed never ticks on its own; tests drive it
  with ``await service.tick(price)``. ``host`` is always ``"127.0.0.1"``.
* ``btc_paper_trader.service.Service(config)``; ``async with service.running():`` starts
  everything. Attributes: ``engine`` (the ``matching.Engine``), ``exchange``
  (``ExchangeTask``), ``store``, ``feed``, ``broadcaster``. ``await service.tick(price)``
  pushes one reference tick (plus the house requote in the same batch) and awaits
  ``exchange.idle()``.
* ``btc_paper_trader.api.create_app(config)``; ``app.state.service`` is the running service.
* Engine read side: ``engine.account(id)`` returns ``None`` for an unknown id, otherwise a
  view with ``usd, btc, usd_reserved, btc_reserved, available_usd, free_btc, equity,
  realized_pnl, unrealized_pnl, fees_paid, return_pct, cost_basis, epoch``.
  ``engine.orders(id, open_only=...)`` lists the current epoch's orders, oldest first;
  ``open_only=True`` means status ``new``, ``open`` or ``partially_filled``.
  ``engine.ledger()`` returns entries with ``account_id, asset, amount, kind, ref``.
  Special account ids: ``"house"``, ``"fees"``, ``"treasury"``.
* ``ExchangeTask(engine, store, clock=..., maxsize=10_000)``; async ``submit(req)``,
  ``cancel(account_id, order_id)``, ``reset(account_id)``, ``open_account(account_id)``,
  ``close_position(account_id)`` each return the engine ``Result``; ``await idle()``.
* ``matching.OrderRequest(account_id, side, type, qty=None, quote_amount=None, max=False,
  price=None, stop_price=None, reduce_only=False, sl=None, tp=None)``. Orders have
  ``order_id, account_id, side, type, qty, price, stop_price, reduce_only, parent_id, role
  (entry|sl|tp|close|house|bot), armed, status, filled_qty, reason, seq, created_ms``. Trades
  have ``trade_id, ms, price, qty, buy_order_id, sell_order_id, buy_account_id,
  sell_account_id, maker_side, buy_fee, sell_fee``. ``Result`` has ``order, trades, events,
  reason, touched_accounts, triggered_order_ids``.
* ``Broadcaster``: see ``unit/test_broadcast.py``. WS ``fill`` messages carry ``order_id``,
  ``trade_id``, ``price``, ``qty``; ``state`` messages carry the ``/api/state`` body.
* All money values are ``decimal.Decimal``; over HTTP/WS they are strings.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

# Shared pure helpers live in tests/bpt_helpers.py (importable as ``bpt_helpers``).
sys.path.insert(0, str(Path(__file__).parent))

from bpt_helpers import FakeClock  # noqa: E402

settings.register_profile(
    "gate",
    derandomize=True,
    deadline=None,
    max_examples=100,
    stateful_step_count=40,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
settings.load_profile("gate")

# A UTC day boundary, so every timeframe is aligned at the start of the tests.
T0 = 1_699_920_000_000

D = Decimal


def pytest_collection_modifyitems(config, items):
    skip_e2e = pytest.mark.skip(reason="e2e is opt-in: set BTC_E2E=1")
    skip_load = pytest.mark.skip(reason="load is opt-in: set BTC_LOAD=1")
    for item in items:
        if "e2e" in item.keywords and os.environ.get("BTC_E2E") != "1":
            item.add_marker(skip_e2e)
        if "load" in item.keywords and os.environ.get("BTC_LOAD") != "1":
            item.add_marker(skip_load)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_config(tmp_path, clock):
    """Build a test Config: sim feed in manual mode, temporary DB, fake clock."""

    def _make(**overrides):
        from btc_paper_trader.config import Config

        kwargs = dict(
            feed="sim",
            seed=7,
            db=tmp_path / f"exchange-{uuid.uuid4().hex[:8]}.db",
            bots=0,
            port=0,
            open_browser=False,
            sim_tick_ms=500,
            sim_manual=True,
            clock=clock.now,
            sleep=clock.sleep,
        )
        kwargs.update(overrides)
        return Config(**kwargs)

    return _make


@pytest.fixture
async def service(make_config):
    from btc_paper_trader.service import Service

    svc = Service(make_config())
    async with svc.running():
        yield svc


@pytest.fixture
def new_account_id():
    return lambda: uuid.uuid4().hex


@pytest.fixture
async def app(make_config):
    from btc_paper_trader.api import create_app

    application = create_app(make_config())
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    """An httpx client with its own fresh, well-formed account cookie."""
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        cookies={"account_id": uuid.uuid4().hex},
    ) as c:
        yield c


@pytest.fixture
async def make_client(app):
    """Factory for more httpx clients against the same app, each with its own account."""
    import httpx

    async with contextlib.AsyncExitStack() as stack:

        async def _make(account_id: str | None = None):
            c = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
                cookies={"account_id": account_id or uuid.uuid4().hex},
            )
            return await stack.enter_async_context(c)

        yield _make


class LoopLag:
    def __init__(self) -> None:
        self.max_ms = 0.0
        self.samples = 0


@contextlib.asynccontextmanager
async def _loop_lag(interval_s: float = 0.005):
    """Real-time heartbeat; ``max_ms`` is the worst lateness of a wake-up."""
    lag = LoopLag()

    async def beat():
        while True:
            start = time.perf_counter()
            await asyncio.sleep(interval_s)
            late = (time.perf_counter() - start - interval_s) * 1000
            lag.max_ms = max(lag.max_ms, late)
            lag.samples += 1

    task = asyncio.create_task(beat())
    try:
        await asyncio.sleep(0)
        yield lag
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.fixture
def loop_lag():
    return _loop_lag
