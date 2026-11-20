"""Order book: price levels with FIFO queues (price-time priority). Pure, no I/O."""

from __future__ import annotations

from bisect import bisect_left, insort
from collections import deque
from collections.abc import Iterator
from decimal import Decimal


class OrderBook:
    """Resting limit orders. Orders only need ``side``, ``price``, ``qty`` and ``filled_qty``."""

    def __init__(self) -> None:
        self._levels: dict[str, dict[Decimal, deque]] = {"buy": {}, "sell": {}}
        self._prices: dict[str, list[Decimal]] = {"buy": [], "sell": []}  # ascending

    # --- mutation ---------------------------------------------------------------------------

    def add(self, order) -> None:
        level = self._levels[order.side].get(order.price)
        if level is None:
            level = self._levels[order.side][order.price] = deque()
            insort(self._prices[order.side], order.price)
        level.append(order)

    def remove(self, order) -> None:
        level = self._levels[order.side].get(order.price)
        if level is None:
            return
        try:
            level.remove(order)
        except ValueError:
            return
        if not level:
            del self._levels[order.side][order.price]
            prices = self._prices[order.side]
            del prices[bisect_left(prices, order.price)]

    # --- read side --------------------------------------------------------------------------

    def best_bid(self) -> Decimal | None:
        prices = self._prices["buy"]
        return prices[-1] if prices else None

    def best_ask(self) -> Decimal | None:
        prices = self._prices["sell"]
        return prices[0] if prices else None

    def first(self, side: str):
        """The highest-priority resting order of ``side`` (the best price, then the earliest)."""
        prices = self._prices[side]
        if not prices:
            return None
        price = prices[-1] if side == "buy" else prices[0]
        return self._levels[side][price][0]

    def _ordered_prices(self, side: str) -> Iterator[Decimal]:
        prices = self._prices[side]
        return reversed(prices) if side == "buy" else iter(prices)

    def levels(self, side: str, depth: int) -> list[tuple[Decimal, Decimal]]:
        """``[(price, total_remaining_qty)]``, best price first."""
        out: list[tuple[Decimal, Decimal]] = []
        for price in self._ordered_prices(side):
            if len(out) >= depth:
                break
            out.append((price, sum((o.qty - o.filled_qty for o in self._levels[side][price]), Decimal(0))))
        return out

    def iter_makers(self, side: str) -> Iterator:
        """Resting orders of ``side`` best price first, then in time order."""
        for price in list(self._ordered_prices(side)):
            yield from list(self._levels[side][price])

    def is_crossed(self) -> bool:
        bid, ask = self.best_bid(), self.best_ask()
        return bid is not None and ask is not None and bid >= ask
