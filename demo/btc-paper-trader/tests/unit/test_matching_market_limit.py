"""Engine: market and limit orders, reservations, level-by-level fills, the band, every reason."""

import ast
from decimal import Decimal as D
from pathlib import Path

import pytest
from bpt_helpers import (
    MAKER,
    MAKER2,
    T0,
    USER_A,
    USER_B,
    engine,
    limit,
    maker,
    market,
    order_by_id,
    req,
    snap,
    user,
)


@pytest.fixture
def eng():
    e = engine()
    user(e, USER_A)
    user(e, USER_B)
    maker(e, MAKER)
    maker(e, MAKER2)
    return e


# --- accounts -------------------------------------------------------------------------------


def test_open_account_issues_100_usd_once_and_is_idempotent():
    from btc_paper_trader.matching import Engine

    e = Engine()
    e.open_account(USER_A, kind="user", now_ms=T0)
    e.open_account(USER_A, kind="user", now_ms=T0 + 1)
    a = e.account(USER_A)
    assert a.usd == D("100") and a.btc == 0
    assert e.totals()["usd"]["accounts"] == D("100")
    assert e.totals()["usd"]["treasury"] == D("-100")
    assert e.totals()["usd"]["total"] == 0


def test_unknown_account_is_none():
    assert engine().account(USER_A) is None


# --- limit buy reservations -----------------------------------------------------------------


def test_resting_limit_buy_reserves_price_times_qty_plus_max_fee_and_buffer(eng):
    r = limit(eng, USER_A, "buy", "0.0005", "99000")
    assert r.order.status == "open"
    assert r.trades == []
    a = eng.account(USER_A)
    assert a.usd_reserved == D("49.5495005")
    assert a.available_usd == D("100") - D("49.5495005")
    assert a.usd == D("100")
    assert eng.book.best_bid() == D("99000")


def test_partial_fill_releases_its_share_of_the_buy_reservation(eng):
    order = limit(eng, USER_A, "buy", "0.0005", "99000").order
    r = market(eng, MAKER, "sell", "0.0002")
    assert [(t.price, t.qty) for t in r.trades] == [(D("99000"), D("0.0002"))]
    a = eng.account(USER_A)
    assert a.btc == D("0.0002")
    assert a.usd_reserved == D("29.7297003")  # buy_reservation(0.0003, 99000)
    assert a.usd == D("100") - D("19.8") - D("0.0099")  # maker fee ceil(19.8 * 0.0005)
    o = order_by_id(eng, USER_A, order.order_id)
    assert o.status == "partially_filled"
    assert o.filled_qty == D("0.0002")


def test_cancel_releases_the_remaining_reservation(eng):
    order = limit(eng, USER_A, "buy", "0.0005", "99000").order
    market(eng, MAKER, "sell", "0.0002")
    res = eng.cancel(USER_A, order.order_id, now_ms=T0)
    assert res.order.status == "cancelled"
    assert res.order.reason == "user"
    a = eng.account(USER_A)
    assert a.usd_reserved == 0
    assert a.available_usd == a.usd
    assert eng.book.best_bid() is None


def test_limit_sell_reserves_its_btc(eng):
    r = limit(eng, MAKER, "sell", "0.003", "101000")
    assert r.order.status == "open"
    m = eng.account(MAKER)
    assert m.btc_reserved == D("0.003")
    assert m.free_btc == D("0.007")


def test_a_sell_can_never_exceed_free_btc(eng):
    limit(eng, MAKER, "sell", "0.008", "101000")
    r = limit(eng, MAKER, "sell", "0.003", "102000")
    assert r.order.status == "rejected"
    assert r.reason == "insufficient_btc"
    assert eng.account(MAKER).btc_reserved == D("0.008")


# --- level by level, FIFO, maker prices -----------------------------------------------------


def test_market_buy_fills_level_by_level_at_the_makers_prices(eng):
    limit(eng, MAKER, "sell", "0.0002", "100000")
    limit(eng, MAKER2, "sell", "0.0002", "100010")
    limit(eng, MAKER, "sell", "0.0002", "100020")
    r = market(eng, USER_A, "buy", "0.0005")
    assert [(t.price, t.qty) for t in r.trades] == [
        (D("100000"), D("0.0002")),
        (D("100010"), D("0.0002")),
        (D("100020"), D("0.0001")),
    ]
    assert r.order.status == "filled"
    assert r.order.filled_qty == D("0.0005")
    a = eng.account(USER_A)
    assert a.btc == D("0.0005")
    # 50.004 notional, taker fees 0.02 + 0.020002 + 0.010002
    assert a.usd == D("100") - D("50.004") - D("0.050004")
    assert eng.book.levels("sell", 20) == [(D("100020"), D("0.0001"))]


def test_within_a_level_the_earliest_order_fills_first(eng):
    first = limit(eng, MAKER, "sell", "0.0002", "100000").order
    limit(eng, MAKER2, "sell", "0.0002", "100000")
    r = market(eng, USER_A, "buy", "0.0001")
    (t,) = r.trades
    assert t.sell_order_id == first.order_id
    assert t.sell_account_id == MAKER
    assert t.buy_account_id == USER_A
    assert t.maker_side == "sell"


