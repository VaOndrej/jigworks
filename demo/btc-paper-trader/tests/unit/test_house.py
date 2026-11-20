"""House market maker: ladder around the reference, post-only, inventory-limited, never topped up."""

from decimal import Decimal as D

from bpt_helpers import T0, USER_A, engine, limit, market, user


def _cfg(**kw):
    from btc_paper_trader.house import HouseConfig

    return HouseConfig(**kw)


def test_house_config_defaults_match_the_design():
    c = _cfg()
    assert (c.levels, c.spread_bps, c.step_bps) == (10, 10, 5)
    assert c.level_qty == D("0.01")
    assert D(c.usd) == D("200000") and D(c.btc) == D("2")


def test_requote_places_k_bids_and_asks_at_spread_and_step_around_the_reference():
    eng = engine()
    eng.house_requote(_cfg(), now_ms=T0)
    bids = eng.book.levels("buy", 50)
    asks = eng.book.levels("sell", 50)
    assert len(bids) == 10 and len(asks) == 10
    assert bids[0] == (D("99950"), D("0.01"))
    assert asks[0] == (D("100050"), D("0.01"))
    assert bids[1][0] == D("99900")
    assert asks[1][0] == D("100100")
    assert bids[-1][0] == D("99500")
    assert asks[-1][0] == D("100500")


def test_requote_rounds_bids_down_and_asks_up_to_the_tick():
    eng = engine(ref=D("100000.03"))
    eng.house_requote(_cfg(levels=1), now_ms=T0)
    # 100000.03 * 0.9995 = 99950.0299..., * 1.0005 = 100050.0300...
    assert eng.book.best_bid() == D("99950.02")
    assert eng.book.best_ask() == D("100050.04")


def test_requote_cancels_the_previous_quotes_with_reason_requote():
    eng = engine()
    eng.house_requote(_cfg(), now_ms=T0)
    old = eng.orders("house", open_only=True)
    eng.reference_tick(D("101000"), ts_ms=T0 + 2000)
    eng.house_requote(_cfg(), now_ms=T0 + 2000)
    old_ids = {o.order_id for o in old}
    for o in eng.orders("house", open_only=False):
        if o.order_id in old_ids:
            assert o.status == "cancelled" and o.reason == "requote"
    assert eng.book.best_bid() == D("100949.50")
    assert len(eng.orders("house", open_only=True)) == 20


def test_quotes_are_post_only_and_skip_levels_that_would_cross():
    eng = engine()
    user(eng)
    limit(eng, USER_A, "buy", "0.0001", "100060")
    res = eng.house_requote(_cfg(), now_ms=T0)
    assert res.trades == []
    assert eng.book.is_crossed() is False
    asks = [p for p, _ in eng.book.levels("sell", 50)]
    assert asks and min(asks) > D("100060")
    assert D("100050") not in asks


def test_quotes_are_limited_by_house_inventory():
    eng = engine(house_btc=D("0.025"), house_usd=D("1500"))
    eng.house_requote(_cfg(), now_ms=T0)
    asks = eng.book.levels("sell", 50)
    bids = eng.book.levels("buy", 50)
    assert sum(q for _, q in asks) <= D("0.025")
    assert all(q <= D("0.01") for _, q in asks)
    assert sum(p * q for p, q in bids) <= D("1500")
    house = eng.account("house")
    assert house.available_usd >= 0 and house.free_btc >= 0


def test_house_is_never_topped_up():
    eng = engine()
    user(eng)
    eng.house_requote(_cfg(), now_ms=T0)
    market(eng, USER_A, "buy", "0.0005")
    after_trade = eng.account("house")
    btc, usd = after_trade.btc, after_trade.usd
    assert btc == D("2") - D("0.0005")
    eng.reference_tick(D("100000"), ts_ms=T0 + 2000)
    eng.house_requote(_cfg(), now_ms=T0 + 2000)
    house = eng.account("house")
    assert house.btc == btc and house.usd == usd
    assert eng.totals()["btc"]["total"] == 0


def test_no_requote_without_a_fresh_reference():
    eng = engine(ref=None)
    eng.house_requote(_cfg(), now_ms=T0)
    assert eng.book.levels("sell", 50) == []
    stale = engine()
    stale.house_requote(_cfg(), now_ms=T0 + 10_001)
    assert stale.book.levels("sell", 50) == []
