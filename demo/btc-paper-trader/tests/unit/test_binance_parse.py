import json
from decimal import Decimal as D
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_rest_klines_parse_into_decimal_candles():
    from btc_paper_trader.feeds.binance import parse_rest_klines

    candles = parse_rest_klines(_load("binance_klines_1m.json"))
    assert len(candles) == 3
    c = candles[0]
    assert c.open_time_ms == 1699919880000
    assert (c.open, c.high, c.low, c.close) == (D("36500.10"), D("36520.00"), D("36490.55"), D("36510.25"))
    assert c.volume == D("12.345")
    assert all(isinstance(v, D) for v in (c.open, c.high, c.low, c.close, c.volume))
    assert [x.open_time_ms for x in candles] == [1699919880000, 1699919940000, 1699920000000]


def test_ws_kline_update_parses_timeframe_candle_and_open_state():
    from btc_paper_trader.feeds.binance import parse_ws_kline

    u = parse_ws_kline(_load("binance_ws_kline_1m.json"))
    assert u.tf == "1m"
    assert u.closed is False
    assert u.event_ms == 1699920061234
    assert u.candle.open_time_ms == 1699920060000
    assert u.candle.close == D("36495.12")
    assert u.candle.high == D("36501.00")
    assert u.candle.volume == D("2.5")


def test_ws_kline_for_a_higher_timeframe_keeps_its_interval():
    from btc_paper_trader.feeds.binance import parse_ws_kline

    u = parse_ws_kline(_load("binance_ws_kline_1h_closed.json"))
    assert u.tf == "1h"
    assert u.closed is True
    assert u.candle.open_time_ms == 1699916400000


def test_ws_kline_accepts_the_raw_text_frame_too():
    from btc_paper_trader.feeds.binance import parse_ws_kline

    raw = (FIXTURES / "binance_ws_kline_1m.json").read_text()
    assert parse_ws_kline(raw).candle.close == D("36495.12")