def test_marketable_limit_fills_at_maker_prices_and_rests_the_remainder(eng):
    limit(eng, MAKER, "sell", "0.0002", "100000")
    limit(eng, MAKER2, "sell", "0.0002", "100100")
    r = limit(eng, USER_A, "buy", "0.0005", "100050")
    assert [(t.price, t.qty) for t in r.trades] == [(D("100000"), D("0.0002"))]
    assert r.order.status == "partially_filled"
    assert eng.book.best_bid() == D("100050")
    assert eng.book.best_ask() == D("100100")
    assert eng.account(USER_A).usd_reserved == D("30.0450153")  # buy_reservation(0.0003, 100050)


def test_maker_pays_maker_fee_taker_pays_taker_fee_and_both_go_to_the_fee_account(eng):
    limit(eng, MAKER, "sell", "0.0005", "100000")
    r = market(eng, USER_A, "buy", "0.0005")
    (t,) = r.trades
    assert t.buy_fee == D("0.05")
    assert t.sell_fee == D("0.025")
    assert eng.account(USER_A).fees_paid == D("0.05")
    assert eng.account(MAKER).fees_paid == D("0.025")
    assert eng.account("fees").usd == D("0.075")


# --- market sizing --------------------------------------------------------------------------


def test_market_buy_by_usd_amount_includes_the_fee(eng):
    limit(eng, MAKER, "sell", "0.01", "100000")
    r = market(eng, USER_A, "buy", quote_amount=D("20"))
    assert sum(t.qty for t in r.trades) == D("0.00019")
    assert eng.account(USER_A).usd == D("100") - D("19") - D("0.019")


def test_market_buy_max_spends_all_available_usd(eng):
    limit(eng, MAKER, "sell", "0.01", "100000")
    r = market(eng, USER_A, "buy", max=True)
    assert sum(t.qty for t in r.trades) == D("0.00099")
    assert eng.account(USER_A).usd == D("100") - D("99") - D("0.099")


def test_market_sell_max_sells_all_free_btc(eng):
    limit(eng, USER_A, "buy", "0.0009", "99000")
    r = market(eng, MAKER, "sell", max=True)
    assert sum(t.qty for t in r.trades) == D("0.0009")
    assert eng.account(MAKER).btc == D("0.01") - D("0.0009")


def test_market_buy_that_cannot_afford_the_fill_is_refused_with_insufficient_funds(eng):
    limit(eng, MAKER, "sell", "0.005", "100000")
    r = market(eng, USER_A, "buy", "0.002")
    assert r.reason == "insufficient_funds"
    assert eng.account(USER_A).available_usd >= 0


# --- the band -------------------------------------------------------------------------------


def test_market_order_stops_at_the_5_percent_band_and_cancels_the_rest(eng):
    limit(eng, MAKER, "sell", "0.0002", "100000")
    limit(eng, MAKER2, "sell", "0.0002", "106000")  # above 100000 * 1.05
    r = market(eng, USER_A, "buy", "0.0005")
    assert [(t.price, t.qty) for t in r.trades] == [(D("100000"), D("0.0002"))]
    assert r.order.status == "cancelled"
    assert r.order.reason == "band_exhausted"
    assert r.order.filled_qty == D("0.0002")
    assert eng.book.best_ask() == D("106000")


def test_market_order_with_only_out_of_band_liquidity_is_rejected_band_exhausted(eng):
    limit(eng, MAKER2, "sell", "0.0002", "106000")
    r = market(eng, USER_A, "buy", "0.0001")
    assert r.order.status == "rejected"
    assert r.reason == "band_exhausted"
    assert r.trades == []


def test_band_edges_are_inclusive(eng):
    limit(eng, MAKER2, "sell", "0.0001", "105000")
    r = market(eng, USER_A, "buy", "0.0001")
    assert [t.price for t in r.trades] == [D("105000")]


def test_limit_remainder_that_would_cross_the_book_is_cancelled_band_exhausted(eng):
    limit(eng, MAKER, "sell", "0.0002", "100000")
    limit(eng, MAKER2, "sell", "0.0002", "106000")
    r = limit(eng, USER_A, "buy", "0.0005", "107000")
    assert [t.price for t in r.trades] == [D("100000")]
    assert r.order.status == "cancelled"
    assert r.order.reason == "band_exhausted"
    assert eng.account(USER_A).usd_reserved == 0
    assert eng.book.is_crossed() is False


def test_market_order_into_an_empty_book_is_rejected_no_liquidity(eng):
    r = market(eng, USER_A, "buy", "0.0001")
    assert r.order.status == "rejected"
    assert r.reason == "no_liquidity"


