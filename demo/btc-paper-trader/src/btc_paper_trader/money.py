"""Money quanta, strict parsing and rounding helpers. Every value is a ``Decimal``."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation

QTY_STEP = Decimal("0.00001")
PRICE_TICK = Decimal("0.01")
USD_Q = Decimal("0.00000001")
MIN_NOTIONAL = Decimal("1")

ZERO = Decimal(0)


class MoneyError(ValueError):
    """A value that cannot be accepted; ``reason`` is the API rejection reason."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def to_decimal(raw: object) -> Decimal:
    """Convert str / int / Decimal to a finite Decimal. Floats are refused."""
    if isinstance(raw, (bool, float)):
        raise MoneyError("invalid_order", f"not an exact number: {raw!r}")
    try:
        value = raw if isinstance(raw, Decimal) else Decimal(str(raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError("invalid_order", f"not a number: {raw!r}") from exc
    if not value.is_finite():
        raise MoneyError("invalid_order", f"not finite: {raw!r}")
    return value


def on_step(value: Decimal, step: Decimal) -> bool:
    return value % step == 0


def _parse(raw: object, step: Decimal) -> Decimal:
    value = to_decimal(raw)
    if value < 0:
        raise MoneyError("invalid_order", f"negative value: {raw!r}")
    if not on_step(value, step):
        raise MoneyError("invalid_precision", f"{raw!r} is not a multiple of {step}")
    return value


def parse_qty(raw: object) -> Decimal:
    return _parse(raw, QTY_STEP)


def parse_price(raw: object) -> Decimal:
    return _parse(raw, PRICE_TICK)


def parse_usd(raw: object) -> Decimal:
    return _parse(raw, USD_Q)


def _floor(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def floor_qty(value: Decimal) -> Decimal:
    return _floor(value, QTY_STEP)


def floor_price(value: Decimal) -> Decimal:
    return _floor(value, PRICE_TICK)


def ceil_price(value: Decimal) -> Decimal:
    return _ceil(value, PRICE_TICK)


def ceil_usd(value: Decimal) -> Decimal:
    return _ceil(value, USD_Q)


def floor_usd(value: Decimal) -> Decimal:
    return _floor(value, USD_Q)


def dstr(value: Decimal | None) -> str | None:
    """Canonical plain-text form: no exponent, no trailing zeros ('0' for zero)."""
    if value is None:
        return None
    if value == 0:
        return "0"
    return format(value.normalize(), "f")
