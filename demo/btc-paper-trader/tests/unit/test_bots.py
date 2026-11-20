"""Bots: seeded, deterministic, rate-limited, one scheduler task, stable accounts across restarts.

Contract: ``BotPool(n, seed)`` with ``bots`` (each has ``account_id`` and ``strategy`` in
``taker|maker|mean_reversion``). The service starts the pool when ``config.bots > 0``; the
bot scheduler uses ``config.clock``/``config.sleep``.
"""

import asyncio
import uuid
from collections import Counter
from decimal import Decimal as D

import pytest

from bpt_helpers import FakeClock


def _ids(n):
    return [f"bot-{i:04d}" for i in range(1, n + 1)]


def test_bot_accounts_are_named_bot_0001_to_bot_n():
    from btc_paper_trader.bots import BotPool

    pool = BotPool(12, seed=5)
    assert [b.account_id for b in pool.bots] == _ids(12)


def test_strategy_mix_is_40_percent_taker_40_maker_20_mean_reversion():
    from btc_paper_trader.bots import BotPool

    mix = Counter(b.strategy for b in BotPool(1000, seed=5).bots)
    assert mix == {"taker": 400, "maker": 400, "mean_reversion": 200}


async def _simulate(make_config, tmp_path, seed, bots, seconds, db=None):
    """Run a service with bots on a virtual clock: a tick every 2 s, time in 100 ms steps."""
    from btc_paper_trader.service import Service

    clock = FakeClock()
    cfg = make_config(
        bots=bots, seed=seed, clock=clock.now, sleep=clock.sleep, db=db or tmp_path / f"{uuid.uuid4().hex}.db"
    )
    svc = Service(cfg)
    async with svc.running():
        price = D("100000")
        for step in range(seconds * 10):
            if step % 20 == 0:
                price += D("7.31") if (step // 20) % 3 else D("-11.17")
                await svc.tick(price)
            await clock.advance(100)
            await svc.exchange.idle()
        records = svc.engine.to_records()
        orders = {a: list(svc.engine.orders(a, open_only=False)) for a in _ids(bots)}
        accounts = {a: svc.engine.account(a) for a in _ids(bots)}
    return cfg, records, orders, accounts


async def test_the_service_creates_n_bot_accounts_with_100_dollars(make_config, tmp_path):
    from btc_paper_trader.service import Service

    svc = Service(make_config(bots=25))
    async with svc.running():
        for a in _ids(25):
            acct = svc.engine.account(a)
            assert acct is not None
            assert acct.usd == D("100") and acct.btc == 0
        assert svc.engine.account("bot-0026") is None


async def test_bots_trade_and_the_same_seed_gives_the_same_market(make_config, tmp_path):
    _, rec1, orders1, _ = await _simulate(make_config, tmp_path, seed=9, bots=20, seconds=40)
    _, rec2, _, _ = await _simulate(make_config, tmp_path, seed=9, bots=20, seconds=40)
    assert sum(len(v) for v in orders1.values()) > 20, "bots must act about every 5 s"
    assert rec1 == rec2


async def test_different_seeds_give_different_bot_behaviour(make_config, tmp_path):
    _, rec1, _, _ = await _simulate(make_config, tmp_path, seed=1, bots=20, seconds=20)
    _, rec2, _, _ = await _simulate(make_config, tmp_path, seed=2, bots=20, seconds=20)
    assert rec1 != rec2


async def test_each_bot_acts_at_most_once_per_second(make_config, tmp_path):
    _, _, orders, _ = await _simulate(make_config, tmp_path, seed=3, bots=30, seconds=40)
    for account_id, os_ in orders.items():
        own = sorted({o.created_ms for o in os_ if o.parent_id is None})
        gaps = [b - a for a, b in zip(own, own[1:])]
        assert all(g >= 1000 for g in gaps), (account_id, gaps)


async def test_a_broke_bot_is_never_topped_up(make_config, tmp_path):
    _, _, _, accounts = await _simulate(make_config, tmp_path, seed=4, bots=20, seconds=30)
    for acct in accounts.values():
        assert acct.usd >= 0 and acct.btc >= 0
        assert acct.epoch == 0


async def test_one_scheduler_task_runs_regardless_of_the_number_of_bots(make_config):
    from btc_paper_trader.service import Service

    async def task_count(bots):
        svc = Service(make_config(bots=bots))
        async with svc.running():
            await asyncio.sleep(0)
            return len(asyncio.all_tasks())

    without = await task_count(0)
    with_many = await task_count(300)
    assert with_many - without <= 1


async def test_bot_accounts_are_the_same_after_a_restart(make_config, tmp_path):
    db = tmp_path / "bots.db"
    cfg, _, _, before = await _simulate(make_config, tmp_path, seed=6, bots=15, seconds=20, db=db)
    snapshot = {a: (v.usd, v.btc, v.usd_reserved, v.btc_reserved) for a, v in before.items()}

    from btc_paper_trader.service import Service

    clock = FakeClock(start_ms=cfg.clock() + 60_000)
    svc = Service(make_config(bots=15, seed=6, db=db, clock=clock.now, sleep=clock.sleep))
    async with svc.running():
        after = {a: svc.engine.account(a) for a in _ids(15)}
        assert {a: (v.usd, v.btc, v.usd_reserved, v.btc_reserved) for a, v in after.items()} == snapshot
        totals = svc.engine.totals()
        assert totals["usd"]["total"] == 0 and totals["btc"]["total"] == 0


@pytest.mark.parametrize("n", [0])
def test_bot_pool_of_zero_is_empty(n):
    from btc_paper_trader.bots import BotPool

    assert BotPool(n, seed=1).bots == []
