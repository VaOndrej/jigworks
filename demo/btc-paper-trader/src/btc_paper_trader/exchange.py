"""The exchange task: one asyncio task owns the engine (single writer, so no locks).

Producers (HTTP handlers, bots, the feed) enqueue commands and await a future. The task takes the
first command, drains up to ``max_batch`` more without waiting, applies them all to the pure
``Engine``, commits one store transaction for the whole batch, resolves the futures and then
tells the observers (the WebSocket fan-out) what happened.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from .accounts import START_USD
from .house import HouseConfig
from .matching import Engine, OrderRequest, Result

log = logging.getLogger(__name__)

MAX_BATCH = 500


class Closed(Exception):
    """The exchange is shutting down and takes no new commands."""


@dataclass(slots=True)
class Command:
    kind: str
    args: tuple
    future: asyncio.Future
    enqueued_ms: int


class ExchangeTask:
    def __init__(
        self,
        engine: Engine,
        store,
        clock: Callable[[], int],
        maxsize: int = 10_000,
        house: HouseConfig | None = None,
        max_batch: int = MAX_BATCH,
    ) -> None:
        self.engine = engine
        self.store = store
        self.clock = clock
        self.house = house
        self.max_batch = max_batch
        self._queue: asyncio.Queue[Command] = asyncio.Queue(maxsize)
        self._pending = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._closing = False
        self._last_meta: dict | None = None
        self.observers: list[Callable[[Command, Result | None], None]] = []

    # --- async API ------------------------------------------------------------------------------

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    async def submit(self, req: OrderRequest) -> Result:
        return await self._call("submit", req)

    async def cancel(self, account_id: str, order_id: int) -> Result:
        return await self._call("cancel", account_id, order_id)

    async def reset(self, account_id: str) -> Result:
        return await self._call("reset", account_id)

    async def close_position(self, account_id: str) -> Result:
        return await self._call("close", account_id)

    async def open_account(
        self, account_id: str, kind: str = "user", usd: Decimal = START_USD, btc: Decimal = Decimal(0)
    ) -> Result:
        return await self._call("open_account", account_id, kind, usd, btc)

    async def tick(self, price: Decimal, ts_ms: int) -> Result:
        """A reference tick; the house requotes in the same batch."""
        return await self._call("tick", price, ts_ms)

    def try_submit(self, req: OrderRequest) -> bool:
        return self._try("submit", req)

    def try_cancel(self, account_id: str, order_id: int) -> bool:
        return self._try("cancel", account_id, order_id)

    async def idle(self) -> None:
        """Return once the queue is empty and the last batch is committed and published."""
        await self._idle.wait()

    async def drain(self) -> None:
        """Stop taking commands and finish what is queued."""
        self._closing = True
        await self._idle.wait()

    # --- enqueueing -----------------------------------------------------------------------------

    def _make(self, kind: str, args: tuple) -> Command:
        if self._closing:
            raise Closed()
        fut = asyncio.get_running_loop().create_future()
        return Command(kind, args, fut, self.clock())

    async def _call(self, kind: str, *args) -> Result:
        cmd = self._make(kind, args)
        self._pending += 1
        self._idle.clear()
        try:
            await self._queue.put(cmd)
        except BaseException:
            self._done(1)
            raise
        return await cmd.future

    def _try(self, kind: str, *args) -> bool:
        """Fire-and-forget enqueue that never waits; False when the queue is full."""
        cmd = self._make(kind, args)
        try:
            self._queue.put_nowait(cmd)
        except asyncio.QueueFull:
            return False
        self._pending += 1
        self._idle.clear()
        cmd.future.add_done_callback(_consume)
        return True

    def _done(self, n: int) -> None:
        self._pending -= n
        if self._pending <= 0:
            self._pending = 0
            self._idle.set()

    # --- the single writer ----------------------------------------------------------------------

    def _apply(self, cmd: Command) -> Result:
        eng, now, a = self.engine, self.clock(), cmd.args
        match cmd.kind:
            case "submit":
                return eng.submit(a[0], now)
            case "cancel":
                return eng.cancel(a[0], a[1], now)
            case "reset":
                return eng.reset(a[0], now)
            case "close":
                return eng.close_position(a[0], now)
            case "open_account":
                return eng.open_account(a[0], kind=a[1], now_ms=now, usd=a[2], btc=a[3])
            case "tick":
                eng.reference_tick(a[0], a[1])
                if self.house is not None:
                    return eng.house_requote(self.house, now)
                return Result()
        raise ValueError(f"unknown command {cmd.kind!r}")

    async def run(self) -> None:
        queue = self._queue
        while True:
            batch = [await queue.get()]
            while len(batch) < self.max_batch:
                try:
                    batch.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            outcomes: list[tuple[Command, Result | None, Exception | None]] = []
            for cmd in batch:
                try:
                    outcomes.append((cmd, self._apply(cmd), None))
                except Exception as exc:  # an engine bug must not take the exchange down
                    log.exception("command %s failed", cmd.kind)
                    outcomes.append((cmd, None, exc))
            journal = self.engine.drain_journal()
            if not journal.empty() or journal.meta != self._last_meta:
                try:
                    await self.store.commit(journal)
                except BaseException as exc:
                    for cmd, _, _ in outcomes:
                        if not cmd.future.done():
                            cmd.future.set_exception(exc if isinstance(exc, Exception) else RuntimeError("cancelled"))
                    self._done(len(batch))
                    raise
                self._last_meta = journal.meta
            for cmd, res, err in outcomes:
                if cmd.future.done():
                    continue
                if err is not None:
                    cmd.future.set_exception(err)
                else:
                    cmd.future.set_result(res)
            for cmd, res, err in outcomes:
                if res is not None:
                    for observer in self.observers:
                        try:
                            observer(cmd, res)
                        except Exception:
                            log.exception("observer failed")
            self._done(len(batch))
            await asyncio.sleep(0)


def _consume(fut: asyncio.Future) -> None:
    if not fut.cancelled():
        fut.exception()  # mark retrieved; fire-and-forget callers never look at it
