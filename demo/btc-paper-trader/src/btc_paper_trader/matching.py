"""The matching engine: pure, synchronous, deterministic. No I/O, no clock, no randomness.

The caller passes ``now_ms`` to every command. Every command returns a ``Result``. All state
changes are also collected in a journal (``drain_journal``) that the exchange task hands to the
store; the engine itself never touches storage.
"""

from __future__ import annotations

from bisect import insort
from collections import deque
from dataclasses import dataclass, field, replace
from decimal import Decimal

from .accounts import (
    FILLS_KEPT,
    ORDERS_KEPT,
    START_USD,
    Account,
    AccountView,
    Fill,
    LedgerEntry,
    make_view,
)
from .book import OrderBook
from .fees import MAKER, TAKER, buy_reservation, fee
from .house import HouseConfig, ladder
from .money import MIN_NOTIONAL, PRICE_TICK, QTY_STEP, USD_Q, dstr, floor_qty

ZERO = Decimal(0)
LIVE = ("new", "open", "partially_filled")
TERMINAL = ("filled", "cancelled", "rejected")
TAPE_KEPT = 500
SPECIAL = ("treasury", "fees")


@dataclass(frozen=True)
class FeeSchedule:
    maker: Decimal = MAKER
    taker: Decimal = TAKER


@dataclass(eq=False, slots=True)
class Order:
    order_id: int
    account_id: str
    epoch: int
    side: str
    type: str  # market | limit | stop
    qty: Decimal | None
    quote_amount: Decimal | None
    price: Decimal | None
    stop_price: Decimal | None
    reduce_only: bool
    parent_id: int | None
    role: str  # entry | sl | tp | close | house | bot
    armed: bool
    status: str
    filled_qty: Decimal
    reserved_usd: Decimal
    reserved_btc: Decimal
    reason: str | None
    seq: int
    created_ms: int
    updated_ms: int


@dataclass(frozen=True, slots=True)
class Trade:
    trade_id: int
    ms: int
    price: Decimal
    qty: Decimal
    buy_order_id: int
    sell_order_id: int
    buy_account_id: str
    sell_account_id: str
    maker_side: str
    buy_fee: Decimal
    sell_fee: Decimal


@dataclass
class OrderRequest:
    account_id: str
    side: str
    type: str
    qty: Decimal | None = None
    quote_amount: Decimal | None = None
    max: bool = False
    price: Decimal | None = None
    stop_price: Decimal | None = None
    reduce_only: bool = False
    sl: Decimal | None = None
    tp: Decimal | None = None


@dataclass
class Result:
    order: Order | None = None
    trades: list = field(default_factory=list)
    events: list = field(default_factory=list)
    reason: str | None = None
    touched_accounts: list = field(default_factory=list)
    triggered_order_ids: list = field(default_factory=list)


@dataclass
class Journal:
    """Everything that changed since the last drain, as plain records for the store."""

    accounts: list = field(default_factory=list)
    orders: list = field(default_factory=list)
    deleted_orders: list = field(default_factory=list)
    fills: list = field(default_factory=list)
    trades: list = field(default_factory=list)
    ledger: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def empty(self) -> bool:
        return not (self.accounts or self.orders or self.deleted_orders or self.fills or self.trades or self.ledger)


def order_record(o: Order) -> dict:
    return {
        "order_id": o.order_id,
        "account_id": o.account_id,
        "epoch": o.epoch,
        "side": o.side,
        "type": o.type,
        "qty": dstr(o.qty),
        "quote_amount": dstr(o.quote_amount),
        "price": dstr(o.price),
        "stop_price": dstr(o.stop_price),
        "reduce_only": bool(o.reduce_only),
        "parent_id": o.parent_id,
        "role": o.role,
        "armed": bool(o.armed),
        "status": o.status,
        "filled_qty": dstr(o.filled_qty),
        "reserved_usd": dstr(o.reserved_usd),
        "reserved_btc": dstr(o.reserved_btc),
        "reason": o.reason,
        "seq": o.seq,
        "created_ms": o.created_ms,
        "updated_ms": o.updated_ms,
    }


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(v)


def order_from_record(r: dict) -> Order:
    return Order(
        order_id=int(r["order_id"]),
        account_id=r["account_id"],
        epoch=int(r["epoch"]),
        side=r["side"],
        type=r["type"],
        qty=_dec(r["qty"]),
        quote_amount=_dec(r["quote_amount"]),
        price=_dec(r["price"]),
        stop_price=_dec(r["stop_price"]),
        reduce_only=bool(r["reduce_only"]),
        parent_id=None if r["parent_id"] is None else int(r["parent_id"]),
        role=r["role"],
        armed=bool(r["armed"]),
        status=r["status"],
        filled_qty=Decimal(r["filled_qty"]),
        reserved_usd=Decimal(r["reserved_usd"]),
        reserved_btc=Decimal(r["reserved_btc"]),
        reason=r["reason"],
        seq=int(r["seq"]),
        created_ms=int(r["created_ms"]),
        updated_ms=int(r["updated_ms"]),
    )


def account_record(a: Account) -> dict:
    return {
        "account_id": a.account_id,
        "kind": a.kind,
        "usd": dstr(a.usd),
        "btc": dstr(a.btc),
        "usd_reserved": dstr(a.usd_reserved),
        "btc_reserved": dstr(a.btc_reserved),
        "cost_basis": dstr(a.cost_basis),
        "realized_pnl": dstr(a.realized_pnl),
        "fees_paid": dstr(a.fees_paid),
        "epoch": a.epoch,
        "created_ms": a.created_ms,
    }


