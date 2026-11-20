from decimal import Decimal as D

import pytest

T0 = 1_699_920_000_000  # a UTC day boundary
MIN = 60_000


def test_timeframes_are_the_six_named_intervals_in_ms():
    from btc_paper_trader.candles import TIMEFRAMES

    assert dict(TIMEFRAMES) == {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }


def test_apply_tick_aligns_open_time_to_the_utc_interval():
    from btc_paper_trader.candles import CandleSeries

    s = CandleSeries("5m")
    s.apply_tick(T0 + 7 * MIN + 1234, D("100"))
    (c,) = s.candles()
    assert c.open_time_ms == T0 + 5 * MIN


def test_ticks_in_one_interval_build_ohlc_and_a_new_interval_starts_a_new_candle():
    from btc_paper_trader.candles import CandleSeries

    s = CandleSeries("1m")
    for ts, p in [(0, "100"), (10_000, "105"), (20_000, "95"), (59_999, "101"), (60_000, "102")]:
        s.apply_tick(T0 + ts, D(p))
    first, second = s.candles()
    assert (first.open, first.high, first.low, first.close) == (D("100"), D("105"), D("95"), D("101"))
    assert first.open_time_ms == T0
    assert second.open_time_ms == T0 + MIN
    assert second.open == second.close == D("102")


def test_apply_tick_adds_volume():
    from btc_paper_trader.candles import CandleSeries

    s = CandleSeries("1m")
    s.apply_tick(T0, D("100"), volume=D("0.5"))
    s.apply_tick(T0 + 1, D("101"), volume=D("0.25"))
    (c,) = s.candles()
    assert c.volume == D("0.75")


def test_upsert_replaces_the_candle_with_the_same_open_time():
    from btc_paper_trader.candles import Candle, CandleSeries

    s = CandleSeries("1m")
    s.upsert(Candle(T0, D("1"), D("2"), D("1"), D("2"), D("0")))
    s.upsert(Candle(T0, D("1"), D("3"), D("1"), D("3"), D("1")))
    (c,) = s.candles()
    assert c.high == D("3")


def test_series_keeps_at_most_500_candles_newest_last():
    from btc_paper_trader.candles import CandleSeries

    s = CandleSeries("1m")
    for i in range(650):
        s.apply_tick(T0 + i * MIN, D(100 + i))
    out = s.candles()
    assert len(out) == 500
    assert out[-1].open_time_ms == T0 + 649 * MIN
    assert out[0].open_time_ms == T0 + 150 * MIN


@pytest.mark.parametrize("tf", ["5m", "15m", "1h"])
def test_aggregate_of_1m_equals_building_the_timeframe_directly(tf):
    from btc_paper_trader.candles import CandleSeries, aggregate

    one = CandleSeries("1m")
    direct = CandleSeries(tf)
    for i in range(240):
        ts = T0 + i * 15_000 + 3
        price = D(1000 + (i * 37) % 101)
        one.apply_tick(ts, price, volume=D("0.001"))
        direct.apply_tick(ts, price, volume=D("0.001"))
    assert aggregate(one.candles(), tf) == direct.candles()
