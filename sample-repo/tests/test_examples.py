"""Plain example tests: the kind an agent writes for its own code. They pass even with the
bugs in scripts/break-invariant.sh; the property tests in test_invariants.py do not."""

from decimal import Decimal

import pytest

from sample_repo import OrderService, OrderStatus, Side


def test_place_buy_and_fill_completely():
    svc = OrderService()
    order = svc.place("acc-1", "SYN-A", Side.BUY, 10)
    svc.fill(order.order_id, 10, Decimal("101.5"))
    assert order.status is OrderStatus.FILLED
    assert order.filled_quantity == 10
    assert svc.position("acc-1", "SYN-A") == 10


def test_partial_fill_then_cancel_keeps_the_fill():
    svc = OrderService()
    order = svc.place("acc-1", "SYN-A", Side.BUY, 10)
    svc.fill(order.order_id, 4, Decimal("100"))
    assert order.status is OrderStatus.PARTIALLY_FILLED
    svc.cancel(order.order_id)
    assert order.status is OrderStatus.CANCELLED
    assert svc.position("acc-1", "SYN-A") == 4


def test_sell_reduces_position():
    svc = OrderService()
    order = svc.place("acc-2", "SYN-B", Side.SELL, 5)
    svc.fill(order.order_id, 5, Decimal("20"))
    assert svc.position("acc-2", "SYN-B") == -5


def test_average_price():
    svc = OrderService()
    order = svc.place("acc-1", "SYN-A", Side.BUY, 10)
    svc.fill(order.order_id, 5, Decimal("100"))
    svc.fill(order.order_id, 5, Decimal("102"))
    assert order.average_price == Decimal("101")


def test_order_over_the_size_limit_is_rejected():
    svc = OrderService(max_order_quantity=100)
    order = svc.place("acc-1", "SYN-A", Side.BUY, 101)
    assert order.status is OrderStatus.REJECTED


def test_cancel_new_order():
    svc = OrderService()
    order = svc.place("acc-1", "SYN-C", Side.BUY, 3)
    svc.cancel(order.order_id)
    assert order.status is OrderStatus.CANCELLED


def test_non_positive_quantity_is_refused():
    svc = OrderService()
    with pytest.raises(Exception):
        svc.place("acc-1", "SYN-A", Side.BUY, 0)
