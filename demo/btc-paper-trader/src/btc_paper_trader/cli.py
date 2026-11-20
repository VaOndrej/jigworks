"""Command line: ``btc-paper-trader --bots 1000`` serves http://127.0.0.1:8000.

One process, one asyncio event loop (uvloop when available): uvicorn and the service share it.
The host is fixed to 127.0.0.1; there is deliberately no flag to change it.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import webbrowser
from decimal import Decimal
from pathlib import Path

from .config import DEFAULT_BINANCE_BASE, DEFAULT_DB, HOST, Config
from .logs import setup_logging

MAX_OPEN_FILES = 10_240


def parse_args(argv: list[str] | None = None) -> Config:
    p = argparse.ArgumentParser(prog="btc-paper-trader", description="Local BTC/USD paper-trading exchange.")
    p.add_argument("--feed", choices=["binance", "sim"], default="binance", help="reference price source")
    p.add_argument("--seed", type=int, default=0, help="seed for the sim feed and the bots")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file")
    p.add_argument("--bots", type=int, default=0, help="number of in-process bots")
    p.add_argument("--no-browser", action="store_true", help="do not open the browser")
    p.add_argument("--binance-base", default=DEFAULT_BINANCE_BASE)
    p.add_argument("--sim-tick-ms", type=int, default=500)
    p.add_argument("--house-usd", type=Decimal, default=Decimal("200000"))
    p.add_argument("--house-btc", type=Decimal, default=Decimal("2"))
    p.add_argument("--house-levels", type=int, default=10)
    p.add_argument("--house-spread-bps", type=int, default=10)
    a = p.parse_args(argv)
    return Config(
        feed=a.feed,
        seed=a.seed,
        db=a.db,
        bots=a.bots,
        port=a.port,
        open_browser=not a.no_browser,
        binance_base=a.binance_base,
        sim_tick_ms=a.sim_tick_ms,
        house_usd=a.house_usd,
        house_btc=a.house_btc,
        house_levels=a.house_levels,
        house_spread_bps=a.house_spread_bps,
    )


def raise_file_limit() -> None:
    """Thousands of WebSocket clients need thousands of file descriptors."""
    with contextlib.suppress(ImportError, ValueError, OSError):
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = MAX_OPEN_FILES if hard == resource.RLIM_INFINITY else min(hard, MAX_OPEN_FILES)
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))


async def run(config: Config) -> None:
    import uvicorn

    from .api import create_app

    app = create_app(config)
    server = uvicorn.Server(
        uvicorn.Config(app, host=HOST, port=config.port, log_level="warning", lifespan="on", access_log=False)
    )
    opener = None
    if config.open_browser:

        async def open_when_started() -> None:
            while not server.started:
                await asyncio.sleep(0.05)
            await asyncio.to_thread(webbrowser.open, f"http://{HOST}:{config.port}")

        opener = asyncio.create_task(open_when_started())
    try:
        await server.serve()
    finally:
        if opener is not None:
            opener.cancel()
    if not server.started:
        raise RuntimeError("the server failed to start")


def main(argv: list[str] | None = None) -> None:
    config = parse_args(argv)
    raise_file_limit()
    listener = setup_logging()
    try:
        try:
            import uvloop

            loop_factory = uvloop.new_event_loop
        except ImportError:
            loop_factory = None
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(run(config), loop_factory=loop_factory)
    except BaseException as exc:  # noqa: BLE001 - report and exit non-zero
        print(f"btc-paper-trader failed: {exc!r}", file=sys.stderr)
        listener.stop()
        sys.exit(1)
    listener.stop()
