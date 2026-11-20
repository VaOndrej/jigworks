"""Runtime configuration. ``clock`` and ``sleep`` are injected so tests run without real waits."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_BINANCE_BASE = "https://api.binance.com"
FALLBACK_BINANCE_BASE = "https://data-api.binance.vision"
DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "exchange.db"


def real_clock() -> int:
    """Epoch milliseconds."""
    return time.time_ns() // 1_000_000


@dataclass
class Config:
    feed: str = "binance"  # binance | sim
    seed: int = 0
    db: Path = DEFAULT_DB
    bots: int = 0
    port: int = 8000
    open_browser: bool = True
    binance_base: str = DEFAULT_BINANCE_BASE
    sim_tick_ms: int = 500
    sim_manual: bool = False  # the sim feed never ticks on its own; tests call ``service.tick``
    clock: Callable[[], int] = real_clock
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    queue_maxsize: int = 10_000
    ack_timeout_s: float = 5.0
    house_usd: Decimal = Decimal("200000")
    house_btc: Decimal = Decimal("2")
    house_levels: int = 10
    house_spread_bps: int = 10
    extra: dict = field(default_factory=dict)

    @property
    def host(self) -> str:
        return HOST
