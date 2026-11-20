"""Invariant 16: candle properties for reference candles (CandleSeries, sim history) and
internal candles (TradeCandles)."""

import asyncio
from decimal import Decimal as D

import pytest
from hypothesis import given
from hypothesis import strategies as st

T0 = 1_699_920_000_000
TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}

ticks = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=3 * 86_400_000),  # time offset
        st.integers(min_value=1, max_value=20_000_000),  # price in cents
        st.integers(min_value=0, max_value=100_000),  # volume in 1e-5 BTC
    ),
    min_size=1,
    max_size=300,
)


def _check(candles, tf):
    times = [c.open_time_ms for c in candles]
    assert times == sorted(times)
    assert len(set(times)) == len(times)
    for c in candles:
        assert c.open_time_ms % TF_MS[tf] == 0
        assert c.high >= max(c.open, c.close)
        assert c.low <= min(c.open, c.close)
        assert c.volume >= 0


def _sorted(raw):
    return sorted(((T0 + dt, D(p) / 100, D(v) / 100_000) for dt, p, v in raw), key=lambda x: x[0])


@pytest.mark.parametrize("tf", list(TF_MS))
@given(raw=ticks)
def test_reference_series_candles_are_well_formed(tf, raw):
    from btc_paper_trader.candles import CandleSeries

    s = CandleSeries(tf)
    for ts, p, v in _sorted(raw):
        s.apply_tick(ts, p, volume=v)
    out = s.candles()
    _check(out, tf)
    assert len(out) <= 500


@pytest.mark.parametrize("tf", ["5m", "15m", "1h", "4h", "1d"])
@given(raw=ticks)
def test_aggregating_1m_equals_building_directly(tf, raw):
    from btc_paper_trader.candles import CandleSeries, aggregate

    one, direct = CandleSeries("1m"), CandleSeries(tf)
    for ts, p, v in _sorted(raw):
        one.apply_tick(ts, p, volume=v)
        direct.apply_tick(ts, p, volume=v)
    if len(one.candles()) < 500:  # the 1m window must cover the whole range
        assert aggregate(one.candles(), tf) == direct.candles()


@pytest.mark.parametrize("tf", list(TF_MS))
@given(raw=ticks)
def test_internal_trade_candles_are_well_formed(tf, raw):
    from btc_paper_trader.trade_candles import TradeCandles

    tc = TradeCandles()
    for ts, p, v in _sorted(raw):
        tc.apply_trade(ts, p, v)
    _check(tc.candles(tf), tf)


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_sim_history_candles_are_well_formed(seed):
    from btc_paper_trader.feeds.sim import SimFeed

    async def sleep(_):
        return None

    feed = SimFeed(seed=seed, start_ms=T0, tick_ms=500, clock=lambda: T0, sleep=sleep)

    async def all_tfs():
        return {tf: await feed.history(tf) for tf in TF_MS}

    for tf, candles in asyncio.run(all_tfs()).items():
        assert len(candles) == 500
        _check(candles, tf)
