"""In-memory order service: place, fill, cancel, reject; positions per account and instrument."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .orders import Fill, InvalidOrder, Order, OrderError, Side


class OrderService:
    def __init__(self, max_order_quantity: int = 1_000_000) -> None:
        self._orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self._positions: dict[tuple[str, str], int] = defaultdict(int)
        self._next_id = 0
        self.max_order_quantity = max_order_quantity

    # -- commands -------------------------------------------------------------------------

    def place(
        self,
        account: str,
        instrument: str,
        side: Side,
        quantity: int,
        limit_price: Decimal | None = None,
    ) -> Order:
        if quantity <= 0:
            raise InvalidOrder(f"order quantity must be positive, got {quantity}")
        if limit_price is not None and limit_price <= 0:
            raise InvalidOrder(f"limit price must be positive, got {limit_price}")
        order_id = f"ord-{self._next_id:06d}"
        self._next_id += 1
        order = Order(order_id, account, instrument, side, quantity, limit_price)
        self._orders[order_id] = order
        if quantity > self.max_order_quantity:
            # A rejected order is kept for the audit trail, never filled.
            order.reject()
        return order

    def fill(self, order_id: str, quantity: int, price: Decimal) -> Fill:
        order = self.get(order_id)
        fill = order.apply_fill(quantity, price)
        self._fills.append(fill)
        self._positions[(order.account, order.instrument)] += order.side.sign * fill.quantity
        return fill

    def cancel(self, order_id: str) -> Order:
        order = self.get(order_id)
        order.cancel()
        return order

    # -- queries --------------------------------------------------------------------------

    def get(self, order_id: str) -> Order:
        try:
            return self._orders[order_id]
        except KeyError:
            raise OrderError(f"unknown order {order_id}") from None

    def orders(self) -> list[Order]:
        return list(self._orders.values())

    def fills(self) -> list[Fill]:
        return list(self._fills)

    def position(self, account: str, instrument: str) -> int:
        return self._positions.get((account, instrument), 0)

    def positions(self) -> dict[tuple[str, str], int]:
        return {k: v for k, v in self._positions.items() if v != 0}
