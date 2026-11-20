"""Small shared helpers for the engine-level tests (not a test module)."""

from __future__ import annotations

import asyncio
import heapq
import itertools
from decimal import Decimal

D = Decimal
T0 = 1_699_920_000_000
REF = D("100000")

USER_A = "a" * 32
USER_B = "b" * 32
USER_C = "c" * 32
MAKER = "bot-0001"
MAKER2 = "bot-0002"
TERMINAL = {"filled", "cancelled", "rejected"}


def req(account_id, side, type, **kw):
    from btc_paper_trader.matching import OrderRequest

    return OrderRequest(account_id=account_id, side=side, type=type, **kw)


def engine(ref=REF, now=T0, house_usd=D("200000"), house_btc=D("2")):
    """A fresh engine with a house account (no quotes yet) and one reference tick."""
    from btc_paper_trader.matching import Engine

    eng = Engine()
    eng.open_account("house", kind="house", now_ms=now, usd=house_usd, btc=house_btc)
    if ref is not None:
        eng.reference_tick(ref, ts_ms=now)
    return eng


def user(eng, account_id=USER_A, now=T0):
    eng.open_account(account_id, kind="user", now_ms=now)
    return account_id


def maker(eng, account_id=MAKER, btc=D("0.01"), usd=D("100"), now=T0):
    """A bot-kind account that starts with some BTC, used as a controllable counterparty."""
    eng.open_account(account_id, kind="bot", now_ms=now, usd=usd, btc=btc)
    return account_id


def limit(eng, account_id, side, qty, price, now=T0, **kw):
    return eng.submit(req(account_id, side, "limit", qty=D(qty), price=D(price), **kw), now_ms=now)


def market(eng, account_id, side, qty=None, now=T0, **kw):
    if qty is not None:
        kw["qty"] = D(qty)
    return eng.submit(req(account_id, side, "market", **kw), now_ms=now)


def stop(eng, account_id, side, qty, stop_price, now=T0, **kw):
    return eng.submit(
        req(account_id, side, "stop", qty=D(qty), stop_price=D(stop_price), **kw), now_ms=now
    )


def remaining(order):
    return order.qty - order.filled_qty


def order_by_id(eng, account_id, order_id):
    for o in eng.orders(account_id, open_only=False):
        if o.order_id == order_id:
            return o
    return None


ACCOUNT_FIELDS = (
    "usd",
    "btc",
    "usd_reserved",
    "btc_reserved",
    "available_usd",
    "free_btc",
    "realized_pnl",
    "fees_paid",
    "cost_basis",
    "epoch",
)


def snap(view):
    """A value snapshot of an account view (views may be live objects)."""
    return None if view is None else tuple(getattr(view, f) for f in ACCOUNT_FIELDS)


def order_snap(o):
    return (o.order_id, o.status, o.qty, o.filled_qty, o.reason, o.price, o.stop_price)


def is_multiple(value, step) -> bool:
    return (D(value) % D(step)) == 0


# --- command generation shared by the property tests -------------------------------------------

PROP_USERS = ["1" * 32, "2" * 32, "3" * 32, "4" * 32]
QTYS = ["0.00001", "0.00005", "0.0001", "0.0002", "0.0003", "0.0005", "0.001", "0.002", "0.01", "0.000015"]
PRICE_FACTORS = ["0.9", "0.97", "0.995", "0.999", "0.9995", "1", "1.0005", "1.001", "1.005", "1.03", "1.1"]
GAP_FACTORS = ["0.5", "0.9", "0.98", "0.999", "1", "1.001", "1.02", "1.1", "1.5"]


def command_strategy():
    """Hypothesis strategy for one engine command (as a plain tuple)."""
    from hypothesis import strategies as st

    idx = st.integers(min_value=0, max_value=len(PROP_USERS) - 1)
    submit = st.tuples(
        st.just("submit"),
        idx,
        st.sampled_from(["buy", "sell"]),
        st.sampled_from(["market", "limit", "limit", "stop"]),
        st.sampled_from(["qty", "qty", "qty", "quote", "max", "both", "none"]),
        st.sampled_from(QTYS),
        st.sampled_from(PRICE_FACTORS),
        st.sampled_from(PRICE_FACTORS),
        st.sampled_from([False] * 9 + [True]),  # off-tick limit price
        st.sampled_from([False, False, False, True]),
        st.sampled_from([None, None, "0.98", "0.995", "1.01"]),
        st.sampled_from([None, None, "1.02", "1.005", "0.99"]),
    )
    return st.one_of(
        submit,
        submit,
        submit,
        st.tuples(st.just("tick"), st.sampled_from(GAP_FACTORS)),
        st.tuples(st.just("requote")),
        st.tuples(st.just("advance"), st.sampled_from([1, 500, 2_000, 9_000, 10_500, 15_000])),
        st.tuples(st.just("cancel"), idx, st.sampled_from(["own", "own", "foreign", "unknown"]), st.integers(0, 50)),
        st.tuples(st.just("reset"), idx),
        st.tuples(st.just("close"), idx),
    )


