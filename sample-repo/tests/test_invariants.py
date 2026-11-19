"""Hypothesis property tests, one group per invariant in INVARIANTS.md (I1–I7), plus a
stateful model test that checks all of them after every random operation."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import (
    Bundle,
    RuleBasedStateMachine,
    invariant,
    rule,
)

from sample_repo import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    InvalidTransition,
    OrderError,
    OrderService,
    OrderStatus,
    Overfill,
    Side,
)

ACCOUNTS = st.sampled_from(["acc-1", "acc-2", "acc-3"])
INSTRUMENTS = st.sampled_from(["SYN-A", "SYN-B", "SYN-C"])
SIDES = st.sampled_from(list(Side))
QUANTITIES = st.integers(min_value=1, max_value=50)
PRICES = st.decimals(min_value=Decimal("1.00"), max_value=Decimal("200.00"), places=2)
LIMITS = st.none() | PRICES


# --- the invariants as plain checks ----------------------------------------------------


def check_i1(svc: OrderService) -> None:
    for o in svc.orders():
        assert 0 <= o.filled_quantity <= o.quantity, f"I1 broken on {o.order_id}"


def check_i2(svc: OrderService) -> None:
    expected: dict[tuple[str, str], int] = defaultdict(int)
    by_id = {o.order_id: o for o in svc.orders()}
    for f in svc.fills():
        o = by_id[f.order_id]
        expected[(o.account, o.instrument)] += o.side.sign * f.quantity
    keys = set(expected) | set(svc.positions())
    for account, instrument in keys:
        assert svc.position(account, instrument) == expected[(account, instrument)], (
            f"I2 broken for {account}/{instrument}"
        )


def check_i4(svc: OrderService) -> None:
    for o in svc.orders():
        filled = o.filled_quantity
        assert (o.status is OrderStatus.FILLED) == (filled == o.quantity), f"I4 broken on {o.order_id}"
        if o.status is OrderStatus.PARTIALLY_FILLED:
            assert 0 < filled < o.quantity, f"I4 broken on {o.order_id}"
        if o.status in (OrderStatus.NEW, OrderStatus.REJECTED):
            assert filled == 0, f"I4 broken on {o.order_id}"


def check_i5(svc: OrderService) -> None:
    log = svc.fills()
    for o in svc.orders():
        assert [f.seq for f in o.fills] == list(range(len(o.fills))), f"I5 gap on {o.order_id}"
        assert all(f.quantity > 0 and f.price > 0 for f in o.fills), f"I5 bad fill on {o.order_id}"
        assert [f for f in log if f.order_id == o.order_id] == o.fills, f"I5 log mismatch on {o.order_id}"
    assert len(log) == sum(len(o.fills) for o in svc.orders()), "I5 log has extra fills"


def check_i6(svc: OrderService) -> None:
    for o in svc.orders():
        if o.limit_price is None:
            continue
        for f in o.fills:
            if o.side is Side.BUY:
                assert f.price <= o.limit_price, f"I6 broken on {o.order_id}"
            else:
                assert f.price >= o.limit_price, f"I6 broken on {o.order_id}"


def check_all(svc: OrderService) -> None:
    check_i1(svc)
    check_i2(svc)
    check_i4(svc)
    check_i5(svc)
    check_i6(svc)


def snapshot(svc: OrderService):
    return (
        [(o.order_id, o.status, list(o.fills)) for o in svc.orders()],
        svc.fills(),
        svc.positions(),
    )


def fill_price_within_limit(order, price: Decimal) -> Decimal:
    if order.limit_price is None:
        return price
    return min(price, order.limit_price) if order.side is Side.BUY else max(price, order.limit_price)


# --- I1: filled never exceeds ordered ----------------------------------------------------


@given(qty=QUANTITIES, fills=st.lists(QUANTITIES, min_size=1, max_size=8), price=PRICES)
def test_i1_filled_never_exceeds_ordered(qty, fills, price):
    svc = OrderService()
    order = svc.place("acc-1", "SYN-A", Side.BUY, qty)
    for q in fills:
        try:
            svc.fill(order.order_id, q, price)
        except Overfill:
            assert q > order.remaining
        except InvalidTransition:
            assert order.status is OrderStatus.FILLED
        check_i1(svc)


@given(qty=QUANTITIES, extra=st.integers(min_value=1, max_value=20), price=PRICES)
def test_i1_overfill_is_rejected(qty, extra, price):
    svc = OrderService()
    order = svc.place("acc-1", "SYN-A", Side.SELL, qty)
    with pytest.raises(Overfill):
        svc.fill(order.order_id, qty + extra, price)
    assert order.filled_quantity == 0


# --- I2: position = sum of signed fills --------------------------------------------------


@given(
    ops=st.lists(
        st.tuples(ACCOUNTS, INSTRUMENTS, SIDES, QUANTITIES, st.lists(QUANTITIES, max_size=4), PRICES),
        min_size=1,
        max_size=12,
    )
)
def test_i2_position_is_sum_of_signed_fills(ops):
    svc = OrderService()
    for account, instrument, side, qty, fills, price in ops:
        order = svc.place(account, instrument, side, qty)
        for q in fills:
            if q <= order.remaining:
                svc.fill(order.order_id, q, price)
    check_i2(svc)


# --- I3: no transition out of a terminal state -------------------------------------------


@given(qty=QUANTITIES, partial=st.integers(min_value=0, max_value=49), price=PRICES)
def test_i3_cancelled_order_cannot_fill_or_cancel_again(qty, partial, price):
    svc = OrderService()
    order = svc.place("acc-1", "SYN-B", Side.BUY, qty)
    if 0 < partial < qty:
        svc.fill(order.order_id, partial, price)
    svc.cancel(order.order_id)
    before = snapshot(svc)
    with pytest.raises(InvalidTransition):
        svc.fill(order.order_id, 1, price)
    with pytest.raises(InvalidTransition):
        svc.cancel(order.order_id)
    assert snapshot(svc) == before


@given(qty=QUANTITIES, price=PRICES)
def test_i3_filled_order_cannot_be_cancelled(qty, price):
    svc = OrderService()
    order = svc.place("acc-1", "SYN-C", Side.SELL, qty)
    svc.fill(order.order_id, qty, price)
    with pytest.raises(InvalidTransition):
        svc.cancel(order.order_id)
    assert order.status is OrderStatus.FILLED


@given(qty=st.integers(min_value=101, max_value=500), price=PRICES)
def test_i3_rejected_order_stays_rejected(qty, price):
    svc = OrderService(max_order_quantity=100)
    order = svc.place("acc-2", "SYN-A", Side.BUY, qty)
    assert order.status is OrderStatus.REJECTED
    with pytest.raises(InvalidTransition):
        svc.fill(order.order_id, 1, price)
    with pytest.raises(InvalidTransition):
        svc.cancel(order.order_id)


def test_i3_terminal_states_have_no_outgoing_edges():
    for status in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[status] == frozenset()
    for status, targets in ALLOWED_TRANSITIONS.items():
        assert OrderStatus.NEW not in targets, f"nothing may go back to new (from {status})"


# --- I4: status agrees with quantities ---------------------------------------------------


@given(qty=QUANTITIES, fills=st.lists(QUANTITIES, max_size=6), price=PRICES, cancel=st.booleans())
def test_i4_status_matches_quantities(qty, fills, price, cancel):
    svc = OrderService()
    order = svc.place("acc-3", "SYN-A", Side.BUY, qty)
    for q in fills:
        if not order.status.is_terminal and q <= order.remaining:
            svc.fill(order.order_id, q, price)
        check_i4(svc)
    if cancel and not order.status.is_terminal:
        svc.cancel(order.order_id)
    check_i4(svc)


# --- I5: fills are append-only and consistent with the log -------------------------------


@given(
    ops=st.lists(st.tuples(SIDES, QUANTITIES, st.lists(QUANTITIES, max_size=5), PRICES), max_size=8)
)
def test_i5_fill_log_is_append_only(ops):
    svc = OrderService()
    seen = []
    for side, qty, fills, price in ops:
        order = svc.place("acc-1", "SYN-B", side, qty)
        for q in fills:
            if q <= order.remaining:
                svc.fill(order.order_id, q, price)
                log = svc.fills()
                assert log[: len(seen)] == seen, "I5: earlier fills changed"
                seen = log
    check_i5(svc)


# --- I6: limit price is respected --------------------------------------------------------


@given(side=SIDES, qty=QUANTITIES, limit=PRICES, price=PRICES)
def test_i6_never_fills_through_the_limit(side, qty, limit, price):
    svc = OrderService()
    order = svc.place("acc-1", "SYN-C", side, qty, limit_price=limit)
    try:
        svc.fill(order.order_id, qty, price)
    except OrderError:
        through = price > limit if side is Side.BUY else price < limit
        assert through, "a fill at or inside the limit was refused"
        assert order.filled_quantity == 0
    check_i6(svc)


# --- I7: a refused operation changes nothing ---------------------------------------------


@given(
    qty=QUANTITIES,
    first=st.integers(min_value=0, max_value=50),
    bad=st.sampled_from(["overfill", "zero", "negative_price", "unknown", "after_cancel"]),
    price=PRICES,
)
def test_i7_refused_operation_leaves_state_unchanged(qty, first, bad, price):
    svc = OrderService()
    order = svc.place("acc-2", "SYN-B", Side.SELL, qty)
    if 0 < first < qty:
        svc.fill(order.order_id, first, price)
    if bad == "after_cancel":
        svc.cancel(order.order_id)
    before = snapshot(svc)
    with pytest.raises(OrderError):
        if bad == "overfill":
            svc.fill(order.order_id, order.remaining + 1, price)
        elif bad == "zero":
            svc.fill(order.order_id, 0, price)
        elif bad == "negative_price":
            svc.fill(order.order_id, 1, -price)
        elif bad == "unknown":
            svc.fill("ord-999999", 1, price)
        else:
            svc.fill(order.order_id, 1, price)
    assert snapshot(svc) == before


# --- all invariants, random operation sequences ------------------------------------------


class OrderServiceMachine(RuleBasedStateMachine):
    """Random place / fill / cancel sequences; every invariant checked after every step.
    Illegal operations are attempted on purpose: they must raise and change nothing (I3, I7)."""

    orders = Bundle("orders")

    def __init__(self) -> None:
        super().__init__()
        self.svc = OrderService(max_order_quantity=40)

    @rule(target=orders, account=ACCOUNTS, instrument=INSTRUMENTS, side=SIDES, qty=QUANTITIES, limit=LIMITS)
    def place(self, account, instrument, side, qty, limit):
        return self.svc.place(account, instrument, side, qty, limit_price=limit).order_id

    @rule(order_id=orders, qty=QUANTITIES, price=PRICES)
    def fill(self, order_id, qty, price):
        order = self.svc.get(order_id)
        price = fill_price_within_limit(order, price)
        before = snapshot(self.svc)
        legal = not order.status.is_terminal and qty <= order.remaining
        try:
            self.svc.fill(order_id, qty, price)
        except OrderError:
            assert not legal, f"legal fill of {qty} refused on {order_id} ({order.status.value})"
            assert snapshot(self.svc) == before, "I7: refused fill changed state"
        else:
            assert legal, f"illegal fill of {qty} accepted on {order_id} ({order.status.value})"

    @rule(order_id=orders)
    def cancel(self, order_id):
        order = self.svc.get(order_id)
        was_terminal = order.status.is_terminal
        before = snapshot(self.svc)
        try:
            self.svc.cancel(order_id)
        except InvalidTransition:
            assert was_terminal, f"cancel refused on live order {order_id}"
            assert snapshot(self.svc) == before, "I7: refused cancel changed state"
        else:
            assert not was_terminal, f"I3: cancel accepted on terminal order {order_id}"
            assert order.status is OrderStatus.CANCELLED

    @rule(order_id=orders)
    def fill_remaining(self, order_id):
        order = self.svc.get(order_id)
        if not order.status.is_terminal:
            price = fill_price_within_limit(order, Decimal("100.00"))
            self.svc.fill(order_id, order.remaining, price)
            assert order.status is OrderStatus.FILLED

    @invariant()
    def all_invariants_hold(self):
        check_all(self.svc)


TestServiceStateMachine = OrderServiceMachine.TestCase

