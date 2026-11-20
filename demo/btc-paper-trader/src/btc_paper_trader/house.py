"""House market maker: the ladder of post-only quotes around the reference price."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import ceil_price, floor_price

BPS = Decimal(10_000)


@dataclass(frozen=True)
class HouseConfig:
    levels: int = 10
    spread_bps: int = 10
    step_bps: int = 5
    level_qty: Decimal = Decimal("0.01")
    usd: Decimal = Decimal("200000")  # starting inventory, issued once on the first start
    btc: Decimal = Decimal("2")


def ladder(cfg: HouseConfig, ref: Decimal) -> tuple[list[Decimal], list[Decimal]]:
    """``(bid_prices, ask_prices)``, nearest to the reference first."""
    half = Decimal(cfg.spread_bps) / 2
    bids, asks = [], []
    for i in range(cfg.levels):
        offset = (half + i * cfg.step_bps) / BPS
        bids.append(floor_price(ref * (1 - offset)))
        asks.append(ceil_price(ref * (1 + offset)))
    return bids, asks
