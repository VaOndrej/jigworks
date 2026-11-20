from decimal import Decimal as D

from hypothesis import given
from hypothesis import strategies as st


def test_fee_rates_are_maker_5_bps_and_taker_10_bps():
    from btc_paper_trader import fees

    assert fees.MAKER == D("0.0005")
    assert fees.TAKER == D("0.001")


def test_fee_is_notional_times_rate_rounded_up_to_1e8():
    from btc_paper_trader.fees import MAKER, TAKER, fee

    assert fee(D("0.0005"), D("100000"), TAKER) == D("0.05")
    assert fee(D("0.0005"), D("100000"), MAKER) == D("0.025")
    # 0.00001 * 100000.01 * 0.0005 = 0.00050000005 -> ceil to 0.00000001
    assert fee(D("0.00001"), D("100000.01"), MAKER) == D("0.00050001")


def test_buy_reservation_adds_taker_fee_and_a_1e8_buffer_per_qty_step():
    from btc_paper_trader.fees import buy_reservation

    # 0.0005 * 99000 = 49.5; taker fee 0.0495; buffer 50 steps * 1e-8
    assert buy_reservation(D("0.0005"), D("99000")) == D("49.5495005")
    assert buy_reservation(D("0.0003"), D("99000")) == D("29.7297003")
    assert buy_reservation(D("0"), D("99000")) == D("0")


@given(
    qty_steps=st.integers(min_value=1, max_value=200_000),
    cents=st.integers(min_value=1, max_value=20_000_000),
    split=st.integers(min_value=1, max_value=50),
)
def test_buy_reservation_covers_any_split_into_partial_maker_or_taker_fills(qty_steps, cents, split):
    from btc_paper_trader.fees import TAKER, buy_reservation, fee

    step = D("0.00001")
    qty = qty_steps * step
    price = D(cents) / 100
    reserved = buy_reservation(qty, price)
    # Split the order into up to `split` fills and pay each at taker rate (the worst case).
    n = min(split, qty_steps)
    base = qty_steps // n
    parts = [base] * (n - 1) + [qty_steps - base * (n - 1)]
    cost = sum(p * step * price + fee(p * step, price, TAKER) for p in parts)
    assert cost <= reserved
