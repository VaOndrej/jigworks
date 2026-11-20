"""Async quality rules A1 (runtime), A2 and A3."""

import ast
import asyncio
import inspect
import time
import uuid
from pathlib import Path

EXPECTED_ROUTES = {
    ("GET", "/"),
    ("GET", "/healthz"),
    ("GET", "/api/reference/candles"),
    ("GET", "/api/candles"),
    ("GET", "/api/book"),
    ("GET", "/api/trades"),
    ("GET", "/api/state"),
    ("POST", "/api/orders"),
    ("DELETE", "/api/orders/{order_id}"),
    ("POST", "/api/position/close"),
    ("POST", "/api/account/reset"),
    ("GET", "/api/internal/totals"),
}


def _src_root() -> Path:
    import btc_paper_trader

    return Path(btc_paper_trader.__file__).parent


def test_every_route_and_the_websocket_endpoint_are_coroutine_functions(make_config):
    """A2."""
    from fastapi.routing import APIRoute, APIWebSocketRoute
    from starlette.routing import WebSocketRoute

    from btc_paper_trader.api import create_app

    app = create_app(make_config())
    seen = set()
    ws_paths = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            assert inspect.iscoroutinefunction(route.endpoint), route.path
            for m in route.methods:
                seen.add((m, route.path))
        elif isinstance(route, (APIWebSocketRoute, WebSocketRoute)):
            assert inspect.iscoroutinefunction(route.endpoint), route.path
            ws_paths.add(route.path)
    normalized = {(m, p.replace("{id}", "{order_id}")) for m, p in seen}
    missing = EXPECTED_ROUTES - normalized
    assert not missing, f"missing routes: {sorted(missing)}"
    assert "/ws" in ws_paths


def _violations(path: Path, forbid_open: bool) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in ("requests", "sqlite3", "urllib.request") or a.name.startswith("requests."):
                    out.append(f"{path.name}:{node.lineno} import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in ("requests", "sqlite3", "urllib.request") or mod.startswith("requests."):
                out.append(f"{path.name}:{node.lineno} from {mod} import")
            if mod == "urllib" and any(a.name == "request" for a in node.names):
                out.append(f"{path.name}:{node.lineno} from urllib import request")
            if mod == "time" and any(a.name == "sleep" for a in node.names):
                out.append(f"{path.name}:{node.lineno} from time import sleep")
        elif isinstance(node, ast.Call):
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "sleep"
                and isinstance(f.value, ast.Name)
                and f.value.id == "time"
            ):
                out.append(f"{path.name}:{node.lineno} time.sleep()")
            if forbid_open and isinstance(f, ast.Name) and f.id == "open":
                out.append(f"{path.name}:{node.lineno} open()")
    return out


def test_source_has_no_blocking_calls():
    """A3: no time.sleep, requests, urllib.request, sqlite3; no open() in the hot modules."""
    root = _src_root()
    files = sorted(root.rglob("*.py"))
    assert files, "package sources not found"
    hot = {"api.py", "exchange.py", "broadcast.py", "bots.py"}
    found = []
    for f in files:
        forbid_open = f.name in hot or "feeds" in f.relative_to(root).parts
        found += _violations(f, forbid_open)
    assert not found, "\n".join(found)


def test_the_ast_scan_itself_detects_violations(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import time, sqlite3\nimport requests\ntime.sleep(1)\nopen('x')\n")
    assert len(_violations(bad, forbid_open=True)) == 4


async def test_loop_lag_stays_under_100ms_with_200_bots_house_and_50_ws_clients(make_config, loop_lag):
    """A1 (runtime part): 5 s at real speed with the sim feed ticking every 500 ms."""
    from btc_paper_trader.service import Service

    cfg = make_config(
        bots=200,
        sim_manual=False,
        sim_tick_ms=500,
        clock=lambda: int(time.time() * 1000),
        sleep=asyncio.sleep,
    )
    svc = Service(cfg)
    async with svc.running():
        queues = [svc.broadcaster.register(uuid.uuid4().hex) for _ in range(50)]
        received = [0] * len(queues)

        async def reader(i, q):
            while True:
                received[i] += len(q.drain())
                await asyncio.sleep(0.01)

        readers = [asyncio.create_task(reader(i, q)) for i, q in enumerate(queues)]
        try:
            async with loop_lag() as lag:
                await asyncio.sleep(5)
        finally:
            for t in readers:
                t.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
        bot_orders = sum(len(svc.engine.orders(f"bot-{i:04d}", open_only=False)) for i in range(1, 201))
    assert bot_orders > 0, "the bots must trade during the run"
    assert sum(received) > 0, "WS clients must receive messages"
    assert lag.max_ms < 100, f"max loop lag {lag.max_ms:.1f} ms"
