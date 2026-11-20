"""The feed is `stale` after more than 10 s without a reference tick, and trading halts."""

from decimal import Decimal as D


async def test_feed_turns_stale_after_more_than_10_seconds_without_a_tick(app, client, clock):
    service = app.state.service
    await service.tick(D("100000"))
    await clock.advance(9_000)
    assert (await client.get("/healthz")).json()["status"] != "stale"
    await clock.advance(1_500)
    body = (await client.get("/healthz")).json()
    assert body["status"] == "stale"
    assert body["last_tick_age_ms"] >= 10_000


async def test_a_new_tick_after_stale_makes_the_feed_live_again(app, client, clock):
    service = app.state.service
    await service.tick(D("100000"))
    await clock.advance(11_000)
    assert (await client.get("/healthz")).json()["status"] == "stale"
    await service.tick(D("100010"))
    await clock.advance(100)
    body = (await client.get("/healthz")).json()
    assert body["status"] == "live"
    assert body["last_tick_age_ms"] < 10_000


async def test_orders_are_rejected_with_stale_reference_while_stale_but_cancel_still_works(
    app, client, clock
):
    service = app.state.service
    await service.tick(D("100000"))
    placed = await client.post(
        "/api/orders", json={"side": "buy", "type": "limit", "qty": "0.0001", "price": "90000.00"}
    )
    assert placed.status_code == 200, placed.text
    order_id = placed.json()["order"]["order_id"]

    await clock.advance(10_500)
    r = await client.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "10"})
    assert r.status_code == 422
    assert r.json()["reason"] == "stale_reference"

    c = await client.delete(f"/api/orders/{order_id}")
    assert c.status_code == 200
    assert c.json()["order"]["status"] == "cancelled"


def test_engine_checks_staleness_itself_from_now_ms():
    from bpt_helpers import T0, USER_A, engine, limit, user

    eng = engine()
    user(eng)
    fresh = limit(eng, USER_A, "buy", "0.0001", "90000", now=T0 + 9_999)
    assert fresh.order.status == "open"
    stale = limit(eng, USER_A, "buy", "0.0001", "90000", now=T0 + 10_001)
    assert stale.order.status == "rejected"
    assert stale.reason == "stale_reference"