def quantize_price(value):
    return D(value).quantize(D("0.01"))


def build_request(ref, cmd):
    """Turn a ``submit`` command tuple into an OrderRequest relative to the current reference."""
    _, i, side, type_, size, qty, pf, sf, off_tick, ro, sl, tp = cmd
    ref = ref or REF
    kw = {}
    if size in ("qty", "both"):
        kw["qty"] = D(qty)
    if size in ("quote", "both"):
        kw["quote_amount"] = (D(qty) * ref).quantize(D("0.00000001"))
    if size == "max":
        kw["max"] = True
    if type_ == "limit":
        p = quantize_price(ref * D(pf))
        kw["price"] = p + D("0.001") if off_tick else p
    if type_ == "stop":
        kw["stop_price"] = quantize_price(ref * D(sf))
    if ro:
        kw["reduce_only"] = True
    if sl is not None and side == "buy":
        kw["sl"] = quantize_price(ref * D(sl))
    if tp is not None and side == "buy":
        kw["tp"] = quantize_price(ref * D(tp))
    return req(PROP_USERS[i], side, type_, **kw)


def pick_cancel_target(eng, cmd):
    _, i, kind, n = cmd
    me = PROP_USERS[i]
    if kind == "unknown":
        return me, 10_000_000 + n
    owner = me if kind == "own" else PROP_USERS[(i + 1) % len(PROP_USERS)]
    open_orders = eng.orders(owner, open_only=True)
    if not open_orders:
        return me, 10_000_000 + n
    return me, open_orders[n % len(open_orders)].order_id


def new_prop_engine(now=T0):
    from btc_paper_trader.house import HouseConfig

    eng = engine(now=now)
    for u in PROP_USERS:
        eng.open_account(u, kind="user", now_ms=now)
    eng.house_requote(HouseConfig(), now_ms=now)
    return eng


def apply_engine_command(eng, clock_state, cmd):
    """Apply a command tuple to an Engine; ``clock_state`` is a dict holding ``now``."""
    from btc_paper_trader.house import HouseConfig

    kind = cmd[0]
    now = clock_state["now"]
    if kind == "submit":
        return eng.submit(build_request(eng.reference_price, cmd), now_ms=now)
    if kind == "tick":
        ref = eng.reference_price or REF
        price = max(quantize_price(ref * D(cmd[1])), D("1000"))
        return eng.reference_tick(price, ts_ms=now)
    if kind == "requote":
        return eng.house_requote(HouseConfig(), now_ms=now)
    if kind == "advance":
        clock_state["now"] = now + cmd[1]
        return None
    if kind == "cancel":
        acct, oid = pick_cancel_target(eng, cmd)
        return eng.cancel(acct, oid, now_ms=now)
    if kind == "reset":
        return eng.reset(PROP_USERS[cmd[1]], now_ms=now)
    if kind == "close":
        return eng.close_position(PROP_USERS[cmd[1]], now_ms=now)
    raise AssertionError(kind)


class FakeClock:
    """Virtual time. ``now()`` is epoch ms; ``sleep()`` waits until ``advance()`` passes it."""

    def __init__(self, start_ms: int = T0) -> None:
        self.ms = start_ms
        self._sleepers: list[tuple[float, int, asyncio.Future]] = []
        self._seq = itertools.count()
        self.sleeps: list[float] = []

    def now(self) -> int:
        return int(self.ms)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        fut = asyncio.get_running_loop().create_future()
        heapq.heappush(self._sleepers, (self.ms + seconds * 1000, next(self._seq), fut))
        await fut

    async def settle(self, rounds: int = 50) -> None:
        for _ in range(rounds):
            await asyncio.sleep(0)

    async def advance(self, ms: int) -> None:
        """Move time forward, waking sleepers in deadline order and letting them run."""
        target = self.ms + ms
        while True:
            self._sleepers = [s for s in self._sleepers if not s[2].done()]
            heapq.heapify(self._sleepers)
            if not self._sleepers or self._sleepers[0][0] > target:
                break
            deadline, _, fut = heapq.heappop(self._sleepers)
            self.ms = max(self.ms, deadline)
            if not fut.done():
                fut.set_result(None)
            await self.settle()
        self.ms = target
        await self.settle()
