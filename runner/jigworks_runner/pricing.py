"""Cost from a price table with validity (design.md §8).

Cost = Σ tokens × price of the `PriceEntry` valid at the call time (the entry with the latest
`validFrom` not after the call). Cache writes and cache reads have their own prices.
The CLI's `costUSD` / `total_cost_usd` is only a cross-check (`cross_check`).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import jigworks_contracts as contracts

TOKEN_TYPES = ("input", "output", "cache_write", "cache_read")
MTOK = Decimal(1_000_000)


class UnknownPrice(LookupError):
    pass


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Price:
    model: str
    token_type: str
    per_mtok: Decimal
    valid_from: datetime


class PriceTable:
    def __init__(self, entries: Iterable[Mapping[str, Any]]) -> None:
        self._prices: dict[tuple[str, str], list[Price]] = {}
        for entry in entries:
            contracts.assert_valid("PriceEntry", dict(entry))
            price = Price(
                model=entry["model"],
                token_type=entry["tokenType"],
                per_mtok=Decimal(str(entry["pricePerMtok"])),
                valid_from=_parse_ts(entry["validFrom"]),
            )
            self._prices.setdefault((price.model, price.token_type), []).append(price)
        for prices in self._prices.values():
            prices.sort(key=lambda p: p.valid_from)

    @classmethod
    def from_file(cls, path: str | Path) -> PriceTable:
        return cls(json.loads(Path(path).read_text()))

    def price(self, model: str, token_type: str, at: datetime | str) -> Decimal:
        when = _parse_ts(at) if isinstance(at, str) else at
        valid = [p for p in self._prices.get((model, token_type), []) if p.valid_from <= when]
        if not valid:
            raise UnknownPrice(f"no {token_type} price for {model} valid at {when.isoformat()}")
        return valid[-1].per_mtok

    def cost(self, usage: Mapping[str, Any], at: datetime | str | None = None) -> Decimal:
        """API-equivalent USD cost of one UsageRecord."""
        when = at if at is not None else usage.get("at")
        if when is None:
            raise ValueError("cost needs the call time (usage.at or at=)")
        return sum(
            (Decimal(usage[t]) * self.price(usage["model"], t, when) / MTOK for t in TOKEN_TYPES),
            Decimal(0),
        )

    def total(self, usages: Iterable[Mapping[str, Any]]) -> Decimal:
        return sum((self.cost(u) for u in usages), Decimal(0))


def cross_check(table: PriceTable, usages: Iterable[Mapping[str, Any]], tolerance: Decimal = Decimal("0.000001")) -> dict[str, Any]:
    """Compare our cost with the CLI's own cliCostUsd. Never used for billing."""
    usages = list(usages)
    ours = table.total(usages)
    cli = sum((Decimal(str(u.get("cliCostUsd", 0))) for u in usages), Decimal(0))
    return {"ours": ours, "cli": cli, "delta": ours - cli, "match": abs(ours - cli) <= tolerance}