def trade_record(t: Trade) -> dict:
    return {
        "trade_id": t.trade_id,
        "ms": t.ms,
        "price": dstr(t.price),
        "qty": dstr(t.qty),
        "buy_order_id": t.buy_order_id,
        "sell_order_id": t.sell_order_id,
        "buy_account_id": t.buy_account_id,
        "sell_account_id": t.sell_account_id,
        "maker_side": t.maker_side,
        "buy_fee": dstr(t.buy_fee),
        "sell_fee": dstr(t.sell_fee),
    }


def trade_from_record(r: dict) -> Trade:
    return Trade(
        int(r["trade_id"]),
        int(r["ms"]),
        Decimal(r["price"]),
        Decimal(r["qty"]),
        int(r["buy_order_id"]),
        int(r["sell_order_id"]),
        r["buy_account_id"],
        r["sell_account_id"],
        r["maker_side"],
        Decimal(r["buy_fee"]),
        Decimal(r["sell_fee"]),
    )


def fill_record(account_id: str, epoch: int, f: Fill) -> dict:
    return {
        "account_id": account_id,
        "epoch": epoch,
        "trade_id": f.trade_id,
        "order_id": f.order_id,
        "side": f.side,
        "role": f.role,
        "price": dstr(f.price),
        "qty": dstr(f.qty),
        "fee": dstr(f.fee),
        "ms": f.ms,
    }


def ledger_record(e: LedgerEntry) -> dict:
    return {
        "entry_id": e.entry_id,
        "account_id": e.account_id,
        "asset": e.asset,
        "amount": dstr(e.amount),
        "kind": e.kind,
        "ref": e.ref,
        "ms": e.ms,
    }


