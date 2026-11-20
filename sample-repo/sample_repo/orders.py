"""Order model and the order state machine.

Synthetic only: instruments are made-up symbols (``SYN-A`` …), accounts are made-up ids.
Quantities are whole lots (``int``); prices are ``Decimal``. The invariants this module
must keep are listed in ``INVARIANTS.md`` and guarded by ``tests/test_invariants.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATES


TERMINAL_STATES = frozenset({OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED})

# I3: the only allowed transitions. Terminal states have no outgoing edge.
ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.NEW: frozenset(
        {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED}
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
}


class OrderError(Exception):
    """Base class for rejected operations. The order is left unchanged."""


class InvalidTransition(OrderError):
    pass


class Overfill(OrderError):
    pass


class InvalidOrder(OrderError):
    pass


@dataclass(frozen=True)
class Fill:
    order_id: str
    seq: int
    quantity: int
    price: Decimal


@dataclass
class Order:
    order_id: str
    account: str
    instrument: str
    side: Side
    quantity: int
    limit_price: Decimal | None = None
    status: OrderStatus = OrderStatus.NEW
    fills: list[Fill] = field(default_factory=list)

    @property
    def filled_quantity(self) -> int:
        return sum(f.quantity for f in self.fills)

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled_quantity

    @property
    def average_price(self) -> Decimal | None:
        filled = self.filled_quantity
        if filled == 0:
            return None
        return sum((f.price * f.quantity for f in self.fills), Decimal(0)) / filled

    def _transition(self, new_status: OrderStatus) -> None:
        if new_status not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidTransition(f"{self.order_id}: {self.status.value} -> {new_status.value}")
        self.status = new_status

    def apply_fill(self, quantity: int, price: Decimal) -> Fill:
        if self.status.is_terminal:
            raise InvalidTransition(f"{self.order_id}: cannot fill a {self.status.value} order")
        if quantity <= 0:
            raise InvalidOrder(f"{self.order_id}: fill quantity must be positive, got {quantity}")
        if price <= 0:
            raise InvalidOrder(f"{self.order_id}: fill price must be positive, got {price}")
        if quantity > self.remaining:
            raise Overfill(f"{self.order_id}: fill {quantity} exceeds remaining {self.remaining}")
        if self.limit_price is not None:
            worse = price > self.limit_price if self.side is Side.BUY else price < self.limit_price
            if worse:
                raise InvalidOrder(f"{self.order_id}: fill price {price} breaches limit {self.limit_price}")
        fill = Fill(order_id=self.order_id, seq=len(self.fills), quantity=quantity, price=price)
        self.fills.append(fill)
        self._transition(OrderStatus.FILLED if self.remaining == 0 else OrderStatus.PARTIALLY_FILLED)
        return fill

    def cancel(self) -> None:
        self._transition(OrderStatus.CANCELLED)

    def reject(self) -> None:
        self._transition(OrderStatus.REJECTED)
