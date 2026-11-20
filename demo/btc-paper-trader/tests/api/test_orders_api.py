"""M2 API: buy from the book, limit sell, reasons, 404 for foreign ids, reset scope, close."""

from decimal import Decimal as D

import pytest


async def _ready(app):
    await app.state.service.tick(D("100000"))  # the house quotes 99950 / 100050 and outwards


async def _state(c):
    r = await c.get("/api/state")
    assert r.status_code == 200
    return r.json()


async def test_market_buy_by_usd_amount_fills_from_the_house_asks(app, client):
    await _ready(app)
    r = await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "20"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order"]["status"] == "filled"
    assert body["trades"] and all(D(t["price"]) == D("100050") for t in body["trades"])
    acct = (await _state(client))["account"]
    assert D("80") <= D(acct["usd"]) < D("81")
    assert D(acct["btc"]) == sum(D(t["qty"]) for t in body["trades"])
    assert D(acct["fees_paid"]) > 0


async def test_state_shape_has_account_position_orders_history_and_fills(app, client):
    await _ready(app)
    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "20"})
    s = await _state(client)
    for k in ("usd", "btc", "usd_reserved", "btc_reserved", "available_usd", "free_btc", "equity",
              "realized_pnl", "unrealized_pnl", "fees_paid", "return_pct", "mark_price"):
        assert k in s["account"], k
        assert isinstance(s["account"][k], str), k
    assert set(s["position"]) >= {"qty", "avg_cost", "mark", "unrealized"}
    assert D(s["position"]["avg_cost"]) == D("100050")
    assert isinstance(s["open_orders"], list)
    assert len(s["history"]) == 1
    assert len(s["fills"]) >= 1


async def test_limit_sell_above_the_market_rests_and_reserves_btc(app, client):
    await _ready(app)
    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "20"})
    btc = (await _state(client))["account"]["btc"]
    r = await client.post("/api/orders", json={"side": "sell", "type": "limit", "qty": btc, "price": "101000.00"})
    assert r.status_code == 200, r.text
    assert r.json()["order"]["status"] == "open"
    s = await _state(client)
    assert D(s["account"]["btc_reserved"]) == D(btc)
    assert D(s["account"]["free_btc"]) == 0
    assert [o["order_id"] for o in s["open_orders"]] == [r.json()["order"]["order_id"]]
    book = (await client.get("/api/book", params={"depth": 20})).json()
    assert any(D(p) == D("101000") and D(q) == D(btc) for p, q in book["asks"])


async def test_sell_max_sells_all_free_btc(app, client):
    await _ready(app)
    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "20"})
    r = await client.post("/api/orders", json={"side": "sell", "type": "market", "max": True})
    assert r.status_code == 200
    assert D((await _state(client))["account"]["btc"]) == 0


@pytest.mark.parametrize(
    "body, reason",
    [
        ({"side": "buy", "type": "market", "qty": "0.001", "quote_amount": "10"}, "invalid_order"),
        ({"side": "buy", "type": "market"}, "invalid_order"),
        ({"side": "sideways", "type": "market", "qty": "0.001"}, "invalid_order"),
        ({"side": "buy", "type": "limit", "qty": "0.000015", "price": "99000.00"}, "invalid_precision"),
        ({"side": "buy", "type": "limit", "qty": "0.0001", "price": "99000.001"}, "invalid_precision"),
        ({"side": "buy", "type": "limit", "qty": "0.00001", "price": "50000.00"}, "below_minimum"),
        ({"side": "buy", "type": "limit", "qty": "0.01", "price": "99000.00"}, "insufficient_funds"),
        ({"side": "sell", "type": "limit", "qty": "0.0001", "price": "101000.00"}, "insufficient_btc"),
        ({"side": "buy", "type": "market", "qty": "0.0001", "reduce_only": True}, "reduce_only_buy"),
        ({"side": "sell", "type": "limit", "qty": "0.0001", "price": "101000.00", "reduce_only": True}, "nothing_to_reduce"),
        ({"side": "buy", "type": "market", "qty": "0.0001", "sl": "100500.00"}, "invalid_sl_tp"),
        ({"side": "buy", "type": "stop", "qty": "0.0001", "stop_price": "90000.00"}, "invalid_stop"),
    ],
)
async def test_rejections_return_422_with_a_reason(app, client, body, reason):
    await _ready(app)
    r = await client.post("/api/orders", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["reason"] == reason


async def test_a_rejected_order_appears_in_history_with_its_reason(app, client):
    await _ready(app)
    r = await client.post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.01", "price": "99000.00"})
    assert r.status_code == 422
    assert r.json()["order"]["status"] == "rejected"
    history = (await _state(client))["history"]
    assert [(h["status"], h["reason"]) for h in history] == [("rejected", "insufficient_funds")]


async def test_stale_or_missing_reference_rejects_orders(app, client, clock):
    await _ready(app)
    await clock.advance(10_500)
    r = await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "10"})
    assert r.status_code == 422
    assert r.json()["reason"] == "stale_reference"


