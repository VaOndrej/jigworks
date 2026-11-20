"""Internal OHLCV candles from the exchange's own trades (volume = BTC qty).

Contract: ``TradeCandles()`` with ``apply_trade(ms, price, qty)`` and ``candles(tf)``.
"""

from decimal import Decimal as D

from bpt_helpers import MAKER, T0, USER_A, engine, limit, maker, market, user


def test_trades_build_ohlcv_per_interval():
    from btc_paper_trader.trade_candles import TradeCandles

    tc = TradeCandles()
    tc.apply_trade(T0 + 1_000, D("100"), D("0.1"))
    tc.apply_trade(T0 + 2_000, D("105"), D("0.2"))
    tc.apply_trade(T0 + 3_000, D("98"), D("0.3"))
    tc.apply_trade(T0 + 4_000, D("101"), D("0.4"))
    (c,) = tc.candles("1m")
    assert c.open_time_ms == T0
    assert (c.open, c.high, c.low, c.close, c.volume) == (D("100"), D("105"), D("98"), D("101"), D("1.0"))


def test_intervals_without_trades_have_no_candle():
    from btc_paper_trader.trade_candles import TradeCandles

    tc = TradeCandles()
    tc.apply_trade(T0, D("100"), D("0.1"))
    tc.apply_trade(T0 + 5 * 60_000, D("101"), D("0.1"))
    assert [c.open_time_ms for c in tc.candles("1m")] == [T0, T0 + 5 * 60_000]


def test_all_six_timeframes_are_built():
    from btc_paper_trader.trade_candles import TradeCandles

    tc = TradeCandles()
    tc.apply_trade(T0 + 3_700_000, D("100"), D("0.1"))
    for tf, ms in {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}.items():
        (c,) = tc.candles(tf)
        assert c.open_time_ms == (T0 + 3_700_000) // ms * ms


def test_engine_trades_feed_the_internal_candles_with_the_trade_qty_as_volume():
    from btc_paper_trader.trade_candles import TradeCandles

    eng = engine()
    user(eng)
    maker(eng)
    limit(eng, MAKER, "sell", "0.0002", "100000")
    limit(eng, MAKER, "sell", "0.0002", "100010")
    r = market(eng, USER_A, "buy", "0.0003", now=T0 + 10)
    tc = TradeCandles()
    for t in r.trades:
        tc.apply_trade(t.ms, t.price, t.qty)
    (c,) = tc.candles("1m")
    assert c.volume == D("0.0003")
    assert (c.open, c.close) == (D("100000"), D("100010"))
