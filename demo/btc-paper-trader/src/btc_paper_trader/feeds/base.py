"""Feed protocol: a source of the reference price and of reference candles."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from ..candles import Candle


@dataclass(frozen=True, slots=True)
class Tick:
    price: Decimal
    ts_ms: int


OnTick = Callable[[Tick], Awaitable[None]]
OnCandle = Callable[[str, Candle], None]


class Feed(Protocol):
    name: str
    status: str  # connecting | live | stale | reconnecting
    last_tick_ms: int | None
    on_candle: OnCandle | None

    async def history(self, tf: str) -> list[Candle]: ...

    async def run(self, on_tick: OnTick) -> None: ...