# --- every rejection reason -----------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        (dict(side="buy", type="limit", qty=D("0.001"), max=True, price=D("99000")), "invalid_order"),
        (dict(side="buy", type="limit", price=D("99000")), "invalid_order"),
        (dict(side="buy", type="market", qty=D("0.0001"), quote_amount=D("10")), "invalid_order"),
        (dict(side="buy", type="limit", qty=D("0.000015"), price=D("99000")), "invalid_precision"),
        (dict(side="buy", type="limit", qty=D("0.0001"), price=D("99000.001")), "invalid_precision"),
        (dict(side="buy", type="limit", qty=D("0.00001"), price=D("50000")), "below_minimum"),
        (dict(side="buy", type="market", quote_amount=D("0.5")), "below_minimum"),
        (dict(side="buy", type="limit", qty=D("0.002"), price=D("99000")), "insufficient_funds"),
        (dict(side="sell", type="limit", qty=D("0.0001"), price=D("101000")), "insufficient_btc"),
        (dict(side="sell", type="market", qty=D("0.0001")), "insufficient_btc"),
    ],
)
def test_invalid_orders_are_rejected_with_their_reason_and_kept_in_history(eng, kwargs, reason):
    r = eng.submit(req(USER_A, **kwargs), now_ms=T0)
    assert r.reason == reason
    assert r.order is not None and r.order.status == "rejected"
    assert r.order.reason == reason
    history = eng.orders(USER_A, open_only=False)
    assert any(o.order_id == r.order.order_id and o.reason == reason for o in history)
    assert eng.orders(USER_A, open_only=True) == []
    a = eng.account(USER_A)
    assert (a.usd, a.usd_reserved, a.btc) == (D("100"), 0, 0)


def test_orders_before_any_reference_price_are_rejected_no_reference_price():
    e = engine(ref=None)
    user(e, USER_A)
    r = limit(e, USER_A, "buy", "0.0001", "99000")
    assert r.reason == "no_reference_price"
    assert r.order.status == "rejected"


def test_orders_on_a_stale_reference_are_rejected_stale_reference(eng):
    r = limit(eng, USER_A, "buy", "0.0001", "99000", now=T0 + 10_001)
    assert r.reason == "stale_reference"


def test_cancel_still_works_when_the_reference_is_stale(eng):
    o = limit(eng, USER_A, "buy", "0.0001", "99000").order
    res = eng.cancel(USER_A, o.order_id, now_ms=T0 + 60_000)
    assert res.order.status == "cancelled"


# --- cancel ---------------------------------------------------------------------------------


def test_cancel_of_another_accounts_order_is_not_found_and_changes_nothing(eng):
    o = limit(eng, USER_A, "buy", "0.0001", "99000").order
    res = eng.cancel(USER_B, o.order_id, now_ms=T0)
    assert res.reason == "not_found"
    assert order_by_id(eng, USER_A, o.order_id).status == "open"
    assert eng.book.best_bid() == D("99000")


def test_cancel_of_an_unknown_order_is_not_found(eng):
    assert eng.cancel(USER_A, 987654321, now_ms=T0).reason == "not_found"


def test_a_cancelled_order_cannot_change_again(eng):
    o = limit(eng, USER_A, "buy", "0.0001", "99000").order
    eng.cancel(USER_A, o.order_id, now_ms=T0)
    again = eng.cancel(USER_A, o.order_id, now_ms=T0)
    assert again.reason == "not_found"
    assert order_by_id(eng, USER_A, o.order_id).status == "cancelled"


# --- reset ----------------------------------------------------------------------------------


def test_reset_returns_the_account_to_a_fresh_100_and_touches_no_one_else(eng):
    limit(eng, MAKER, "sell", "0.001", "100000")
    market(eng, USER_A, "buy", "0.0003")
    limit(eng, USER_A, "buy", "0.0001", "98000")
    b_order = limit(eng, USER_B, "buy", "0.0002", "97000").order
    before_b = snap(eng.account(USER_B))
    before_maker = snap(eng.account(MAKER))
    epoch = eng.account(USER_A).epoch

    res = eng.reset(USER_A, now_ms=T0 + 5)
    a = eng.account(USER_A)
    assert (a.usd, a.btc, a.usd_reserved, a.btc_reserved) == (D("100"), 0, 0, 0)
    assert (a.realized_pnl, a.fees_paid, a.cost_basis) == (0, 0, 0)
    assert a.epoch == epoch + 1
    assert eng.orders(USER_A, open_only=False) == []
    assert eng.book.levels("buy", 20) == [(D("97000"), D("0.0002"))]
    assert snap(eng.account(USER_B)) == before_b
    assert snap(eng.account(MAKER)) == before_maker
    assert order_by_id(eng, USER_B, b_order.order_id).status == "open"
    assert eng.totals()["usd"]["total"] == 0
    assert eng.totals()["btc"]["total"] == 0
    assert res.reason is None


# --- purity ---------------------------------------------------------------------------------


def test_matching_module_has_no_io_clock_randomness_or_asyncio():
    import btc_paper_trader.matching as matching

    tree = ast.parse(Path(matching.__file__).read_text())
    banned = {"asyncio", "time", "random", "datetime", "os", "socket", "aiosqlite", "sqlite3", "httpx"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert not (imported & banned), imported & banned
