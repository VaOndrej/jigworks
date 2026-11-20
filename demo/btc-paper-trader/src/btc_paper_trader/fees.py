"""Fee schedule and the USD reservation for an open buy."""

from __future__ import annotations

from decimal import Decimal

from .money import QTY_STEP, USD_Q, ceil_usd

MAKER = Decimal("0.0005")
TAKER = Decimal("0.001")


def fee(qty: Decimal, price: Decimal, rate: Decimal) -> Decimal:
    """``ceil_usd(qty * price * rate)``, charged per trade in USD."""
    return ceil_usd(qty * price * rate)


def buy_reservation(rem_qty: Decimal, limit: Decimal) -> Decimal:
    """USD reserved by an open buy: notional + max (taker) fee + 1e-8 per qty step.

    The per-step buffer guarantees per-trade fee rounding can never push the available USD
    below zero across many partial fills.
    """
    if rem_qty <= 0:
        return Decimal(0)
    notional = rem_qty * limit
    return notional + ceil_usd(notional * TAKER) + (rem_qty / QTY_STEP) * USD_Q
