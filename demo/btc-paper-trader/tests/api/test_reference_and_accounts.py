"""M1 API: cookie accounts, /healthz, reference candles, the page.

Candles over HTTP are JSON lists of objects with ``open_time_ms, open, high, low, close, volume``
(Decimals as strings).
"""

import asyncio
import re
import uuid
from decimal import Decimal as D

import httpx

HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _anon(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")


async def test_first_visit_sets_an_httponly_lax_one_year_account_cookie(app):
    async with _anon(app) as c:
        r = await c.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        header = r.headers["set-cookie"]
        assert header.startswith("account_id=")
        assert "httponly" in header.lower()
        assert "samesite=lax" in header.lower()
        m = re.search(r"max-age=(\d+)", header.lower())
        assert m and int(m.group(1)) >= 365 * 24 * 3600 - 1
        assert HEX32.match(c.cookies["account_id"])


async def test_a_new_cookie_gets_exactly_one_100_dollar_account(app):
    async with _anon(app) as c:
        await c.get("/")
        state = (await c.get("/api/state")).json()
        assert D(state["account"]["usd"]) == D("100")
        assert D(state["account"]["btc"]) == D("0")
        assert D(state["account"]["equity"]) == D("100")
        totals = (await c.get("/api/internal/totals")).json()
        assert D(totals["usd"]["accounts"]) == D("100")


async def test_twenty_concurrent_requests_with_the_same_new_cookie_create_one_account(app):
    aid = uuid.uuid4().hex
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", cookies={"account_id": aid}
    ) as c:
        responses = await asyncio.gather(*(c.get("/api/state") for _ in range(20)))
        assert all(r.status_code == 200 for r in responses)
        totals = (await c.get("/api/internal/totals")).json()
    assert D(totals["usd"]["accounts"]) == D("100")
    assert D(totals["usd"]["total"]) == 0
    assert app.state.service.engine.account(aid).usd == D("100")


async def test_a_malformed_cookie_is_replaced_by_a_fresh_id(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        cookies={"account_id": "not-a-valid-id"},
    ) as c:
        r = await c.get("/api/state")
        assert r.status_code == 200
        new = r.cookies.get("account_id")
        assert new and HEX32.match(new)


async def test_a_well_formed_unknown_cookie_becomes_an_account_with_that_id(app):
    aid = uuid.uuid4().hex
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", cookies={"account_id": aid}
    ) as c:
        assert (await c.get("/api/state")).status_code == 200
    assert app.state.service.engine.account(aid) is not None


async def test_healthz_reports_feed_status_age_and_loop_lag(app, client):
    await app.state.service.tick(D("100000"))
    body = (await client.get("/healthz")).json()
    for key in ("feed", "status", "last_tick_age_ms", "reference_price", "queue_depth", "loop_lag_ms", "ws_clients"):
        assert key in body, key
    assert body["feed"] == "sim"
    assert body["status"] == "live"
    assert D(body["reference_price"]) == D("100000")
    assert set(body["loop_lag_ms"]) >= {"max", "p99"}
    assert body["queue_depth"] >= 0
    assert body["ws_clients"] == 0


async def test_reference_candles_return_500_aligned_candles_per_timeframe(client):
    tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
    for tf, ms in tf_ms.items():
        r = await client.get("/api/reference/candles", params={"tf": tf})
        assert r.status_code == 200, tf
        candles = r.json()
        assert len(candles) == 500, tf
        times = [c["open_time_ms"] for c in candles]
        assert times == sorted(set(times))
        assert all(t % ms == 0 for t in times)
        c = candles[-1]
        assert isinstance(c["close"], str)
        assert D(c["high"]) >= max(D(c["open"]), D(c["close"]))


async def test_a_reference_tick_updates_the_latest_1m_reference_candle(app, client, clock):
    await app.state.service.tick(D("123456.78"))
    candles = (await client.get("/api/reference/candles", params={"tf": "1m"})).json()
    last = candles[-1]
    assert last["open_time_ms"] == clock.now() // 60_000 * 60_000
    assert D(last["close"]) == D("123456.78")


async def test_unknown_timeframe_is_a_422(client):
    r = await client.get("/api/reference/candles", params={"tf": "2m"})
    assert r.status_code == 422


async def test_the_page_contains_the_chart_and_the_feed_badge(client):
    html = (await client.get("/")).text
    assert 'data-testid="chart"' in html
    assert 'data-testid="feed-status"' in html
