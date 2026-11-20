"""WS /ws: subscribe, reference/candle/book/trade messages, fill/state only for the cookie's account.

Uses ``starlette.testclient.TestClient`` and drives the app loop through ``client.portal``.
Receives run in a helper thread with a timeout so a missing message fails instead of hanging.
"""

import queue
import threading
import time
import uuid
from decimal import Decimal as D

import pytest
from starlette.testclient import TestClient


class Reader:
    """Pumps a TestClient websocket into a queue on a background thread."""

    def __init__(self, ws):
        self.ws = ws
        self.q: queue.Queue = queue.Queue()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            while True:
                self.q.put(self.ws.receive_json())
        except Exception as e:  # noqa: BLE001 - socket closed at the end of the test
            self.q.put(e)

    def until(self, pred, timeout=5.0):
        seen = []
        deadline = timeout
        import time

        end = time.monotonic() + deadline
        while time.monotonic() < end:
            try:
                m = self.q.get(timeout=max(0.01, end - time.monotonic()))
            except queue.Empty:
                break
            if isinstance(m, Exception):
                break
            seen.append(m)
            if pred(m):
                return m, seen
        raise AssertionError(f"no matching message within {timeout}s; got types {[x.get('type') for x in seen]}")

    def collect(self, seconds=0.5):
        import time

        out = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                m = self.q.get(timeout=max(0.01, end - time.monotonic()))
            except queue.Empty:
                break
            if not isinstance(m, Exception):
                out.append(m)
        return out


@pytest.fixture
def ws_app(make_config, clock):
    from btc_paper_trader.api import create_app

    app = create_app(make_config())
    with TestClient(app, base_url="http://127.0.0.1") as tc:
        yield app, tc, clock


def _connect(tc, aid):
    return tc.websocket_connect("/ws", headers={"cookie": f"account_id={aid}"})


def _tick(app, tc, price):
    tc.portal.call(app.state.service.tick, D(price))


def test_reference_message_carries_price_tick_ts_status_and_server_ts(ws_app):
    app, tc, clock = ws_app
    with _connect(tc, uuid.uuid4().hex) as ws:
        ws.send_json({"type": "subscribe", "tf": "1m"})
        r = Reader(ws)
        _tick(app, tc, "100123.45")
        m, _ = r.until(lambda m: m.get("type") == "reference")
        assert D(m["price"]) == D("100123.45")
        assert m["tick_ts"] == clock.now()
        assert m["status"] == "live"
        assert isinstance(m["server_ts"], int)


def test_subscribed_timeframe_gets_reference_candle_updates(ws_app):
    app, tc, _ = ws_app
    with _connect(tc, uuid.uuid4().hex) as ws:
        ws.send_json({"type": "subscribe", "tf": "5m"})
        r = Reader(ws)
        _tick(app, tc, "100000")
        m, _ = r.until(lambda m: m.get("type") == "candle" and m.get("source") == "reference")
        assert m["tf"] == "5m"


def test_fill_and_state_go_only_to_the_cookies_account(ws_app):
    app, tc, _ = ws_app
    a, b = uuid.uuid4().hex, uuid.uuid4().hex
    with _connect(tc, a) as wa, _connect(tc, b) as wb:
        wa.send_json({"type": "subscribe", "tf": "1m"})
        wb.send_json({"type": "subscribe", "tf": "1m"})
        ra, rb = Reader(wa), Reader(wb)
        _tick(app, tc, "100000")
        r = tc.post(
            "/api/orders",
            json={"side": "buy", "type": "market", "quote_amount": "20"},
            headers={"cookie": f"account_id={a}"},
        )
        assert r.status_code == 200, r.text
        fill, _ = ra.until(lambda m: m.get("type") == "fill")
        assert D(fill["price"]) == D("100050")
        assert fill["order_id"] == r.json()["order"]["order_id"]
        state, _ = ra.until(lambda m: m.get("type") == "state")
        assert D(state["account"]["usd"]) < D("81")
        trade, _ = rb.until(lambda m: m.get("type") == "trade")
        assert D(trade["price"]) == D("100050")
        others = rb.collect(0.5)
        assert not [m for m in others if m.get("type") in ("fill", "state")]


def test_book_is_throttled_to_one_message_per_100ms_and_only_when_changed(ws_app):
    app, tc, clock = ws_app
    with _connect(tc, uuid.uuid4().hex) as ws:
        ws.send_json({"type": "subscribe", "tf": "1m"})
        r = Reader(ws)
        for p in ("100000", "100010", "100020", "100030", "100040"):
            _tick(app, tc, p)
        tc.portal.call(clock.advance, 100)
        first = [m for m in r.collect(0.7) if m.get("type") == "book"]
        assert len(first) == 1
        assert first[0]["bids"] and first[0]["asks"]
        assert D(first[0]["bids"][0][0]) == D("99989.98")  # latest requote: floor(100040 * 0.9995)
        tc.portal.call(clock.advance, 100)
        tc.portal.call(clock.advance, 100)
        unchanged = [m for m in r.collect(0.5) if m.get("type") == "book"]
        assert unchanged == []


def test_healthz_counts_connected_ws_clients(ws_app):
    app, tc, _ = ws_app
    with _connect(tc, uuid.uuid4().hex) as ws:
        ws.send_json({"type": "subscribe", "tf": "1m"})
        Reader(ws)
        _tick(app, tc, "100000")
        assert tc.get("/healthz").json()["ws_clients"] == 1


def test_ws_with_a_new_cookie_creates_the_account(ws_app):
    app, tc, _ = ws_app
    aid = uuid.uuid4().hex
    with _connect(tc, aid) as ws:
        ws.send_json({"type": "subscribe", "tf": "1m"})
        r = Reader(ws)
        _tick(app, tc, "100000")
        r.until(lambda m: m.get("type") == "reference")
    assert app.state.service.engine.account(aid) is not None
