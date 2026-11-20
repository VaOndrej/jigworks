"""The HTTP and WebSocket API. Every route is a coroutine function; nothing here blocks the loop."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from .broadcast import Broadcaster, ClientQueue, Shared
from .candles import TIMEFRAMES
from .config import Config
from .exchange import Closed
from .matching import OrderRequest, Result
from .money import dstr
from .service import Service
from .views import book_json, candle_json, order_json, state_body, trade_json

STATIC_DIR = Path(__file__).parent / "static"
ACCOUNT_COOKIE = "account_id"
HEX32 = re.compile(r"^[0-9a-f]{32}$")
COOKIE_MAX_AGE = 365 * 24 * 3600
ACCOUNT_PATHS = ("/api/state", "/api/orders", "/api/position/close", "/api/account/reset")
WS_SEND_TIMEOUT_S = 10


def _needs_account(path: str) -> bool:
    return path == "/" or any(path == p or path.startswith(p + "/") for p in ACCOUNT_PATHS)


def _cookie_from_headers(headers: list[tuple[bytes, bytes]]) -> str | None:
    for name, value in headers:
        if name == b"cookie":
            for part in value.decode("latin-1").split(";"):
                key, _, val = part.strip().partition("=")
                if key == ACCOUNT_COOKIE:
                    return val
    return None


class AccountCookieMiddleware:
    """An unknown ``account_id`` cookie lazily creates exactly one $100 account (no login)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not _needs_account(scope["path"]):
            await self.app(scope, receive, send)
            return
        cookie = _cookie_from_headers(scope["headers"])
        is_new = cookie is None or not HEX32.match(cookie)
        account_id = uuid.uuid4().hex if is_new else cookie
        service: Service = scope["app"].state.service
        try:
            if service.engine.account(account_id) is None:
                async with asyncio.timeout(service.config.ack_timeout_s):
                    await service.exchange.open_account(account_id)
        except (TimeoutError, Closed):
            response = JSONResponse({"reason": "overloaded"}, status_code=503)
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["account_id"] = account_id

        async def send_with_cookie(message) -> None:
            if is_new and message["type"] == "http.response.start":
                value = f"{ACCOUNT_COOKIE}={account_id}; HttpOnly; Max-Age={COOKIE_MAX_AGE}; Path=/; SameSite=lax"
                message = {**message, "headers": [*message.get("headers", []), (b"set-cookie", value.encode())]}
            await send(message)

        await self.app(scope, receive, send_with_cookie)


def _reason(status: int, reason: str, **extra) -> JSONResponse:
    return JSONResponse({"reason": reason, **extra}, status_code=status)


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("bool is not a number")
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError("not a number") from exc
    if not d.is_finite():
        raise ValueError("not finite")
    return d


def _parse_order(account_id: str, body) -> OrderRequest | None:
    """None when the body is not even well-formed; the engine judges everything else."""
    if not isinstance(body, dict):
        return None
    side, type_ = body.get("side"), body.get("type")
    if side not in ("buy", "sell") or type_ not in ("market", "limit", "stop"):
        return None
    max_ = body.get("max", False)
    reduce_only = body.get("reduce_only", False)
    if not isinstance(max_, bool) or not isinstance(reduce_only, bool):
        return None
    try:
        return OrderRequest(
            account_id=account_id,
            side=side,
            type=type_,
            qty=_decimal(body.get("qty")),
            quote_amount=_decimal(body.get("quote_amount")),
            max=max_,
            price=_decimal(body.get("price")),
            stop_price=_decimal(body.get("stop_price")),
            reduce_only=reduce_only,
            sl=_decimal(body.get("sl")),
            tp=_decimal(body.get("tp")),
        )
    except ValueError:
        return None


def _order_response(res: Result) -> JSONResponse:
    o = res.order
    if o is None:
        return _reason(422, res.reason or "invalid_order")
    mine = [t for t in res.trades if o.order_id in (t.buy_order_id, t.sell_order_id)]
    if o.status == "rejected":
        return _reason(422, o.reason, order=order_json(o))
    return JSONResponse({"order": order_json(o), "trades": [trade_json(t) for t in mine]})