async def test_cancel_own_order_returns_200_cancelled(app, client):
    await _ready(app)
    o = (await client.post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.0002", "price": "95000.00"})).json()["order"]
    r = await client.delete(f"/api/orders/{o['order_id']}")
    assert r.status_code == 200
    assert r.json()["order"]["status"] == "cancelled"
    assert r.json()["order"]["reason"] == "user"
    assert D((await _state(client))["account"]["usd_reserved"]) == 0


async def test_cancel_of_another_accounts_order_or_an_unknown_id_is_404(app, client, make_client):
    await _ready(app)
    o = (await client.post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.0002", "price": "95000.00"})).json()["order"]
    other = await make_client()
    assert (await other.delete(f"/api/orders/{o['order_id']}")).status_code == 404
    assert (await client.delete("/api/orders/999999999")).status_code == 404
    still = (await _state(client))["open_orders"]
    assert [x["order_id"] for x in still] == [o["order_id"]]


async def test_reset_returns_a_fresh_account_and_leaves_others_untouched(app, client, make_client):
    await _ready(app)
    other = await make_client()
    await other.post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.0002", "price": "95000.00"})
    other_before = await _state(other)

    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "30"})
    await client.post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.0001", "price": "96000.00"})
    r = await client.post("/api/account/reset")
    assert r.status_code == 200
    mine = r.json()["state"]
    assert D(mine["account"]["usd"]) == D("100")
    assert D(mine["account"]["btc"]) == 0
    assert D(mine["account"]["fees_paid"]) == 0
    assert D(mine["account"]["realized_pnl"]) == 0
    assert mine["open_orders"] == [] and mine["history"] == [] and mine["fills"] == []
    assert (await _state(client))["history"] == []

    other_after = await _state(other)
    for key in ("usd", "btc", "usd_reserved", "btc_reserved", "fees_paid", "realized_pnl"):
        assert other_after["account"][key] == other_before["account"][key], key
    assert other_after["open_orders"] == other_before["open_orders"]
    totals = (await client.get("/api/internal/totals")).json()
    assert D(totals["usd"]["total"]) == 0 and D(totals["btc"]["total"]) == 0


async def test_close_position_sells_everything(app, client):
    await _ready(app)
    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "30"})
    placed = await client.post("/api/orders", json={"side": "sell", "type": "limit", "qty": "0.0001", "price": "101000.00"})
    assert placed.status_code == 200
    r = await client.post("/api/position/close")
    assert r.status_code == 200, r.text
    assert r.json()["order"]["role"] == "close"
    s = await _state(client)
    assert D(s["account"]["btc"]) == 0
    assert s["open_orders"] == []


async def test_close_position_when_flat_is_422_nothing_to_reduce(app, client):
    await _ready(app)
    r = await client.post("/api/position/close")
    assert r.status_code == 422
    assert r.json()["reason"] == "nothing_to_reduce"


async def test_book_returns_depth_levels_and_validates_depth(app, client):
    await _ready(app)
    b = (await client.get("/api/book", params={"depth": 5})).json()
    assert len(b["bids"]) == 5 and len(b["asks"]) == 5
    assert D(b["bids"][0][0]) == D("99950") and D(b["asks"][0][0]) == D("100050")
    assert all(isinstance(x, str) for lvl in b["bids"] for x in lvl)
    assert "ts" in b
    assert (await client.get("/api/book", params={"depth": 0})).status_code == 422
    assert (await client.get("/api/book", params={"depth": 51})).status_code == 422


async def test_trades_tape_is_newest_first(app, client, make_client):
    await _ready(app)
    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "10"})
    other = await make_client()
    await other.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "10"})
    tape = (await client.get("/api/trades", params={"limit": 100})).json()
    ids = [t["trade_id"] for t in tape]
    assert len(ids) >= 2
    assert ids == sorted(ids, reverse=True)


async def test_internal_candles_are_built_from_trades(app, client, clock):
    await _ready(app)
    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "10"})
    candles = (await client.get("/api/candles", params={"tf": "1m"})).json()
    assert len(candles) == 1
    c = candles[0]
    assert c["open_time_ms"] == clock.now() // 60_000 * 60_000
    assert D(c["close"]) == D("100050")
    assert D(c["volume"]) > 0


async def test_internal_totals_are_zero_for_both_assets(app, client):
    await _ready(app)
    await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "10"})
    t = (await client.get("/api/internal/totals")).json()
    for asset in ("usd", "btc"):
        assert set(t[asset]) >= {"accounts", "house", "fees", "treasury", "total"}
        assert D(t[asset]["total"]) == 0
    assert D(t["usd"]["fees"]) > 0
