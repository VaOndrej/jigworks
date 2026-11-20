"""Sim feed: seeded GBM, 500 pre-generated candles per timeframe, manual stepping.

Contract: ``SimFeed(seed=..., start_ms=..., tick_ms=..., clock=..., sleep=...)``;
``await feed.history(tf)``; ``feed.step()`` and ``feed.push(price)`` return a tick with
``price`` (Decimal) and ``ts_ms``.
"""

from decimal import Decimal as D

import pytest

T0 = 1_699_920_000_000
TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]
TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def _feed(seed, start_ms=T0):
    from btc_paper_trader.feeds.sim import SimFeed

    async def sleep(_):
        return None

    return SimFeed(seed=seed, start_ms=start_ms, tick_ms=500, clock=lambda: start_ms, sleep=sleep)


@pytest.mark.parametrize("tf", TFS)
async def test_history_has_500_aligned_increasing_candles_per_timeframe(tf):
    candles = await _feed(7).history(tf)
    assert len(candles) == 500
    times = [c.open_time_ms for c in candles]
    assert all(t % TF_MS[tf] == 0 for t in times)
    assert times == sorted(set(times))
    assert times[-1] <= T0


async def test_history_starts_near_100000():
    candles = await _feed(7).history("1m")
    assert D("50000") < candles[-1].close < D("200000")


async def test_same_seed_and_start_give_identical_history_and_ticks():
    a, b = _feed(42), _feed(42)
    for tf in TFS:
        assert await a.history(tf) == await b.history(tf)
    ta = [a.step() for _ in range(200)]
    tb = [b.step() for _ in range(200)]
    assert [t.price for t in ta] == [t.price for t in tb]
    assert [t.ts_ms for t in ta] == [t.ts_ms for t in tb]


async def test_different_seeds_give_different_paths():
    a, b = _feed(1), _feed(2)
    assert [a.step().price for _ in range(20)] != [b.step().price for _ in range(20)]


async def test_ticks_are_positive_and_on_the_price_tick():
    feed = _feed(3)
    for _ in range(500):
        p = feed.step().price
        assert isinstance(p, D)
        assert p > 0
        assert p % D("0.01") == 0


async def test_push_returns_a_tick_at_exactly_that_price():
    feed = _feed(3)
    assert feed.push(D("101234.56")).price == D("101234.56")