def create_app(config: Config) -> FastAPI:
    service = Service(config)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async with service.running():
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.add_middleware(AccountCookieMiddleware)
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    async def ack(coro):
        """Await a command ack; None means back-pressure (queue full or shutting down)."""
        try:
            async with asyncio.timeout(config.ack_timeout_s):
                return await coro
        except (TimeoutError, Closed):
            return None

    @app.get("/")
    async def index():
        return HTMLResponse(index_html)

    @app.get("/healthz")
    async def healthz():
        return JSONResponse(service.health())

    def _tf(tf: str) -> str | None:
        return tf if tf in TIMEFRAMES else None

    @app.get("/api/reference/candles")
    async def reference_candles(tf: str = "1m"):
        if _tf(tf) is None:
            return _reason(422, "invalid_timeframe")
        return JSONResponse([candle_json(c) for c in service.ref_series[tf].candles()])

    @app.get("/api/candles")
    async def internal_candles(tf: str = "1m"):
        if _tf(tf) is None:
            return _reason(422, "invalid_timeframe")
        return JSONResponse([candle_json(c) for c in service.trade_candles.candles(tf)])

    @app.get("/api/book")
    async def book(depth: int = Query(20, ge=1, le=50)):
        return JSONResponse(book_json(service.engine, depth, config.clock()))

    @app.get("/api/trades")
    async def trades(limit: int = Query(100, ge=1, le=500)):
        tape = list(service.engine.tape)[-limit:]
        return JSONResponse([trade_json(t) for t in reversed(tape)])

    @app.get("/api/state")
    async def state(request: Request):
        return JSONResponse(state_body(service.engine, request.state.account_id))

    @app.post("/api/orders")
    async def place_order(request: Request):
        try:
            body = await request.json()
        except ValueError:
            return _reason(422, "invalid_order")
        req = _parse_order(request.state.account_id, body)
        if req is None:
            return _reason(422, "invalid_order")
        res = await ack(service.exchange.submit(req))
        if res is None:
            return _reason(503, "overloaded")
        return _order_response(res)

    @app.delete("/api/orders/{order_id}")
    async def cancel_order(order_id: int, request: Request):
        res = await ack(service.exchange.cancel(request.state.account_id, order_id))
        if res is None:
            return _reason(503, "overloaded")
        if res.order is None:
            return _reason(404, "not_found")
        return JSONResponse({"order": order_json(res.order)})

    @app.post("/api/position/close")
    async def close_position(request: Request):
        res = await ack(service.exchange.close_position(request.state.account_id))
        if res is None:
            return _reason(503, "overloaded")
        return _order_response(res)

    @app.post("/api/account/reset")
    async def reset_account(request: Request):
        aid = request.state.account_id
        res = await ack(service.exchange.reset(aid))
        if res is None:
            return _reason(503, "overloaded")
        return JSONResponse({"state": state_body(service.engine, aid)})

    @app.get("/api/internal/totals")
    async def totals():
        out = {a: {k: dstr(v) for k, v in g.items()} for a, g in service.engine.totals().items()}
        return JSONResponse(out)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        cookie = ws.cookies.get(ACCOUNT_COOKIE)
        account_id = cookie if cookie and HEX32.match(cookie) else uuid.uuid4().hex
        if service.engine.account(account_id) is None:
            if await ack(service.exchange.open_account(account_id)) is None:
                await ws.close(code=1013)
                return
        # Register before accepting, so nothing published after the handshake can be missed.
        q = service.broadcaster.register(account_id)
        await ws.accept()
        writer = asyncio.create_task(_ws_writer(ws, q, service.broadcaster), name="ws-writer")
        try:
            with contextlib.suppress(WebSocketDisconnect):  # a normal client disconnect ends the loop
                while True:
                    try:
                        msg = json.loads(await ws.receive_text())
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "subscribe" and msg.get("tf") in TIMEFRAMES:
                        q.tf = msg["tf"]
                        _push_snapshot(service, q)
        finally:
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)
            service.broadcaster.unregister(q)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _push_snapshot(service: Service, q: ClientQueue) -> None:
    """On subscribe, give the client the latest candle of its timeframe right away."""
    ts = service.config.clock()
    ref = service.ref_series[q.tf].last()
    internal = service.trade_candles.last(q.tf)
    if ref is not None:
        q.push({"type": "candle", "source": "reference", "tf": q.tf, "server_ts": ts, **candle_json(ref)})
    if internal is not None:
        q.push({"type": "candle", "source": "internal", "tf": q.tf, "server_ts": ts, **candle_json(internal)})


def _writer_period(clients: int) -> float:
    """Seconds a client writer lets messages pile up (and coalesce) before it sends.

    One WebSocket frame costs the same for every client, so the period grows with the number of
    clients: 0.1 s for a handful, 0.4 s for 1,000.
    """
    return min(0.5, max(0.1, 0.0004 * clients))


OVERLOAD_CLIENTS = 250  # above this many sockets, per-trade frames cost more than one process can send


def _thin_trades(msgs: list[dict]) -> list[dict]:
    """Real overload only: keep the newest trade (the last price) of a batch, drop older ones."""
    last = max((i for i, m in enumerate(msgs) if m.get("type") == "trade"), default=-1)
    return [m for i, m in enumerate(msgs) if m.get("type") != "trade" or i == last]


def _encode(m: dict) -> str:
    return m.text() if isinstance(m, Shared) else json.dumps(m, separators=(",", ":"))


async def _ws_writer(ws: WebSocket, q: ClientQueue, broadcaster: Broadcaster) -> None:
    try:
        while True:
            await q.wait()
            if q.closed:
                break
            if not q.must_pending():  # fills and state go out at once; the rest is batched
                await asyncio.sleep(_writer_period(broadcaster.client_count))
                if q.closed:
                    break
            batch = q.drain()
            if broadcaster.client_count > OVERLOAD_CLIENTS:
                batch = _thin_trades(batch)
            for m in batch:
                async with asyncio.timeout(WS_SEND_TIMEOUT_S):
                    await ws.send_text(_encode(m))
        with contextlib.suppress(Exception):
            await ws.close(code=q.close_code or 1013)
    except (WebSocketDisconnect, RuntimeError, TimeoutError):
        return
