"""Seeded bots: one scheduler task for all of them, the same exchange queue as the API.

``decide`` is a pure function of the bot (and its own seeded RNG) and a market view. The
scheduler wakes when the next bot is due, so 1,000 bots cost one task, not 1,000.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from .matching import Engine, OrderRequest
from .money import MIN_NOTIONAL, USD_Q, ceil_price, floor_price, floor_qty

MEAN_INTERVAL_MS = 5_000  # mean of the exponential gap between a bot's actions
MIN_GAP_MS = 1_000  # token bucket: at most one action per second per bot
STALE_ORDER_MS = 30_000
MAX_OPEN_ORDERS = 3
MAX_ACTIONS_PER_WAKE = 250
DEVIATION_BPS = Decimal(10)
BPS = Decimal(10_000)
STRATEGIES = ("taker", "maker", "mean_reversion")


@dataclass
class Bot:
    index: int  # 1-based
    account_id: str
    strategy: str
    rng: random.Random
    next_ms: int = 0
    last_action_ms: int | None = None


@dataclass(frozen=True)
class MarketView:
    now: int
    ref: Decimal
    last: Decimal
    available_usd: Decimal
    free_btc: Decimal
    open_orders: tuple  # ((order_id, created_ms), ...)


@dataclass
class Action:
    submit: OrderRequest | None = None
    cancel: int | None = None


def _strategy(i0: int) -> str:
    slot = i0 % 10  # 40% taker, 40% maker, 20% mean reversion
    return "taker" if slot < 4 else "maker" if slot < 8 else "mean_reversion"


def _fraction(rng: random.Random) -> Decimal:
    return Decimal(rng.randint(5, 30)) / 100


def _buy_budget(rng: random.Random, available: Decimal) -> Decimal | None:
    if available < MIN_NOTIONAL:
        return None
    budget = (available * _fraction(rng)).quantize(USD_Q, rounding=ROUND_FLOOR)
    return budget if budget >= MIN_NOTIONAL else MIN_NOTIONAL


def _sell_qty(rng: random.Random, free: Decimal, px: Decimal) -> Decimal | None:
    if free * px < MIN_NOTIONAL:
        return None
    qty = floor_qty(free * _fraction(rng))
    return qty if qty * px >= MIN_NOTIONAL else free


def _stale_cancels(v: MarketView) -> list[Action]:
    return [Action(cancel=oid) for oid, created in v.open_orders if v.now - created > STALE_ORDER_MS]


def decide(bot: Bot, v: MarketView) -> list[Action]:
    """What ``bot`` does now. Uses only ``bot.rng`` for randomness, so it is deterministic."""
    rng, aid = bot.rng, bot.account_id
    can_buy = v.available_usd >= MIN_NOTIONAL
    can_sell = v.free_btc * v.ref >= MIN_NOTIONAL
    if bot.strategy == "taker":
        if not (can_buy or can_sell):
            return []
        buy = can_buy and (not can_sell or rng.random() < 0.5)
        if buy:
            budget = _buy_budget(rng, v.available_usd)
            return [Action(submit=OrderRequest(aid, "buy", "market", quote_amount=budget))] if budget else []
        qty = _sell_qty(rng, v.free_btc, v.ref)
        return [Action(submit=OrderRequest(aid, "sell", "market", qty=qty))] if qty else []

    actions = _stale_cancels(v)
    if bot.strategy == "maker":
        if len(v.open_orders) - len(actions) >= MAX_OPEN_ORDERS or not (can_buy or can_sell):
            return actions
        offset = Decimal(rng.randint(1, 20)) / BPS
        buy = can_buy and (not can_sell or rng.random() < 0.5)
        if buy:
            price = floor_price(v.ref * (1 - offset))
            budget = _buy_budget(rng, v.available_usd)
            qty = floor_qty(budget / price) if budget else Decimal(0)
            if qty * price >= MIN_NOTIONAL:
                actions.append(Action(submit=OrderRequest(aid, "buy", "limit", qty=qty, price=price)))
        else:
            price = ceil_price(v.ref * (1 + offset))
            qty = _sell_qty(rng, v.free_btc, price)
            if qty:
                actions.append(Action(submit=OrderRequest(aid, "sell", "limit", qty=qty, price=price)))
        return actions

    # mean reversion: fade a deviation of the internal last trade from the reference price
    if len(v.open_orders) - len(actions) >= MAX_OPEN_ORDERS:
        return actions
    if v.last > v.ref * (1 + DEVIATION_BPS / BPS) and can_sell:
        price = ceil_price(v.ref)
        qty = _sell_qty(rng, v.free_btc, price)
        if qty:
            actions.append(Action(submit=OrderRequest(aid, "sell", "limit", qty=qty, price=price)))
    elif v.last < v.ref * (1 - DEVIATION_BPS / BPS) and can_buy:
        price = floor_price(v.ref)
        budget = _buy_budget(rng, v.available_usd)
        qty = floor_qty(budget / price) if budget else Decimal(0)
        if qty * price >= MIN_NOTIONAL:
            actions.append(Action(submit=OrderRequest(aid, "buy", "limit", qty=qty, price=price)))
    return actions


@dataclass
class BotPool:
    n: int
    seed: int
    bots: list[Bot] = field(init=False)

    def __post_init__(self) -> None:
        self.bots = [
            # seeded simulation randomness, not security: nosec B311
            Bot(i + 1, f"bot-{i + 1:04d}", _strategy(i), random.Random(self.seed * 1_000_003 + i))  # nosec B311
            for i in range(self.n)
        ]

    async def run(
        self,
        engine: Engine,
        exchange,
        clock: Callable[[], int],
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        """The single scheduler task: a heap of next-action times, one sleep until the earliest."""
        heap: list[tuple[int, int]] = []
        now = clock()
        for b in self.bots:
            b.next_ms = now + MIN_GAP_MS + int(b.rng.expovariate(1 / MEAN_INTERVAL_MS))
            heapq.heappush(heap, (b.next_ms, b.index))
        while True:
            if not heap:
                await sleep(1)
                continue
            now = clock()
            if heap[0][0] > now:
                await sleep(min((heap[0][0] - now) / 1000, 1.0))
                continue
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(1):
                    await exchange.idle()  # act on fresh state, not on what is still queued
            now = clock()
            acted = 0
            while heap and heap[0][0] <= now and acted < MAX_ACTIONS_PER_WAKE:
                _, idx = heapq.heappop(heap)
                bot = self.bots[idx - 1]
                if bot.last_action_ms is not None and now - bot.last_action_ms < MIN_GAP_MS:
                    heapq.heappush(heap, (bot.last_action_ms + MIN_GAP_MS, idx))
                    continue
                self._act(bot, engine, exchange, now)
                acted += 1
                bot.last_action_ms = now
                bot.next_ms = now + max(MIN_GAP_MS, int(bot.rng.expovariate(1 / MEAN_INTERVAL_MS)))
                heapq.heappush(heap, (bot.next_ms, idx))
            if acted >= MAX_ACTIONS_PER_WAKE:
                await sleep(0)

    def _act(self, bot: Bot, engine: Engine, exchange, now: int) -> None:
        if engine.reference_is_fresh(now) is not None:
            return
        acct = engine.account(bot.account_id)
        if acct is None:
            return
        ref = engine.reference_price
        view = MarketView(
            now,
            ref,
            engine.last_trade_price if engine.last_trade_price is not None else ref,
            acct.available_usd,
            acct.free_btc,
            tuple((o.order_id, o.created_ms) for o in engine.orders(bot.account_id, open_only=True)),
        )
        for action in decide(bot, view):
            ok = (
                exchange.try_submit(action.submit)
                if action.submit is not None
                else exchange.try_cancel(bot.account_id, action.cancel)
            )
            if not ok:  # queue full: skip the rest of this action
                break
