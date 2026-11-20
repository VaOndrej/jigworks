"""The service: owns one TaskGroup with every long-running task of the process.

``Service.running()`` loads state, starts the exchange task, the feed, the stale watchdog, the
loop-lag monitor, the book throttle and the bot scheduler as children of one ``TaskGroup``, and on
exit stops the producers, drains and commits the exchange queue, then cancels the rest.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from decimal import Decimal

from .broadcast import Broadcaster
from .bots import BotPool
from .candles import TIMEFRAMES, CandleSeries
from .config import Config
from .exchange import Command, ExchangeTask
from .feeds.base import Tick
from .feeds.binance import BinanceFeed
from .feeds.sim import SimFeed
from .house import HouseConfig
from .logs import log_event
from .looplag import LoopLagMonitor
from .matching import Engine, Result
from .money import dstr
from .store import SqliteStore
from .trade_candles import TradeCandles
from .views import book_json, candle_json, state_body, trade_json

STALE_AFTER_MS = 10_000
BOOK_PERIOD_S = 0.1
BOOK_DEPTH = 20
SPECIAL_ACCOUNTS = ("house", "fees", "treasury")


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.store = SqliteStore(config.db)
        self.engine: Engine = Engine(keep_ledger=False)
        self.exchange: ExchangeTask | None = None
        self.feed: SimFeed | BinanceFeed | None = None
        self.broadcaster = Broadcaster()
        self.looplag = LoopLagMonitor()
        self.trade_candles = TradeCandles()
        self.ref_series: dict[str, CandleSeries] = {tf: CandleSeries(tf) for tf in TIMEFRAMES}
        self.house_cfg = HouseConfig(
            levels=config.house_levels,
            spread_bps=config.house_spread_bps,
            usd=Decimal(config.house_usd),
            btc=Decimal(config.house_btc),
        )
        self.bots = BotPool(config.bots, config.seed) if config.bots > 0 else None
        self._last_book: dict | None = None
        self._stale_logged = False

    # --- lifecycle ------------------------------------------------------------------------------

    def _make_feed(self) -> SimFeed | BinanceFeed:
        c = self.config
        if c.feed == "sim":
            return SimFeed(c.seed, c.clock(), c.sim_tick_ms, c.clock, c.sleep)
        return BinanceFeed(base=c.binance_base, clock=c.clock, sleep=c.sleep)

    async def _load_state(self) -> None:
        await self.store.open()
        records = await self.store.load()
        self.engine = Engine.from_records(records, keep_ledger=False) if records else Engine(keep_ledger=False)
        self.trade_candles = TradeCandles()
        async for chunk in self.store.iter_trades():
            for ms, price, qty in chunk:
                self.trade_candles.apply_trade(ms, price, qty)
        self.feed = self._make_feed()
        if isinstance(self.feed, SimFeed):
            for tf in TIMEFRAMES:
                for candle in await self.feed.history(tf):
                    self.ref_series[tf].upsert(candle)
        else:
            self.feed.on_history = self._on_ref_history
            self.feed.on_candle = self._on_ref_candle

    @contextlib.asynccontextmanager
    async def running(self) -> AsyncIterator[Service]:
        cfg = self.config
        try:
            await self._load_state()
            self.exchange = ExchangeTask(
                self.engine, self.store, cfg.clock, cfg.queue_maxsize, self.house_cfg
            )
            self.exchange.observers.append(self._on_result)
            async with asyncio.TaskGroup() as tg:
                exchange_task = tg.create_task(self.exchange.run(), name="exchange")
                producers = [tg.create_task(self._run_feed(), name="feed")]
                if self.bots is not None:
                    producers.append(
                        tg.create_task(
                            self.bots.run(self.engine, self.exchange, cfg.clock, cfg.sleep), name="bots"
                        )
                    )
                background = [
                    tg.create_task(self._watchdog(), name="watchdog"),
                    tg.create_task(self.looplag.run(), name="looplag"),
                    tg.create_task(self._book_loop(), name="book"),
                ]
                try:
                    await self._ensure_accounts()
                    log_event("service.started", feed=cfg.feed, bots=cfg.bots)
                    yield self
                finally:
                    await self._shutdown(exchange_task, producers, background)
        finally:
            await self.store.close()
            log_event("service.stopped")

    async def _ensure_accounts(self) -> None:
        ex, eng = self.exchange, self.engine
        if eng.account("house") is None:
            await ex.open_account("house", "house", self.house_cfg.usd, self.house_cfg.btc)
        if self.bots is not None:
            missing = [b.account_id for b in self.bots.bots if eng.account(b.account_id) is None]
            for i in range(0, len(missing), 500):
                await asyncio.gather(*(ex.open_account(a, "bot") for a in missing[i : i + 500]))

    async def _shutdown(self, exchange_task: asyncio.Task, producers: list, background: list) -> None:
        # 1. stop producing, 2. drain and commit what is queued, 3. cancel the rest
        for t in producers:
            t.cancel()
        await asyncio.gather(*producers, return_exceptions=True)
        if not exchange_task.done():
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(30):
                    await self.exchange.drain()
        for t in (exchange_task, *background):
            t.cancel()
        await asyncio.gather(exchange_task, *background, return_exceptions=True)

    # --- feed -----------------------------------------------------------------------------------

    async def _run_feed(self) -> None:
        feed = self.feed
        if isinstance(feed, SimFeed) and self.config.sim_manual:
            return
        await feed.run(self._on_tick)

    async def _on_tick(self, tick: Tick) -> None:
        if isinstance(self.feed, SimFeed):
            for series in self.ref_series.values():
                series.apply_tick(tick.ts_ms, tick.price)
        await self.exchange.tick(tick.price, tick.ts_ms)

    async def tick(self, price: Decimal | None = None) -> None:
        """Test helper: push one sim tick (a random step when ``price`` is None) and settle."""
        feed = self.feed
        if not isinstance(feed, SimFeed):
            raise TypeError("tick() drives the sim feed")
        await self._on_tick(feed.step() if price is None else feed.push(price))
        await self.exchange.idle()

    def _on_ref_history(self, tf: str, candles: list) -> None:
        for c in candles:
            self.ref_series[tf].upsert(c)

    def _on_ref_candle(self, tf: str, candle) -> None:
        self.ref_series[tf].upsert(candle)
        self.broadcaster.publish(self._candle_msg("reference", tf, candle))

    def feed_status(self) -> tuple[str, int | None]:
        """``(status, last_tick_age_ms)``; ``stale`` is computed from the injected clock."""
        feed = self.feed
        age = None if feed.last_tick_ms is None else self.config.clock() - feed.last_tick_ms
        if feed.status in ("connecting", "reconnecting") or age is None:
            return (feed.status if feed.status != "live" else "connecting"), age
        return ("stale" if age > STALE_AFTER_MS else "live"), age

    async def _watchdog(self) -> None:
        while True:
            await self.config.sleep(1)
            status, age = self.feed_status()
            if status == "stale" and not self._stale_logged:
                self._stale_logged = True
                log_event("feed.stale", feed=self.config.feed, last_tick_age_ms=age)
            elif status == "live":
                self._stale_logged = False

    def health(self) -> dict:
        status, age = self.feed_status()
        return {
            "feed": self.config.feed,
            "status": status,
            "last_tick_age_ms": age,
            "reference_price": dstr(self.engine.reference_price),
            "queue_depth": self.exchange.queue_depth if self.exchange else 0,
            "loop_lag_ms": self.looplag.snapshot(),
            "ws_clients": self.broadcaster.client_count,
        }

    # --- publishing -----------------------------------------------------------------------------

    def _candle_msg(self, source: str, tf: str, candle) -> dict:
        return {"type": "candle", "source": source, "tf": tf, "server_ts": self.config.clock(), **candle_json(candle)}

    async def _book_loop(self) -> None:
        while True:
            await self.config.sleep(BOOK_PERIOD_S)
            if self.broadcaster.client_count == 0:
                continue
            snap = book_json(self.engine, BOOK_DEPTH, 0)
            comparable = (snap["bids"], snap["asks"])
            if comparable == self._last_book:
                continue
            self._last_book = comparable
            ts = self.config.clock()
            self.broadcaster.publish({"type": "book", **snap, "ts": ts, "server_ts": ts})

    def _on_result(self, cmd: Command, res: Result) -> None:
        """Called by the exchange task after each commit, for every command in the batch."""
        b = self.broadcaster
        for ev in res.events:
            log_event(ev["event"], **{k: v for k, v in ev.items() if k != "event"})
        ts = self.config.clock()
        if cmd.kind == "tick":
            status, _ = self.feed_status()
            b.publish(
                {
                    "type": "reference",
                    "price": dstr(cmd.args[0]),
                    "tick_ts": cmd.args[1],
                    "status": status,
                    "server_ts": ts,
                }
            )
            if isinstance(self.feed, SimFeed):
                for tf, series in self.ref_series.items():
                    c = series.last()
                    if c is not None:
                        b.publish(self._candle_msg("reference", tf, c))
        if res.trades:
            for t in res.trades:
                self.trade_candles.apply_trade(t.ms, t.price, t.qty)
                b.publish({"type": "trade", "server_ts": ts, **trade_json(t)})
                for aid, oid, side, taker_side in (
                    (t.buy_account_id, t.buy_order_id, "buy", "buy"),
                    (t.sell_account_id, t.sell_order_id, "sell", "sell"),
                ):
                    if b.has_account(aid):
                        fee = t.buy_fee if side == "buy" else t.sell_fee
                        role = "maker" if t.maker_side == side else "taker"
                        b.publish(
                            {
                                "type": "fill",
                                "server_ts": ts,
                                "trade_id": t.trade_id,
                                "order_id": oid,
                                "side": side,
                                "role": role,
                                "price": dstr(t.price),
                                "qty": dstr(t.qty),
                                "fee": dstr(fee),
                                "ms": t.ms,
                            },
                            account_id=aid,
                        )
            for tf in TIMEFRAMES:
                c = self.trade_candles.last(tf)
                if c is not None:
                    b.publish(self._candle_msg("internal", tf, c))
        for aid in res.touched_accounts:
            if aid not in SPECIAL_ACCOUNTS and b.has_account(aid):
                b.publish({"type": "state", "server_ts": ts, **state_body(self.engine, aid)}, account_id=aid)
