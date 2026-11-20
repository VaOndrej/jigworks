"""Synthetic order-handling service with invariants (see INVARIANTS.md)."""

from .orders import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    Fill,
    InvalidOrder,
    InvalidTransition,
    Order,
    OrderError,
    OrderStatus,
    Overfill,
    Side,
)
from .service import OrderService

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "Fill",
    "InvalidOrder",
    "InvalidTransition",
    "Order",
    "OrderError",
    "OrderService",
    "OrderStatus",
    "Overfill",
    "Side",
]