class Engine:
    """Spot, long-only order matching for many accounts in one book."""

    def __init__(
        self,
        fees: FeeSchedule | None = None,
        band: Decimal = Decimal("0.05"),
        stale_after_ms: int = 10_000,
        keep_ledger: bool = True,
    ) -> None:
        self.fees = fees or FeeSchedule()
        self.band = band
        self.stale_after_ms = stale_after_ms
        self.keep_ledger = keep_ledger

        self.accounts: dict[str, Account] = {}
        self.book = OrderBook()
        self.stops: dict[int, Order] = {}
        self.children: dict[int, list[Order]] = {}
        self._orders: dict[int, Order] = {}
        self.tape: deque[Trade] = deque(maxlen=TAPE_KEPT)
        self._ledger: list[LedgerEntry] = []

        self.reference_price: Decimal | None = None
        self.reference_ts: int | None = None
        self.last_trade_price: Decimal | None = None

        self._next_order_id = 1
        self._next_seq = 1
        self._next_trade_id = 1
        self._next_entry_id = 1
        self._next_group = 1

        self._reset_journal()
        self._begin(0)
        for aid, kind in (("treasury", "treasury"), ("fees", "fees")):
            self.accounts[aid] = Account(aid, kind)
        self._reset_journal()

    # ------------------------------------------------------------------------------------------
    # per-command bookkeeping
    # ------------------------------------------------------------------------------------------

    def _reset_journal(self) -> None:
        self._j_accounts: dict[str, Account] = {}
        self._j_orders: dict[int, Order] = {}
        self._j_deleted: set[int] = set()
        self._j_fills: list[dict] = []
        self._j_trades: list[Trade] = []
        self._j_ledger: list[LedgerEntry] = []

    def _begin(self, now_ms: int) -> None:
        self._now = now_ms
        self._trades: list[Trade] = []
        self._events: list[dict] = []
        self._triggered: list[int] = []
        self._touched: dict[str, None] = {}
        self._pending_arm: dict[int, None] = {}
        self._flat_check: dict[str, None] = {}
        self._stop_check = False

    def _finish(self, order: Order | None = None, reason: str | None = None) -> Result:
        self._settle()
        if reason is None and order is not None and order.status == "rejected":
            reason = order.reason
        return Result(
            order=replace(order) if order is not None else None,
            trades=self._trades,
            events=self._events,
            reason=reason,
            touched_accounts=list(self._touched),
            triggered_order_ids=self._triggered,
        )

    def _dirty_account(self, a: Account) -> None:
        self._j_accounts[a.account_id] = a
        self._touched[a.account_id] = None

    def _mark_order(self, o: Order) -> None:
        self._j_orders[o.order_id] = o
        self._j_deleted.discard(o.order_id)
        self._touched[o.account_id] = None

    def _event(self, name: str, o: Order, **extra) -> None:
        self._events.append(
            {
                "event": name,
                "order_id": o.order_id,
                "account_id": o.account_id,
                "side": o.side,
                "type": o.type,
                "qty": dstr(o.qty),
                "price": dstr(o.price if o.price is not None else o.stop_price),
                "reason": o.reason,
                **extra,
            }
        )

    def drain_journal(self) -> Journal:
        j = Journal(
            accounts=[account_record(a) for a in self._j_accounts.values()],
            orders=[order_record(o) for o in self._j_orders.values()],
            deleted_orders=sorted(self._j_deleted),
            fills=self._j_fills,
            trades=[trade_record(t) for t in self._j_trades],
            ledger=[ledger_record(e) for e in self._j_ledger],
            meta=self._meta(),
        )
        self._reset_journal()
        return j

    # ------------------------------------------------------------------------------------------
    # read side
    # ------------------------------------------------------------------------------------------

    @property
    def mark_price(self) -> Decimal | None:
        return self.last_trade_price if self.last_trade_price is not None else self.reference_price

    def account(self, account_id: str) -> AccountView | None:
        a = self.accounts.get(account_id)
        return None if a is None else make_view(a, self.mark_price)

    def orders(self, account_id: str, open_only: bool = False) -> list[Order]:
        a = self.accounts.get(account_id)
        if a is None:
            return []
        items = list(a.open.values()) if open_only else [*a.open.values(), *a.terminal]
        items.sort(key=lambda o: o.order_id)
        return items

    def fills(self, account_id: str) -> list[Fill]:
        a = self.accounts.get(account_id)
        return [] if a is None else list(a.fills)

    def ledger(self) -> list[LedgerEntry]:
        return list(self._ledger)

    def reference_is_fresh(self, now_ms: int) -> str | None:
        """None when the reference is usable, else the rejection reason."""
        if self.reference_price is None or self.reference_ts is None:
            return "no_reference_price"
        if now_ms - self.reference_ts > self.stale_after_ms:
            return "stale_reference"
        return None

    def totals(self) -> dict:
        out = {}
        for asset in ("usd", "btc"):
            groups = {"accounts": ZERO, "house": ZERO, "fees": ZERO, "treasury": ZERO}
            for a in self.accounts.values():
                key = a.kind if a.kind in ("house", "fees", "treasury") else "accounts"
                groups[key] += getattr(a, asset)
            groups["total"] = sum(groups.values(), ZERO)
            out[asset] = groups
        return out

    # ------------------------------------------------------------------------------------------
    # ledger
    # ------------------------------------------------------------------------------------------

    def _group(self, prefix: str) -> str:
        n = self._next_group
        self._next_group += 1
        return f"{prefix}:{n}"

    def _post(self, ref: str, legs: list[tuple[str, str, Decimal, str]]) -> None:
        """Apply balance changes as one ledger group; each group sums to zero per asset."""
        for account_id, asset, amount, kind in legs:
            if amount == 0:
                continue
            a = self.accounts[account_id]
            if asset == "usd":
                a.usd += amount
            else:
                a.btc += amount
            self._dirty_account(a)
            entry = LedgerEntry(self._next_entry_id, account_id, asset, amount, kind, ref, self._now)
            self._next_entry_id += 1
            self._j_ledger.append(entry)
            if self.keep_ledger:
                self._ledger.append(entry)

    # ------------------------------------------------------------------------------------------
    # accounts
    # ------------------------------------------------------------------------------------------

    def open_account(
        self,
        account_id: str,
        kind: str = "user",
        now_ms: int = 0,
        usd: Decimal = START_USD,
        btc: Decimal = ZERO,
    ) -> Result:
        self._begin(now_ms)
        if account_id not in self.accounts:
            a = Account(account_id, kind, created_ms=now_ms)
            self.accounts[account_id] = a
            self._dirty_account(a)
            ref = self._group("issue")
            self._post(
                ref,
                [
                    ("treasury", "usd", -usd, "issue"),
                    (account_id, "usd", usd, "issue"),
                    ("treasury", "btc", -btc, "issue"),
                    (account_id, "btc", btc, "issue"),
                ],
            )
            self._events.append({"event": "account.opened", "account_id": account_id, "kind": kind})
        return self._finish()

    def reset(self, account_id: str, now_ms: int) -> Result:
        """Return the account to a fresh $100: cancel orders, redeem, issue, bump the epoch."""
        self._begin(now_ms)
        a = self.accounts.get(account_id)
        if a is None or a.kind in SPECIAL:
            return self._finish(reason="not_found")
        for o in sorted(a.open.values(), key=lambda x: x.order_id):
            self._cancel_order(o, "reset")
        for o in a.terminal:
            self._orders.pop(o.order_id, None)
            self._gc_children(o)
        a.terminal.clear()
        a.open.clear()
        a.fills.clear()
        ref = self._group("redeem")
        self._post(
            ref,
            [
                (account_id, "usd", -a.usd, "redeem"),
                ("treasury", "usd", a.usd, "redeem"),
                (account_id, "btc", -a.btc, "redeem"),
                ("treasury", "btc", a.btc, "redeem"),
            ],
        )
        ref = self._group("issue")
        self._post(ref, [("treasury", "usd", -START_USD, "issue"), (account_id, "usd", START_USD, "issue")])
        a.usd_reserved = a.btc_reserved = a.cost_basis = a.realized_pnl = a.fees_paid = ZERO
        a.epoch += 1
        self._dirty_account(a)
        self._events.append({"event": "account.reset", "account_id": account_id, "epoch": a.epoch})
        return self._finish()

    # ------------------------------------------------------------------------------------------
    # reference price and the house
    # ------------------------------------------------------------------------------------------

    def reference_tick(self, price: Decimal, ts_ms: int) -> Result:
        self._begin(ts_ms)
        self.reference_price = price
        self.reference_ts = ts_ms
        return self._finish()

    def house_requote(self, cfg: HouseConfig, now_ms: int) -> Result:
        """Cancel the house quotes and re-place a post-only ladder around the reference."""
        self._begin(now_ms)
        house = self.accounts.get("house")
        if house is None or self.reference_is_fresh(now_ms) is not None:
            return self._finish()
        for o in sorted(house.open.values(), key=lambda x: x.order_id):
            self._cancel_order(o, "requote")
        bids, asks = ladder(cfg, self.reference_price)
        avail_usd = house.usd - house.usd_reserved
        free_btc = house.btc - house.btc_reserved
        for price in bids:
            best_ask = self.book.best_ask()
            if best_ask is not None and price >= best_ask:
                continue
            qty = cfg.level_qty
            while qty > 0 and buy_reservation(qty, price) > avail_usd:
                qty = floor_qty(min(qty - QTY_STEP, (avail_usd / (price * (1 + self.fees.taker)))))
            if qty <= 0:
                continue
            o = self._new_order(house, "buy", "limit", "house", qty=qty, price=price)
            self._reserve(o, house)
            self._rest(o)
            avail_usd = house.usd - house.usd_reserved
        for price in asks:
            best_bid = self.book.best_bid()
            if best_bid is not None and price <= best_bid:
                continue
            qty = min(cfg.level_qty, free_btc)
            if qty <= 0:
                continue
            o = self._new_order(house, "sell", "limit", "house", qty=qty, price=price)
            self._reserve(o, house)
            self._rest(o)
            free_btc = house.btc - house.btc_reserved
        return self._finish()

    # ------------------------------------------------------------------------------------------
    # order creation and status
    # ------------------------------------------------------------------------------------------

    def _new_order(
        self,
        a: Account,
        side: str,
        type_: str,
        role: str,
        *,
        qty: Decimal | None = None,
        quote_amount: Decimal | None = None,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        reduce_only: bool = False,
        parent_id: int | None = None,
    ) -> Order:
        o = Order(
            order_id=self._next_order_id,
            account_id=a.account_id,
            epoch=a.epoch,
            side=side,
            type=type_,
            qty=qty,
            quote_amount=quote_amount,
            price=price,
            stop_price=stop_price,
            reduce_only=reduce_only,
            parent_id=parent_id,
            role=role,
            armed=False,
            status="new",
            filled_qty=ZERO,
            reserved_usd=ZERO,
            reserved_btc=ZERO,
            reason=None,
            seq=self._next_seq,
            created_ms=self._now,
            updated_ms=self._now,
        )
        self._next_order_id += 1
        self._next_seq += 1
        self._orders[o.order_id] = o
        a.open[o.order_id] = o
        self._mark_order(o)
        return o

    def _set_status(self, o: Order, status: str, reason: str | None = None) -> None:
        o.status = status
        if reason is not None:
            o.reason = reason
        o.updated_ms = self._now
        self._mark_order(o)
        if status in TERMINAL:
            self._retire(o)

    def _retire(self, o: Order) -> None:
        a = self.accounts[o.account_id]
        a.open.pop(o.order_id, None)
        if o.role == "house" and o.filled_qty == 0 and o.status == "cancelled":
            # Requote churn is not history: drop it from memory and from the database.
            self._orders.pop(o.order_id, None)
            self._j_orders.pop(o.order_id, None)
            self._j_deleted.add(o.order_id)
            return
        insort(a.terminal, o, key=lambda x: x.order_id)
        if len(a.terminal) > ORDERS_KEPT:
            dropped = a.terminal.pop(0)
            self._orders.pop(dropped.order_id, None)
            self._gc_children(dropped)
        self._gc_children(o)

    def _gc_children(self, o: Order) -> None:
        pid = o.parent_id if o.parent_id is not None else o.order_id
        kids = self.children.get(pid)
        if kids is None:
            return
        parent = self._orders.get(pid)
        if (parent is None or parent.status in TERMINAL) and all(k.status in TERMINAL for k in kids):
            del self.children[pid]

    def _reserve(self, o: Order, a: Account) -> None:
        """Reserve for a limit order's remaining quantity."""
        rem = o.qty - o.filled_qty
        if o.side == "buy":
            new = buy_reservation(rem, o.price)
            a.usd_reserved += new - o.reserved_usd
            o.reserved_usd = new
        else:
            a.btc_reserved += rem - o.reserved_btc
            o.reserved_btc = rem
        self._dirty_account(a)

    def _release(self, o: Order, a: Account) -> None:
        if o.reserved_usd or o.reserved_btc:
            a.usd_reserved -= o.reserved_usd
            a.btc_reserved -= o.reserved_btc
            o.reserved_usd = o.reserved_btc = ZERO
            self._dirty_account(a)

    def _rest(self, o: Order) -> None:
        self.book.add(o)
        if o.status == "new":
            self._set_status(o, "open")
            self._event("order.accepted", o)

    def _reject(self, o: Order, reason: str) -> None:
        a = self.accounts[o.account_id]
        self._release(o, a)
        self._set_status(o, "rejected", reason)
        self._event("order.rejected", o)
        if o.filled_qty == 0:
            for k in list(self.children.get(o.order_id, [])):
                self._cancel_order(k, "parent_cancelled")

    def _cancel_order(self, o: Order, reason: str) -> None:
        if o.status not in LIVE:
            return
        a = self.accounts[o.account_id]
        if o.type == "limit":
            self.book.remove(o)
        elif o.type == "stop":
            self.stops.pop(o.order_id, None)
        self._release(o, a)
        self._set_status(o, "cancelled", reason)
        self._event("order.cancelled", o)
        if o.filled_qty == 0:
            for k in list(self.children.get(o.order_id, [])):
                self._cancel_order(k, "parent_cancelled")

    def cancel(self, account_id: str, order_id: int, now_ms: int) -> Result:
        self._begin(now_ms)
        o = self._orders.get(order_id)
        if o is None or o.account_id != account_id or o.status not in LIVE:
            return self._finish(reason="not_found")
        self._cancel_order(o, "user")
        return self._finish(o)

    # ------------------------------------------------------------------------------------------
    # submit
    # ------------------------------------------------------------------------------------------

    def submit(self, r: OrderRequest, now_ms: int) -> Result:
        self._begin(now_ms)
        a = self.accounts.get(r.account_id)
        if a is None or a.kind in SPECIAL:
            return self._finish(reason="unknown_account")
        o = self._submit(a, r, "bot" if a.kind == "bot" else "house" if a.kind == "house" else "entry")
        return self._finish(o)

    def _submit(self, a: Account, r: OrderRequest, role: str) -> Order:
        o = self._new_order(
            a,
            r.side,
            r.type,
            role,
            qty=r.qty,
            quote_amount=r.quote_amount,
            price=r.price if r.type == "limit" else None,
            stop_price=r.stop_price if r.type == "stop" else None,
            reduce_only=bool(r.reduce_only),
        )
        reason, budget = self._prepare(o, a, r, role)
        if reason is not None:
            self._reject(o, reason)
            return o
        if o.type == "stop":
            o.armed = True
            self.stops[o.order_id] = o
            self._set_status(o, "open")
            self._event("order.accepted", o)
        elif o.type == "limit":
            if r.sl is not None or r.tp is not None:
                self._make_children(a, o, r.sl, r.tp)
            self._reserve(o, a)
            self._event("order.accepted", o)
            self._run_limit(o, a)
        else:
            self._event("order.accepted", o)
            self._run_market(o, budget)
            if o.filled_qty > 0 and (r.sl is not None or r.tp is not None):
                self._make_children(a, o, r.sl, r.tp)
                self._pending_arm[o.order_id] = None
        return o

    def _prepare(self, o: Order, a: Account, r: OrderRequest, role: str) -> tuple[str | None, Decimal | None]:
        """Validate the request and fix the order's size. Returns ``(reason, market_buy_budget)``."""
        exempt = role in ("close", "sl", "tp")
        sizes = (r.qty is not None) + (r.quote_amount is not None) + bool(r.max)
        if sizes != 1 or r.side not in ("buy", "sell") or r.type not in ("market", "limit", "stop"):
            return "invalid_order", None
        if r.type == "limit" and r.price is None:
            return "invalid_order", None
        if r.type == "stop" and (r.stop_price is None or r.qty is None):
            return "invalid_order", None
        for v in (r.qty, r.quote_amount, r.price, r.stop_price, r.sl, r.tp):
            if v is not None and v <= 0:
                return "invalid_order", None
        for v, step in (
            (r.qty, QTY_STEP),
            (r.quote_amount, USD_Q),
            (r.price if r.type == "limit" else None, PRICE_TICK),
            (r.stop_price if r.type == "stop" else None, PRICE_TICK),
            (r.sl, PRICE_TICK),
            (r.tp, PRICE_TICK),
        ):
            if v is not None and v % step != 0:
                return "invalid_precision", None
        stale = self.reference_is_fresh(self._now)
        if stale is not None:
            return stale, None
        ref = self.reference_price
        buy = r.side == "buy"
        if r.reduce_only and buy:
            return "reduce_only_buy", None
        if r.sl is not None or r.tp is not None:
            if not buy or r.type == "stop":
                return "invalid_sl_tp", None
            above = r.price if r.type == "limit" else ref
            if r.sl is not None and (r.sl >= ref or (r.type == "limit" and r.sl >= above)):
                return "invalid_sl_tp", None
            if r.tp is not None and (r.tp <= ref or (r.type == "limit" and r.tp <= above)):
                return "invalid_sl_tp", None

        avail = a.usd - a.usd_reserved
        free = a.btc - a.btc_reserved
        qty = r.qty
        budget: Decimal | None = None

        if r.type == "market":
            if buy:
                if qty is not None:
                    if qty * ref < MIN_NOTIONAL and not exempt:
                        return "below_minimum", None
                else:
                    budget = r.quote_amount if r.quote_amount is not None else avail
                    if budget < MIN_NOTIONAL:
                        return ("insufficient_funds" if r.max and budget == 0 else "below_minimum"), None
                    if budget > avail:
                        return "insufficient_funds", None
                return None, budget
            # market sell
            if qty is None:
                qty = free if r.max else floor_qty(r.quote_amount / ref)
            elif qty * ref < MIN_NOTIONAL and not exempt:
                return "below_minimum", None
            if r.quote_amount is not None and (r.quote_amount < MIN_NOTIONAL or qty <= 0):
                return "below_minimum", None
            return self._sell_checks(o, r, qty, free, ref, skip_min=exempt or r.reduce_only), None

        if r.type == "limit":
            price = r.price
            if buy:
                if qty is None:
                    cap = avail if r.max else min(r.quote_amount, avail)
                    qty = floor_qty(cap / (price * (1 + self.fees.taker)))
                    while qty > 0 and buy_reservation(qty, price) > avail:
                        qty -= QTY_STEP
                    if r.quote_amount is not None and r.quote_amount > avail:
                        return "insufficient_funds", None
                o.qty = qty
                if qty <= 0 or qty * price < MIN_NOTIONAL:
                    return "below_minimum", None
                if buy_reservation(qty, price) > avail:
                    return "insufficient_funds", None
                return None, None
            if qty is None:
                qty = free if r.max else floor_qty(r.quote_amount / price)
            elif qty * price < MIN_NOTIONAL and not r.reduce_only:
                return "below_minimum", None
            return self._sell_checks(o, r, qty, free, price, skip_min=r.reduce_only), None

        # stop
        if qty * r.stop_price < MIN_NOTIONAL:
            return "below_minimum", None
        last = self.last_trade_price if self.last_trade_price is not None else ref
        if (not buy and last <= r.stop_price) or (buy and last >= r.stop_price):
            return "invalid_stop", None
        if not buy:
            return self._sell_checks(o, r, qty, free, r.stop_price, skip_min=True), None
        return None, None

    def _sell_checks(self, o: Order, r: OrderRequest, qty: Decimal, free: Decimal, px: Decimal, skip_min: bool):
        """Reduce-only clipping, the free-BTC limit and the minimum for a sell. Returns a reason."""
        if r.reduce_only:
            if free <= 0:
                return "nothing_to_reduce"
            qty = min(qty, free)
        if qty <= 0:
            return "insufficient_btc" if r.max else "below_minimum"
        if not skip_min and qty * px < MIN_NOTIONAL:
            return "below_minimum"
        if qty > free:
            return "insufficient_btc"
        o.qty = qty
        return None

    # ------------------------------------------------------------------------------------------
    # matching
    # ------------------------------------------------------------------------------------------

    def _afford_qty(self, cap: Decimal, price: Decimal) -> Decimal:
        rate = self.fees.taker
        q = floor_qty(cap / (price * (1 + rate)))
        while q > 0 and q * price + fee(q, price, rate) > cap:
            q -= QTY_STEP
        return q if q > 0 else ZERO

    def _walk(
        self,
        taker: Order,
        *,
        target: Decimal | None,
        budget: Decimal | None = None,
        limit: Decimal | None = None,
        partial_afford: bool = False,
    ) -> str:
        """Fill ``taker`` against the book, best price first, at the makers' prices, inside the band.

        Returns why it stopped: ``done | limit | no_liquidity | band_exhausted | insufficient_funds``.
        """
        buy = taker.side == "buy"
        opp = "sell" if buy else "buy"
        a = self.accounts[taker.account_id]
        lo = self.reference_price * (1 - self.band)
        hi = self.reference_price * (1 + self.band)
        pays_cash = buy and taker.type != "limit"
        filled = ZERO
        while True:
            if target is not None and filled >= target:
                return "done"
            maker = self.book.first(opp)
            if maker is None:
                return "no_liquidity"
            p = maker.price
            if limit is not None and (p > limit if buy else p < limit):
                return "limit"
            if p > hi or p < lo:
                return "band_exhausted"
            m_rem = maker.qty - maker.filled_qty
            qty = m_rem if target is None else min(m_rem, target - filled)
            if pays_cash:
                avail = a.usd - a.usd_reserved
                cap = avail if budget is None else min(budget, avail)
                if target is None or partial_afford:
                    q_aff = self._afford_qty(cap, p)
                    if q_aff < qty:
                        if q_aff <= 0:
                            return "done" if target is None else "insufficient_funds"
                        qty = q_aff
                elif qty * p + fee(qty, p, self.fees.taker) > cap:
                    return "insufficient_funds"
            t = self._execute_trade(taker, maker, qty, p)
            filled += qty
            if budget is not None:
                budget -= t.qty * t.price + t.buy_fee

    def _execute_trade(self, taker: Order, maker: Order, qty: Decimal, price: Decimal) -> Trade:
        taker_is_buy = taker.side == "buy"
        buy_o, sell_o = (taker, maker) if taker_is_buy else (maker, taker)
        buyer, seller = self.accounts[buy_o.account_id], self.accounts[sell_o.account_id]
        notional = qty * price
        buy_fee = fee(qty, price, self.fees.taker if taker_is_buy else self.fees.maker)
        sell_fee = fee(qty, price, self.fees.maker if taker_is_buy else self.fees.taker)
        tid = self._next_trade_id
        self._next_trade_id += 1

        # average-cost bookkeeping (fees are tracked separately)
        buyer.cost_basis += notional
        removed = seller.cost_basis if seller.btc == qty else seller.cost_basis * qty / seller.btc
        seller.cost_basis -= removed
        seller.realized_pnl += notional - removed
        buyer.fees_paid += buy_fee
        seller.fees_paid += sell_fee

        ref = f"trade:{tid}"
        self._post(
            ref,
            [
                (buyer.account_id, "usd", -notional, "trade"),
                (seller.account_id, "usd", notional, "trade"),
                (buyer.account_id, "btc", qty, "trade"),
                (seller.account_id, "btc", -qty, "trade"),
                (buyer.account_id, "usd", -buy_fee, "fee"),
                (seller.account_id, "usd", -sell_fee, "fee"),
                ("fees", "usd", buy_fee + sell_fee, "fee"),
            ],
        )

        trade = Trade(
            tid,
            self._now,
            price,
            qty,
            buy_o.order_id,
            sell_o.order_id,
            buy_o.account_id,
            sell_o.account_id,
            maker.side,
            buy_fee,
            sell_fee,
        )
        self._trades.append(trade)
        self.tape.append(trade)
        self._j_trades.append(trade)
        self.last_trade_price = price
        self._stop_check = True

        for o, acct, f_fee, role in (
            (buy_o, buyer, buy_fee, "taker" if taker_is_buy else "maker"),
            (sell_o, seller, sell_fee, "maker" if taker_is_buy else "taker"),
        ):
            o.filled_qty += qty
            if o.type == "limit":
                self._reserve(o, acct)
            done = o.qty is not None and o.filled_qty >= o.qty
            o.status = "filled" if done else "partially_filled"
            o.updated_ms = self._now
            self._mark_order(o)
            fl = Fill(tid, o.order_id, o.side, role, price, qty, f_fee, self._now)
            acct.fills.append(fl)
            self._j_fills.append(fill_record(acct.account_id, acct.epoch, fl))
            self._dirty_account(acct)
            if done:
                if o is maker:
                    self.book.remove(o)
                self._event("order.filled", o)
                self._retire(o)
            else:
                self._event("order.partially_filled", o)
            if o.order_id in self.children:
                self._pending_arm[o.order_id] = None
        if seller.btc == 0:
            self._flat_check[seller.account_id] = None
        return trade

    def _run_limit(self, o: Order, a: Account) -> None:
        reason = self._walk(o, target=o.qty, limit=o.price)
        if o.filled_qty >= o.qty:
            return
        if reason == "band_exhausted":
            if o.filled_qty == 0:
                self._reject(o, "band_exhausted")
            else:
                self._cancel_order(o, "band_exhausted")
        else:
            self._rest(o)

    def _run_market(self, o: Order, budget: Decimal | None, accepted: bool = False) -> None:
        if o.side == "buy" and budget is not None:
            reason = self._walk(o, target=None, budget=budget)
        else:
            reason = self._walk(o, target=o.qty, partial_afford=accepted)
        self._finish_market(o, reason, accepted)

    def _finish_market(self, o: Order, reason: str, accepted: bool) -> None:
        if o.filled_qty == 0:
            if reason == "done":
                reason = "below_minimum"
            if accepted:
                self._cancel_order(o, reason)
            else:
                self._reject(o, reason)
            return
        if o.qty is None:
            o.qty = o.filled_qty
        if reason == "done":
            if o.status != "filled":
                self._set_status(o, "filled")
                self._event("order.filled", o)
        else:
            self._cancel_order(o, reason)

    # ------------------------------------------------------------------------------------------
    # SL / TP children, stops, reduce-only, close
    # ------------------------------------------------------------------------------------------

    def _make_children(self, a: Account, parent: Order, sl: Decimal | None, tp: Decimal | None) -> None:
        kids: list[Order] = []
        if tp is not None:
            kids.append(
                self._new_order(a, "sell", "limit", "tp", qty=ZERO, price=tp, reduce_only=True, parent_id=parent.order_id)
            )
        if sl is not None:
            kids.append(
                self._new_order(
                    a, "sell", "stop", "sl", qty=ZERO, stop_price=sl, reduce_only=True, parent_id=parent.order_id
                )
            )
        self.children[parent.order_id] = kids

    def _arm_children(self, parent_id: int) -> None:
        parent = self._orders.get(parent_id)
        if parent is None:
            return
        a = self.accounts[parent.account_id]
        for kid in list(self.children.get(parent_id, [])):
            if kid.status not in LIVE:
                continue
            # the TP reserves BTC; the SL reserves nothing and is clipped when it triggers
            avail = a.btc if kid.role == "sl" else a.btc - a.btc_reserved + kid.reserved_btc
            want = kid.filled_qty + min(parent.filled_qty - kid.filled_qty, avail)
            if (kid.armed and want <= kid.qty) or want <= 0:
                continue
            if kid.role == "sl":
                kid.qty = want
                if not kid.armed:
                    kid.armed = True
                    kid.seq = self._next_seq  # time priority starts when it enters the trigger book
                    self._next_seq += 1
                    self.stops[kid.order_id] = kid
                    self._set_status(kid, "open")
                    self._event("order.accepted", kid)
                    self._stop_check = True
                else:
                    kid.updated_ms = self._now
                    self._mark_order(kid)
                continue
            # take profit: a resting reduce-only limit sell; growing it sends it to the back of its level
            if kid.armed:
                self.book.remove(kid)
                self._release(kid, a)
            kid.seq = self._next_seq  # first arming or growth: it joins the back of its level
            self._next_seq += 1
            kid.qty = want
            kid.armed = True
            kid.updated_ms = self._now
            if kid.status == "new":
                self._set_status(kid, "open")
                self._event("order.accepted", kid)
            self._reserve(kid, a)
            self._mark_order(kid)
            self._run_limit(kid, a)

    def _cancel_if_flat(self, account_id: str) -> None:
        a = self.accounts[account_id]
        if a.btc != 0:
            return
        for o in sorted(a.open.values(), key=lambda x: x.order_id):
            if o.reduce_only and o.status in ("open", "partially_filled"):
                self._cancel_order(o, "flat")

    def _next_triggered_stop(self) -> Order | None:
        last = self.last_trade_price
        if last is None or not self.stops:
            return None
        sells = [o for o in self.stops.values() if o.side == "sell" and last <= o.stop_price]
        if sells:
            return min(sells, key=lambda o: (-o.stop_price, o.seq))
        buys = [o for o in self.stops.values() if o.side == "buy" and last >= o.stop_price]
        if buys:
            return min(buys, key=lambda o: (o.stop_price, o.seq))
        return None

    def _trigger(self, o: Order) -> None:
        self.stops.pop(o.order_id, None)
        self._triggered.append(o.order_id)
        self._event("order.triggered", o)
        a = self.accounts[o.account_id]
        if o.role == "sl":
            for sib in list(self.children.get(o.parent_id, [])):
                if sib is not o:
                    self._cancel_order(sib, "sl_triggered")
            parent = self._orders.get(o.parent_id)
            if parent is not None and parent.status in LIVE:
                self._cancel_order(parent, "sl_triggered")
        if o.side == "sell":
            free = a.btc - a.btc_reserved
            qty = min(o.qty, free)
            if qty <= 0:
                self._cancel_order(o, "insufficient_funds")
                return
            o.qty = qty
        self._run_market(o, None, accepted=True)

    def _settle(self) -> None:
        """Run what a trade sets in motion: arm SL/TP, cancel on flat, trigger stops (cascade)."""
        while True:
            if self._pending_arm:
                pid = next(iter(self._pending_arm))
                del self._pending_arm[pid]
                self._arm_children(pid)
            elif self._flat_check:
                aid = next(iter(self._flat_check))
                del self._flat_check[aid]
                self._cancel_if_flat(aid)
            elif self._stop_check:
                o = self._next_triggered_stop()
                if o is None:
                    self._stop_check = False
                else:
                    self._trigger(o)
            else:
                return

    def close_position(self, account_id: str, now_ms: int) -> Result:
        """Cancel the account's sell-side orders, then market-sell all BTC as reduce-only."""
        self._begin(now_ms)
        a = self.accounts.get(account_id)
        if a is None or a.kind in SPECIAL:
            return self._finish(reason="not_found")
        if a.btc <= 0:
            return self._finish(reason="nothing_to_reduce")
        req = OrderRequest(account_id, "sell", "market", max=True, reduce_only=True)
        stale = self.reference_is_fresh(now_ms)
        if stale is not None:
            o = self._new_order(a, "sell", "market", "close", reduce_only=True)
            self._reject(o, stale)
            return self._finish(o)
        for o in sorted(a.open.values(), key=lambda x: x.order_id):
            if o.side == "sell":
                self._cancel_order(o, "close_position")
        o = self._submit(a, req, "close")
        return self._finish(o)

    # ------------------------------------------------------------------------------------------
    # records (persistence round trip)
    # ------------------------------------------------------------------------------------------

    def _meta(self) -> dict:
        return {
            "next_order_id": self._next_order_id,
            "next_seq": self._next_seq,
            "next_trade_id": self._next_trade_id,
            "next_entry_id": self._next_entry_id,
            "next_group": self._next_group,
            "last_trade_price": dstr(self.last_trade_price),
            "reference_price": dstr(self.reference_price),
            "reference_ts": self.reference_ts,
        }

    def to_records(self) -> dict:
        orders = sorted(self._orders.values(), key=lambda o: o.order_id)
        fills = []
        for aid in sorted(self.accounts):
            a = self.accounts[aid]
            fills.extend(
                fill_record(aid, a.epoch, f) for f in sorted(a.fills, key=lambda f: (f.trade_id, f.order_id))
            )
        return {
            "accounts": [account_record(self.accounts[k]) for k in sorted(self.accounts)],
            "orders": [order_record(o) for o in orders],
            "fills": fills,
            "trades": [trade_record(t) for t in self.tape],
            "meta": self._meta(),
        }

    @classmethod
    def from_records(cls, rec: dict, **kwargs) -> Engine:
        eng = cls(**kwargs)
        for r in rec["accounts"]:
            a = eng.accounts.get(r["account_id"]) or Account(r["account_id"], r["kind"])
            a.kind = r["kind"]
            a.usd, a.btc = Decimal(r["usd"]), Decimal(r["btc"])
            a.usd_reserved, a.btc_reserved = Decimal(r["usd_reserved"]), Decimal(r["btc_reserved"])
            a.cost_basis, a.realized_pnl = Decimal(r["cost_basis"]), Decimal(r["realized_pnl"])
            a.fees_paid = Decimal(r["fees_paid"])
            a.epoch = int(r["epoch"])
            a.created_ms = int(r["created_ms"])
            eng.accounts[a.account_id] = a
        resting = []
        for r in sorted(rec["orders"], key=lambda x: int(x["order_id"])):
            o = order_from_record(r)
            a = eng.accounts[o.account_id]
            eng._orders[o.order_id] = o
            if o.status in LIVE:
                a.open[o.order_id] = o
            else:
                a.terminal.append(o)
            if o.type == "limit" and o.status in ("open", "partially_filled"):
                resting.append(o)
            elif o.type == "stop" and o.status == "open":
                eng.stops[o.order_id] = o
            if o.parent_id is not None:
                eng.children.setdefault(o.parent_id, []).append(o)
        for o in sorted(resting, key=lambda x: x.seq):
            eng.book.add(o)
        for r in rec["fills"]:
            eng.accounts[r["account_id"]].fills.append(
                Fill(
                    int(r["trade_id"]),
                    int(r["order_id"]),
                    r["side"],
                    r["role"],
                    Decimal(r["price"]),
                    Decimal(r["qty"]),
                    Decimal(r["fee"]),
                    int(r["ms"]),
                )
            )
        for r in rec["trades"]:
            eng.tape.append(trade_from_record(r))
        m = rec["meta"]
        eng._next_order_id = int(m["next_order_id"])
        eng._next_seq = int(m["next_seq"])
        eng._next_trade_id = int(m["next_trade_id"])
        eng._next_entry_id = int(m["next_entry_id"])
        eng._next_group = int(m["next_group"])
        eng.last_trade_price = _dec(m["last_trade_price"])
        eng.reference_price = _dec(m["reference_price"])
        eng.reference_ts = None if m["reference_ts"] is None else int(m["reference_ts"])
        eng._reset_journal()
        return eng


__all__ = [
    "Engine",
    "FeeSchedule",
    "Journal",
    "Order",
    "OrderRequest",
    "Result",
    "Trade",
    "FILLS_KEPT",
]
