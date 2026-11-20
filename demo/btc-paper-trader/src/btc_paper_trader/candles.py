"""OHLCV candles aligned to UTC epoch multiples, in at most 500 per timeframe."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from decimal import Decimal

TIMEFRAMES: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}
MAX_CANDLES = 500


@dataclass(frozen=True, slots=True)
class Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def align(ts_ms: int, tf: str) -> int:
    ms = TIMEFRAMES[tf]
    return ts_ms // ms * ms


class CandleSeries:
    """Candles of one timeframe, oldest first, strictly increasing ``open_time_ms``."""

    def __init__(self, tf: str, limit: int = MAX_CANDLES) -> None:
        if tf not in TIMEFRAMES:
            raise ValueError(f"unknown timeframe {tf!r}")
        self.tf = tf
        self._limit = limit
        self._candles: list[Candle] = []
        self._times: list[int] = []

    def candles(self) -> list[Candle]:
        return list(self._candles)

    def last(self) -> Candle | None:
        return self._candles[-1] if self._candles else None

    def _trim(self) -> None:
        extra = len(self._candles) - self._limit
        if extra > 0:
            del self._candles[:extra]
            del self._times[:extra]

    def upsert(self, candle: Candle) -> None:
        i = bisect_left(self._times, candle.open_time_ms)
        if i < len(self._times) and self._times[i] == candle.open_time_ms:
            self._candles[i] = candle
        else:
            self._times.insert(i, candle.open_time_ms)
            self._candles.insert(i, candle)
            self._trim()

    def apply_tick(self, ts_ms: int, price: Decimal, volume: Decimal = Decimal(0)) -> Candle:
        open_time = align(ts_ms, self.tf)
        i = bisect_left(self._times, open_time)
        if i < len(self._times) and self._times[i] == open_time:
            c = self._candles[i]
            new = Candle(open_time, c.open, max(c.high, price), min(c.low, price), price, c.volume + volume)
            self._candles[i] = new
            return new
        new = Candle(open_time, price, price, price, price, volume)
        self._times.insert(i, open_time)
        self._candles.insert(i, new)
        self._trim()
        return new


def aggregate(candles: list[Candle], tf: str) -> list[Candle]:
    """Aggregate finer candles (for example 1m) into timeframe ``tf``."""
    out: list[Candle] = []
    for c in sorted(candles, key=lambda x: x.open_time_ms):
        t = align(c.open_time_ms, tf)
        if out and out[-1].open_time_ms == t:
            p = out[-1]
            out[-1] = Candle(t, p.open, max(p.high, c.high), min(p.low, c.low), c.close, p.volume + c.volume)
        else:
            out.append(Candle(t, c.open, c.high, c.low, c.close, c.volume))
    return out[-MAX_CANDLES:]
