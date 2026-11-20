"""Load test (opt-in, BTC_LOAD=1): 1,000 HTTP+WS clients against uvicorn with --bots 1000.

Asserts global conservation over the API and that every client's WS fills match its
/api/state fills; prints p95 order->ack, p95 tick->push and the server loop lag as a Markdown row.
Duration: BTC_LOAD_SECONDS (default 60).
"""

import asyncio
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import time
import uuid
from decimal import Decimal as D
from pathlib import Path

import pytest

pytestmark = pytest.mark.load

PKG = Path(__file__).resolve().parents[2]
CLIENTS = 1000


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _p95(xs):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * 0.95))]


@pytest.fixture
def server(tmp_path):
    port = _free_port()
    cmd = [
        str(Path(sys.executable).parent / "btc-paper-trader"), "--feed", "sim", "--seed", "1", "--bots", "1000",
        "--no-browser", "--port", str(port), "--db", str(tmp_path / "load.db"),
    ]
    proc = subprocess.Popen(cmd, cwd=PKG, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # nosec B603
    import httpx

    url = f"127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://{url}/healthz", timeout=1).json().get("status") == "live":
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("server did not start: " + proc.stderr.read().decode()[-2000:])
    yield url
    proc.terminate()
    proc.wait(timeout=30)


async def _run(host, seconds):
    import httpx
    import websockets

    acks, pushes = [], []
    errors = {"5xx": 0, "overloaded": 0}
    ws_fills = {}
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=100)
    async with httpx.AsyncClient(base_url=f"http://{host}", limits=limits, timeout=30) as http:

        async def client(i):
            aid = uuid.uuid4().hex
            ws_fills[aid] = set()
            cookie = {"account_id": aid}
            rng = random.Random(i)
            async with websockets.connect(f"ws://{host}/ws", additional_headers={"cookie": f"account_id={aid}"}) as ws:
                await ws.send(json.dumps({"type": "subscribe", "tf": "1m"}))

                async def reader():
                    async for raw in ws:
                        m = json.loads(raw)
                        if m.get("type") == "reference" and "tick_ts" in m:
                            pushes.append(time.time() * 1000 - m["tick_ts"])
                        elif m.get("type") == "fill":
                            ws_fills[aid].add((m.get("trade_id"), m.get("order_id")))

                rt = asyncio.create_task(reader())
                end = time.monotonic() + seconds
                await asyncio.sleep(rng.random() * 5)
                while time.monotonic() < end:
                    side = rng.choice(["buy", "sell"])
                    body = {"side": side, "type": "market", "max": True} if side == "sell" else {
                        "side": "buy", "type": "market", "quote_amount": str(rng.randint(2, 10))}
                    t0 = time.perf_counter()
                    r = await http.post("/api/orders", json=body, cookies=cookie)
                    acks.append((time.perf_counter() - t0) * 1000)
                    if r.status_code == 503:
                        errors["overloaded"] += 1
                    elif r.status_code >= 500:
                        errors["5xx"] += 1
                    await asyncio.sleep(4 + rng.random() * 2)
                await asyncio.sleep(2)
                rt.cancel()
            state = (await http.get("/api/state", cookies=cookie)).json()
            api_fills = {(f.get("trade_id"), f.get("order_id")) for f in state["fills"]}
            return aid, api_fills

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(client(i)) for i in range(CLIENTS)]
        results = [t.result() for t in tasks]
        totals = (await http.get("/api/internal/totals")).json()
        health = (await http.get("/healthz")).json()
    return acks, pushes, errors, ws_fills, results, totals, health


def test_1000_clients_keep_conservation_and_report_latency(server):
    seconds = int(os.environ.get("BTC_LOAD_SECONDS", "60"))
    acks, pushes, errors, ws_fills, results, totals, health = asyncio.run(_run(server, seconds))
    assert errors["5xx"] == 0, errors
    for aid, api_fills in results:
        assert ws_fills[aid] == api_fills, aid
    assert D(totals["usd"]["total"]) == 0
    assert D(totals["btc"]["total"]) == 0
    lag = health["loop_lag_ms"]
    print()
    print("| clients | bots | seconds | orders | 503 overloaded | p95 order->ack ms | p95 tick->push ms | loop lag max ms | loop lag p99 ms |")
    print("|---|---|---|---|---|---|---|---|---|")
    print(
        f"| {CLIENTS} | 1000 | {seconds} | {len(acks)} | {errors['overloaded']} | {_p95(acks):.1f} | "
        f"{_p95(pushes):.1f} | {lag['max']} | {lag['p99']} |"
    )
    assert statistics.mean(acks) >= 0
