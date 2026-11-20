"""Average-cost PnL, equity and return, with worked numbers."""

from decimal import Decimal as D

from bpt_helpers import MAKER, T0, USER_A, engine, limit, maker, market, user


def _eng():
    eng = engine()
    user(eng)
    maker(eng)
    return eng


def test_buy_adds_cost_basis_without_fees_and_fees_are_tracked_separately():
    eng = _eng()
    limit(eng, MAKER, "sell", "0.0005", "100000")
    market(eng, USER_A, "buy", "0.0005")
    a = eng.account(USER_A)
    assert a.cost_basis == D("50")
    assert a.fees_paid == D("0.05")
    assert a.realized_pnl == 0
    assert a.unrealized_pnl == 0  # mark = last trade 100000
    assert a.equity == D("99.95")
    assert a.return_pct == D("-0.05")


def test_sell_realizes_against_the_average_cost():
    eng = _eng()
    limit(eng, MAKER, "sell", "0.0002", "100000")
    limit(eng, MAKER, "sell", "0.0002", "102000")
    market(eng, USER_A, "buy", "0.0004")  # avg cost 101000
    a = eng.account(USER_A)
    assert a.cost_basis == D("40.4")
    limit(eng, USER_A, "sell", "0.0001", "103000")
    market(eng, MAKER, "buy", "0.0001")  # USER_A is the maker at 103000
    a = eng.account(USER_A)
    assert a.realized_pnl == D("0.2")  # (103000 - 101000) * 0.0001
    assert a.cost_basis == D("30.3")
    assert a.btc == D("0.0003")
    # mark is now the last trade, 103000
    assert a.unrealized_pnl == D("0.0003") * D("103000") - D("30.3")


def test_mark_falls_back_to_the_reference_price_before_any_trade():
    eng = _eng()
    assert eng.account(USER_A).equity == D("100")
    eng.reference_tick(D("90000"), ts_ms=T0 + 1)
    assert eng.account(USER_A).equity == D("100")


def test_pnl_identity_holds_after_a_round_trip():
    eng = _eng()
    limit(eng, MAKER, "sell", "0.0005", "100000")
    market(eng, USER_A, "buy", "0.0005")
    limit(eng, USER_A, "sell", "0.0002", "101000")
    market(eng, MAKER, "buy", "0.0002")
    a = eng.account(USER_A)
    lhs = a.realized_pnl + a.unrealized_pnl - a.fees_paid
    assert abs(lhs - (a.equity - 100)) <= D("0.000001")
    assert a.return_pct == (a.equity - 100) / 100 * 100
