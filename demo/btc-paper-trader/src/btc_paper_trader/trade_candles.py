"""Internal OHLCV candles built from the exchange's own trades (volume = BTC qty)."""

from __future__ import annotations

from decimal import Decimal

from .candles import TIMEFRAMES, Candle, CandleSeries


class TradeCandles:
    def __init__(self) -> None:
        self._series = {tf: CandleSeries(tf) for tf in TIMEFRAMES}

    def apply_trade(self, ms: int, price: Decimal, qty: Decimal) -> None:
        for s in self._series.values():
            s.apply_tick(ms, price, volume=qty)

    def candles(self, tf: str) -> list[Candle]:
        return self._series[tf].candles()

    def last(self, tf: str) -> Candle | None:
        return self._series[tf].last()
