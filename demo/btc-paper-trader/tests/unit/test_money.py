from decimal import Decimal as D

import pytest


def _reason(exc):
    return getattr(exc, "reason", None)


def test_quanta_constants_match_the_spec():
    from btc_paper_trader import money

    assert money.QTY_STEP == D("0.00001")
    assert money.PRICE_TICK == D("0.01")
    assert money.USD_Q == D("0.00000001")
    assert money.MIN_NOTIONAL == D("1")


def test_parse_qty_accepts_on_step_values_as_decimal():
    from btc_paper_trader.money import parse_qty

    value = parse_qty("0.00123")
    assert isinstance(value, D)
    assert value == D("0.00123")


@pytest.mark.parametrize("raw", ["0.000015", "0.123456", "1.000001"])
def test_parse_qty_rejects_off_step_values_with_invalid_precision(raw):
    from btc_paper_trader.money import parse_qty

    with pytest.raises(ValueError) as e:
        parse_qty(raw)
    assert _reason(e.value) == "invalid_precision"


@pytest.mark.parametrize("raw", ["100.001", "99999.999"])
def test_parse_price_rejects_off_tick_values_with_invalid_precision(raw):
    from btc_paper_trader.money import parse_price

    with pytest.raises(ValueError) as e:
        parse_price(raw)
    assert _reason(e.value) == "invalid_precision"


def test_parse_price_accepts_a_tick_multiple():
    from btc_paper_trader.money import parse_price

    assert parse_price("100123.45") == D("100123.45")


def test_parse_usd_allows_eight_decimals_but_not_nine():
    from btc_paper_trader.money import parse_usd

    assert parse_usd("12.34567891") == D("12.34567891")
    with pytest.raises(ValueError) as e:
        parse_usd("1.000000001")
    assert _reason(e.value) == "invalid_precision"


@pytest.mark.parametrize("raw", ["abc", "", "NaN", "Infinity"])
def test_parse_rejects_non_numbers(raw):
    from btc_paper_trader.money import parse_qty

    with pytest.raises(ValueError):
        parse_qty(raw)


def test_floor_and_ceil_helpers_round_to_their_quantum():
    from btc_paper_trader.money import ceil_price, ceil_usd, floor_price, floor_qty, floor_usd

    assert floor_qty(D("0.000019")) == D("0.00001")
    assert floor_qty(D("0.00002")) == D("0.00002")
    assert floor_price(D("100.019")) == D("100.01")
    assert ceil_price(D("100.011")) == D("100.02")
    assert ceil_price(D("100.01")) == D("100.01")
    assert ceil_usd(D("0.000000001")) == D("0.00000001")
    assert ceil_usd(D("0.05")) == D("0.05")
    assert floor_usd(D("0.000000019")) == D("0.00000001")


def test_rounding_helpers_return_decimals_never_floats():
    from btc_paper_trader.money import ceil_usd, floor_qty

    assert isinstance(ceil_usd(D("1.5")), D)
    assert isinstance(floor_qty(D("1.5")), D)
