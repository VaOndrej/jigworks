"""Binance feed: reconnect backoff, history refetch and REST fallback, all without network.

Contract: ``BinanceFeed(base=..., fallback_base=..., http=httpx.AsyncClient, ws_connect=..., clock=...,
sleep=...)``. ``ws_connect(url)`` returns an async context manager yielding an async iterator of
text frames (the shape of ``websockets.connect``). ``await feed.run(on_tick)`` loops forever and
calls ``await on_tick(tick)`` (``tick.price``, ``tick.ts_ms``) for every 1m kline update. It must
re-raise ``CancelledError``; the fake sleep uses that to stop the loop.
"""

import asyncio
import json
from decimal import Decimal as D
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"
KLINES = json.loads((FIXTURES / "binance_klines_1m.json").read_text())
WS_1M = (FIXTURES / "binance_ws_kline_1m.json").read_text()
WS_1H = (FIXTURES / "binance_ws_kline_1h_closed.json").read_text()


class _Conn:
    def __init__(self, action):
        self.action = action

    async def __aenter__(self):
        if self.action == "fail":
            raise OSError("connection refused (fake)")
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for msg in self.action:
            await asyncio.sleep(0)
            yield msg


class FakeConnector:
    def __init__(self, script):
        self.script = list(script)
        self.urls = []

    def __call__(self, url, *args, **kwargs):
        self.urls.append(url)
        action = self.script.pop(0) if self.script else "fail"
        return _Conn(action)


class StopAfter:
    """Fake sleep: records delays, raises CancelledError after ``n`` of them."""

    def __init__(self, n, feed_ref=None):
        self.n = n
        self.delays = []
        self.statuses = []
        self.feed = None

    async def __call__(self, seconds):
        self.delays.append(seconds)
        if self.feed is not None:
            self.statuses.append(self.feed.status)
        await asyncio.sleep(0)
        if len(self.delays) >= self.n:
            raise asyncio.CancelledError()


def _transport(requests, fail_hosts=()):
    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.host in fail_hosts:
            return httpx.Response(503, json={"msg": "unavailable"})
        return httpx.Response(200, json=KLINES)

    return httpx.MockTransport(handler)


def _feed(connector, sleep, requests, fail_hosts=(), base="https://api.binance.com"):
    from btc_paper_trader.feeds.binance import BinanceFeed

    http = httpx.AsyncClient(transport=_transport(requests, fail_hosts))
    feed = BinanceFeed(
        base=base,
        fallback_base="https://data-api.binance.vision",
        http=http,
        ws_connect=connector,
        clock=lambda: 1_699_920_061_300,
        sleep=sleep,
    )
    sleep.feed = feed
    return feed


async def _noop_tick(tick):
    return None


async def test_failed_connects_back_off_1_2_4_8_16_30_then_stay_at_30():
    sleep = StopAfter(8)
    feed = _feed(FakeConnector([]), sleep, [])
    with pytest.raises(asyncio.CancelledError):
        await feed.run(_noop_tick)
    assert sleep.delays == [1, 2, 4, 8, 16, 30, 30, 30]


async def test_backoff_resets_to_1_after_a_successful_connect():
    sleep = StopAfter(9)
    script = ["fail"] * 6 + [[WS_1M]]  # then fail forever
    feed = _feed(FakeConnector(script), sleep, [])
    with pytest.raises(asyncio.CancelledError):
        await feed.run(_noop_tick)
    assert sleep.delays == [1, 2, 4, 8, 16, 30, 1, 2, 4]


async def test_status_is_reconnecting_while_backing_off_and_live_after_a_tick():
    sleep = StopAfter(2)
    ticks = []

    async def on_tick(tick):
        ticks.append(tick)
        assert feed.status == "live"

    feed = _feed(FakeConnector([[WS_1M]]), sleep, [])
    with pytest.raises(asyncio.CancelledError):
        await feed.run(on_tick)
    assert ticks, "a 1m kline update must be delivered as a reference tick"
    assert set(sleep.statuses) == {"reconnecting"}


async def test_only_1m_updates_become_reference_ticks():
    sleep = StopAfter(1)
    ticks = []

    async def on_tick(tick):
        ticks.append(tick)

    feed = _feed(FakeConnector([[WS_1H, WS_1M, WS_1H]]), sleep, [])
    with pytest.raises(asyncio.CancelledError):
        await feed.run(on_tick)
    assert len(ticks) == 1
    assert ticks[0].price == D("36495.12")
    assert isinstance(ticks[0].ts_ms, int)


async def test_every_reconnect_refetches_history():
    requests = []
    seen_at_first_disconnect = []

    class RecordingSleep(StopAfter):
        async def __call__(self, seconds):
            if not seen_at_first_disconnect:
                seen_at_first_disconnect.append(len(requests))
            await super().__call__(seconds)

    feed = _feed(FakeConnector([[WS_1M], [WS_1M]]), RecordingSleep(3), requests)
    with pytest.raises(asyncio.CancelledError):
        await feed.run(_noop_tick)
    kline_requests = [r for r in requests if r.url.path == "/api/v3/klines"]
    assert len(kline_requests) > seen_at_first_disconnect[0]
    intervals = {r.url.params["interval"] for r in kline_requests}
    assert intervals == {"1m", "5m", "15m", "1h", "4h", "1d"}


async def test_history_uses_the_configured_base_with_btcusdt_and_limit_500():
    requests = []
    feed = _feed(FakeConnector([]), StopAfter(1), requests, base="https://binance-base.example")
    candles = await feed.history("15m")
    assert len(candles) == 3
    (r,) = requests
    assert r.url.host == "binance-base.example"
    assert r.url.path == "/api/v3/klines"
    assert r.url.params["symbol"] == "BTCUSDT"
    assert r.url.params["interval"] == "15m"
    assert r.url.params["limit"] == "500"


async def test_history_falls_back_to_data_api_binance_vision_when_the_base_fails():
    requests = []
    feed = _feed(FakeConnector([]), StopAfter(1), requests, fail_hosts={"api.binance.com"})
    candles = await feed.history("1m")
    assert [c.open_time_ms for c in candles] == [1699919880000, 1699919940000, 1699920000000]
    assert requests[-1].url.host == "data-api.binance.vision"


async def test_websocket_uses_the_combined_kline_stream_for_all_six_timeframes():
    connector = FakeConnector([])
    feed = _feed(connector, StopAfter(1), [])
    with pytest.raises(asyncio.CancelledError):
        await feed.run(_noop_tick)
    url = connector.urls[0]
    assert "stream" in url
    for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
        assert f"btcusdt@kline_{tf}" in url
