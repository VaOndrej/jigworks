"""M3 scenario over HTTP: a limit entry fills partially -> the SL triggers -> the TP is cancelled
with sl_triggered and the position is sold.

Book after a 100000 tick: house bids 99950, 99900, ... and asks 100050, 100100, ... (0.01 each).

Note: with an uncrossed book and price-time priority, the trade that triggers the SL has to walk
through the entry's own resting remainder first (SL < entry limit), so at trigger time the entry
is filled. The test therefore accepts the entry as either ``filled`` or ``cancelled`` with
``sl_triggered``, and asserts that nothing of it remains open.
"""

from decimal import Decimal as D


def _by_role(history, parent_id):
    return {o["role"]: o for o in history if o.get("parent_id") == parent_id}


async def test_partial_entry_then_sl_trigger_cancels_tp_and_sells_the_position(app, client, make_client):
    await app.state.service.tick(D("100000"))
    other = await make_client()
    assert (await other.post("/api/orders", json={"side": "buy", "type": "market", "qty": "0.0008"})).status_code == 200

    entry = await client.post(
        "/api/orders",
        json={"side": "buy", "type": "limit", "qty": "0.0005", "price": "99960.00", "sl": "99955.00", "tp": "101000.00"},
    )
    assert entry.status_code == 200, entry.text
    entry_id = entry.json()["order"]["order_id"]
    assert entry.json()["order"]["status"] == "open"

    # 1) the entry fills partially -> SL and TP arm with the filled qty
    r = await other.post("/api/orders", json={"side": "sell", "type": "market", "qty": "0.0002"})
    assert r.status_code == 200
    s = (await client.get("/api/state")).json()
    kids = _by_role(s["open_orders"], entry_id)
    assert set(kids) == {"sl", "tp"}
    assert D(kids["tp"]["qty"]) == D("0.0002") and D(kids["sl"]["qty"]) == D("0.0002")
    assert D(s["account"]["btc"]) == D("0.0002")
    assert D(s["account"]["btc_reserved"]) == D("0.0002")

    # 2) a larger sell walks through the entry and trades at 99950 <= SL 99955 -> SL triggers
    r = await other.post("/api/orders", json={"side": "sell", "type": "market", "qty": "0.0005"})
    assert r.status_code == 200
    s = (await client.get("/api/state")).json()
    kids = _by_role(s["history"], entry_id)
    assert kids["tp"]["status"] == "cancelled" and kids["tp"]["reason"] == "sl_triggered"
    assert kids["sl"]["status"] == "filled"
    parent = next(o for o in s["history"] if o["order_id"] == entry_id)
    assert parent["status"] == "filled" or (parent["status"] == "cancelled" and parent["reason"] == "sl_triggered")
    assert D(s["account"]["btc"]) == 0
    assert D(s["account"]["btc_reserved"]) == 0
    assert s["open_orders"] == []
    sl_fills = [f for f in s["fills"] if f["order_id"] == kids["sl"]["order_id"]]
    assert sum(D(f["qty"]) for f in sl_fills) == D("0.0005")
    totals = (await client.get("/api/internal/totals")).json()
    assert D(totals["usd"]["total"]) == 0 and D(totals["btc"]["total"]) == 0


async def test_a_market_entry_with_sl_tp_arms_both_children_at_once(app, client):
    await app.state.service.tick(D("100000"))
    entry = await client.post(
        "/api/orders",
        json={"side": "buy", "type": "market", "qty": "0.0003", "sl": "99000.00", "tp": "101000.00"},
    )
    assert entry.status_code == 200, entry.text
    entry_id = entry.json()["order"]["order_id"]
    s = (await client.get("/api/state")).json()
    kids = _by_role(s["open_orders"], entry_id)
    assert set(kids) == {"sl", "tp"}
    assert kids["tp"]["type"] == "limit" and D(kids["tp"]["price"]) == D("101000")
    assert kids["sl"]["type"] == "stop" and D(kids["sl"]["stop_price"]) == D("99000")
    assert all(k["reduce_only"] is True for k in kids.values())
    assert D(s["account"]["btc_reserved"]) == D("0.0003")


async def test_cancelling_an_unfilled_entry_cancels_its_children(app, client):
    await app.state.service.tick(D("100000"))
    entry = await client.post(
        "/api/orders",
        json={"side": "buy", "type": "limit", "qty": "0.0003", "price": "99000.00", "sl": "98000.00", "tp": "101000.00"},
    )
    entry_id = entry.json()["order"]["order_id"]
    assert (await client.delete(f"/api/orders/{entry_id}")).status_code == 200
    s = (await client.get("/api/state")).json()
    kids = _by_role(s["history"], entry_id)
    assert {k["status"] for k in kids.values()} == {"cancelled"}
    assert {k["reason"] for k in kids.values()} == {"parent_cancelled"}
    assert s["open_orders"] == []
