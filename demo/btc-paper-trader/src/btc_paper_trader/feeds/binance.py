"""Binance BTCUSDT reference feed: REST klines for history, the combined kline WebSocket for ticks.

All I/O is injected (``http`` is an ``httpx.AsyncClient``, ``ws_connect`` behaves like
``websockets.connect``), so tests never touch the network. Parsing is pure.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

import httpx

from ..candles import TIMEFRAMES, Candle
from ..config import DEFAULT_BINANCE_BASE, FALLBACK_BINANCE_BASE
from ..logs import log_event
from .base import OnCandle, OnTick, Tick

SYMBOL = "BTCUSDT"
WS_BASE = "wss://stream.binance.com:9443"
BACKOFF_START_S = 1
BACKOFF_MAX_S = 30
HTTP_TIMEOUT_S = 10
WS_IDLE_TIMEOUT_S = 30


@dataclass(frozen=True, slots=True)
class WsKline:
    tf: str
    candle: Candle
    closed: bool
    event_ms: int


def parse_rest_klines(rows: list) -> list[Candle]:
    """Binance REST kline rows: ``[open_time, o, h, l, c, volume, ...]``."""
    return [Candle(int(r[0]), Decimal(r[1]), Decimal(r[2]), Decimal(r[3]), Decimal(r[4]), Decimal(r[5])) for r in rows]


def parse_ws_kline(raw: str | bytes | dict) -> WsKline:
    """A combined-stream frame (``{"stream", "data"}``) or a bare kline event."""
    msg = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    data = msg.get("data", msg)
    k = data["k"]
    candle = Candle(int(k["t"]), Decimal(k["o"]), Decimal(k["h"]), Decimal(k["l"]), Decimal(k["c"]), Decimal(k["v"]))
    return WsKline(k["i"], candle, bool(k["x"]), int(data["E"]))


def stream_url(ws_base: str = WS_BASE) -> str:
    streams = "/".join(f"{SYMBOL.lower()}@kline_{tf}" for tf in TIMEFRAMES)
    return f"{ws_base}/stream?streams={streams}"


def _default_ws_connect(url: str):
    import websockets

    return websockets.connect(url, open_timeout=HTTP_TIMEOUT_S, ping_interval=20)


class BinanceFeed:
    name = "binance"

    def __init__(
        self,
        base: str = DEFAULT_BINANCE_BASE,
        fallback_base: str = FALLBACK_BINANCE_BASE,
        http: httpx.AsyncClient | None = None,
        ws_connect: Callable | None = None,
        clock: Callable[[], int] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        ws_base: str = WS_BASE,
    ) -> None:
        from ..config import real_clock

        self.base = base.rstrip("/")
        self.fallback_base = fallback_base.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)
        self._ws_connect = ws_connect or _default_ws_connect
        self._clock = clock or real_clock
        self._sleep = sleep
        self._ws_base = ws_base
        self.status = "connecting"
        self.last_tick_ms: int | None = None
        self.on_candle: OnCandle | None = None
        self.on_history: Callable[[str, list[Candle]], None] | None = None

    async def _get_klines(self, base: str, tf: str) -> list[Candle]:
        async with asyncio.timeout(HTTP_TIMEOUT_S):
            r = await self._http.get(
                f"{base}/api/v3/klines", params={"symbol": SYMBOL, "interval": tf, "limit": "500"}
            )
        r.raise_for_status()
        return parse_rest_klines(r.json())

    async def history(self, tf: str) -> list[Candle]:
        try:
            return await self._get_klines(self.base, tf)
        except (httpx.HTTPError, TimeoutError, ValueError):
            return await self._get_klines(self.fallback_base, tf)

    async def fetch_all_history(self) -> dict[str, list[Candle]]:
        results = await asyncio.gather(*(self.history(tf) for tf in TIMEFRAMES))
        return dict(zip(TIMEFRAMES, results, strict=True))

    async def run(self, on_tick: OnTick) -> None:
        """Connect, stream, and reconnect forever with backoff 1 -> 30 s; refetch history each time."""
        delay = BACKOFF_START_S
        attempt = 0
        while True:
            attempt += 1
            try:
                history = await self.fetch_all_history()
                if self.on_history is not None:
                    for tf, candles in history.items():
                        self.on_history(tf, candles)
                async with self._ws_connect(stream_url(self._ws_base)) as ws:
                    delay = BACKOFF_START_S
                    self.status = "live"
                    log_event("feed.connected", feed=self.name, attempt=attempt)
                    await self._stream(ws, on_tick)
                log_event("feed.disconnected", feed=self.name, reason="stream ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event("feed.disconnected", feed=self.name, reason=repr(exc))
            self.status = "reconnecting"
            log_event("feed.reconnect", feed=self.name, attempt=attempt, delay_s=delay)
            await self._sleep(delay)
            delay = min(delay * 2, BACKOFF_MAX_S)

    async def _stream(self, ws, on_tick: OnTick) -> None:
        frames = ws.__aiter__()
        while True:
            try:
                async with asyncio.timeout(WS_IDLE_TIMEOUT_S):
                    raw = await frames.__anext__()
            except StopAsyncIteration:
                return
            update = parse_ws_kline(raw)
            if self.on_candle is not None:
                self.on_candle(update.tf, update.candle)
            if update.tf == "1m":
                self.status = "live"
                ts = self._clock()
                self.last_tick_ms = ts
                await on_tick(Tick(update.candle.close, ts))
