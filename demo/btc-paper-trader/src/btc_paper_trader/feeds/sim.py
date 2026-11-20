"""Deterministic sim feed: a seeded geometric random walk.

History is 500 pre-generated candles per timeframe; live ticks continue from the last 1m close.
The same ``seed`` and ``start_ms`` always give the same candles and ticks. Floats are used only
inside the generator and are quantized to ``Decimal`` before anything leaves it.
"""

from __future__ import annotations

import math
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal

from ..candles import MAX_CANDLES, TIMEFRAMES, Candle
from ..money import PRICE_TICK
from .base import OnCandle, OnTick, Tick

START_PRICE = 100_000.0
TICK_SIGMA = 0.0003  # per live tick (about 0.3% per minute at 500 ms)
CANDLE_SIGMA = 0.0006  # per sub-step inside a history candle
STEPS_PER_CANDLE = 4


def _q(x: float) -> Decimal:
    return Decimal(repr(round(x, 4))).quantize(PRICE_TICK)


class SimFeed:
    name = "sim"

    def __init__(
        self,
        seed: int,
        start_ms: int,
        tick_ms: int,
        clock: Callable[[], int],
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        self.seed = seed
        self.start_ms = start_ms
        self.tick_ms = tick_ms
        self._clock = clock
        self._sleep = sleep
        self.status = "connecting"
        self.last_tick_ms: int | None = None
        self.on_candle: OnCandle | None = None
        self._history = {tf: self._generate(tf, i) for i, tf in enumerate(TIMEFRAMES)}
        self._price = float(self._history["1m"][-1].close)
        self._rng = random.Random(f"{seed}:live")  # nosec B311 - seeded simulation, not security

    def _generate(self, tf: str, index: int) -> list[Candle]:
        rng = random.Random(f"{self.seed}:{tf}")  # nosec B311 - seeded simulation, not security
        ms = TIMEFRAMES[tf]
        first = (self.start_ms // ms - (MAX_CANDLES - 1)) * ms
        sigma = CANDLE_SIGMA * math.sqrt(ms / 60_000)
        price, raw = 1.0, []
        for i in range(MAX_CANDLES):
            o, hi, lo = price, price, price
            for _ in range(STEPS_PER_CANDLE):
                price *= math.exp(rng.gauss(0, sigma))
                hi, lo = max(hi, price), min(lo, price)
            raw.append((first + i * ms, o, hi, lo, price, rng.random() * 5))
        scale = START_PRICE / raw[-1][4]  # end the series at the start price
        return [
            Candle(t, _q(o * scale), _q(h * scale), _q(l * scale), _q(c * scale), Decimal(repr(round(v, 5))))
            for t, o, h, l, c, v in raw
        ]

    async def history(self, tf: str) -> list[Candle]:
        return list(self._history[tf])

    def push(self, price: Decimal) -> Tick:
        self._price = float(price)
        self.status = "live"
        ts = self._clock()
        self.last_tick_ms = ts
        return Tick(price, ts)

    def step(self) -> Tick:
        self._price *= math.exp(self._rng.gauss(0, TICK_SIGMA))
        price = max(_q(self._price), Decimal("1000"))
        return self.push(price)

    async def run(self, on_tick: OnTick) -> None:
        while True:
            await on_tick(self.step())
            await self._sleep(self.tick_ms / 1000)
