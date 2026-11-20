"""Account and ledger model, and the PnL / equity math (average-cost method)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

START_USD = Decimal(100)
FILLS_KEPT = 200
ORDERS_KEPT = 200  # terminal orders kept per account in memory (open orders are always kept)

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    entry_id: int
    account_id: str
    asset: str  # usd | btc
    amount: Decimal
    kind: str  # issue | redeem | trade | fee
    ref: str  # group id: every group sums to 0 per asset
    ms: int


@dataclass(frozen=True, slots=True)
class Fill:
    trade_id: int
    order_id: int
    side: str
    role: str  # maker | taker
    price: Decimal
    qty: Decimal
    fee: Decimal
    ms: int


@dataclass(eq=False)
class Account:
    """Mutable account state, owned by the engine. Use ``Engine.account()`` for a view."""

    account_id: str
    kind: str  # user | bot | house | fees | treasury
    created_ms: int = 0
    usd: Decimal = ZERO
    btc: Decimal = ZERO
    usd_reserved: Decimal = ZERO
    btc_reserved: Decimal = ZERO
    cost_basis: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    fees_paid: Decimal = ZERO
    epoch: int = 0
    open: dict = field(default_factory=dict)  # order_id -> Order (new / open / partially_filled)
    terminal: list = field(default_factory=list)  # Orders, ascending order_id, at most ORDERS_KEPT
    fills: deque = field(default_factory=lambda: deque(maxlen=FILLS_KEPT))


@dataclass(frozen=True, slots=True)
class AccountView:
    """A value snapshot of an account with the derived fields."""

    account_id: str
    kind: str
    usd: Decimal
    btc: Decimal
    usd_reserved: Decimal
    btc_reserved: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    fees_paid: Decimal
    epoch: int
    mark_price: Decimal | None

    @property
    def available_usd(self) -> Decimal:
        return self.usd - self.usd_reserved

    @property
    def free_btc(self) -> Decimal:
        return self.btc - self.btc_reserved

    @property
    def _mark(self) -> Decimal:
        return self.mark_price if self.mark_price is not None else ZERO

    @property
    def equity(self) -> Decimal:
        return self.usd + self.btc * self._mark

    @property
    def unrealized_pnl(self) -> Decimal:
        return self.btc * self._mark - self.cost_basis

    @property
    def return_pct(self) -> Decimal:
        return (self.equity - START_USD) / START_USD * 100

    @property
    def avg_cost(self) -> Decimal:
        return self.cost_basis / self.btc if self.btc > 0 else ZERO


def make_view(a: Account, mark: Decimal | None) -> AccountView:
    return AccountView(
        a.account_id,
        a.kind,
        a.usd,
        a.btc,
        a.usd_reserved,
        a.btc_reserved,
        a.cost_basis,
        a.realized_pnl,
        a.fees_paid,
        a.epoch,
        mark,
    )
