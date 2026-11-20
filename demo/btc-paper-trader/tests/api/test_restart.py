"""S8: stop the process, start it again on the same --db, everything comes back."""

from decimal import Decimal as D

import httpx

from bpt_helpers import FakeClock


async def _run(make_config, db, clock, actions):
    from btc_paper_trader.api import create_app

    app = create_app(make_config(db=db, clock=clock.now, sleep=clock.sleep))
    async with app.router.lifespan_context(app):
        clients = {}
        for aid in ("a" * 32, "b" * 32):
            clients[aid] = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", cookies={"account_id": aid}
            )
        try:
            await actions(app, clients)
            out = {}
            for aid, c in clients.items():
                s = (await c.get("/api/state")).json()
                s["account"].pop("mark_price", None)
                out[aid] = s
            any_client = next(iter(clients.values()))
            out["book"] = (await any_client.get("/api/book", params={"depth": 50})).json()
            out["book"].pop("ts", None)
            out["trades"] = (await any_client.get("/api/trades", params={"limit": 100})).json()
            out["candles"] = (await any_client.get("/api/candles", params={"tf": "1m"})).json()
            out["records"] = app.state.service.engine.to_records()
            return out
        finally:
            for c in clients.values():
                await c.aclose()


async def test_accounts_orders_stops_history_and_candles_survive_a_restart(make_config, tmp_path):
    db = tmp_path / "restart.db"
    clock = FakeClock()
    a, b = "a" * 32, "b" * 32

    async def trade(app, clients):
        await app.state.service.tick(D("100000"))
        ca, cb = clients[a], clients[b]
        assert (await ca.post("/api/orders", json={"side": "buy", "type": "market", "quote_amount": "40"})).status_code == 200
        assert (await ca.post("/api/orders", json={"side": "sell", "type": "limit", "qty": "0.0001", "price": "101000.00"})).status_code == 200
        assert (await ca.post("/api/orders", json={"side": "sell", "type": "stop", "qty": "0.0001", "stop_price": "99000.00"})).status_code == 200
        assert (await cb.post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.0002", "price": "99000.00",
                                                   "sl": "98000.00", "tp": "102000.00"})).status_code == 200
        assert (await cb.post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.01", "price": "99000.00"})).status_code == 422

    async def nothing(app, clients):
        return None

    before = await _run(make_config, db, clock, trade)
    after = await _run(make_config, db, clock, nothing)
    assert after[a] == before[a]
    assert after[b] == before[b]
    assert after["trades"] == before["trades"]
    assert after["candles"] == before["candles"]
    assert after["records"] == before["records"]
    # the house quotes from before the restart are restored, not re-issued
    assert after["book"] == before["book"]


async def test_house_inventory_is_issued_only_on_the_first_start(make_config, tmp_path):
    db = tmp_path / "house.db"
    clock = FakeClock()
    from btc_paper_trader.service import Service

    first = Service(make_config(db=db, clock=clock.now, sleep=clock.sleep))
    async with first.running():
        house_usd = first.engine.account("house").usd
        treasury = first.engine.account("treasury").usd
    second = Service(make_config(db=db, clock=clock.now, sleep=clock.sleep))
    async with second.running():
        assert second.engine.account("house").usd == house_usd
        assert second.engine.account("treasury").usd == treasury
    assert house_usd == D("200000")


async def test_a_new_account_after_restart_continues_the_order_id_sequence(make_config, tmp_path):
    db = tmp_path / "seq.db"
    clock = FakeClock()
    ids = []

    async def place(app, clients):
        await app.state.service.tick(D("100000"))
        r = await clients["a" * 32].post("/api/orders", json={"side": "buy", "type": "limit", "qty": "0.0001", "price": "95000.00"})
        ids.append(r.json()["order"]["order_id"])

    await _run(make_config, db, clock, place)
    await clock.advance(100)
    await _run(make_config, db, clock, place)
    assert ids[1] > ids[0]
