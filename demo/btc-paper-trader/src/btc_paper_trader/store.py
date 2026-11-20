"""Persistence behind a small ``Store`` protocol. ``SqliteStore`` uses aiosqlite in WAL mode.

Every table is keyed by ``account_id`` (the public ``trades`` and ``meta`` tables are global).
Decimals are stored as TEXT. One transaction per matcher batch covers every account it touched.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import aiosqlite

from .accounts import FILLS_KEPT, ORDERS_KEPT

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts(
    account_id TEXT PRIMARY KEY, kind TEXT NOT NULL, usd TEXT NOT NULL, btc TEXT NOT NULL,
    usd_reserved TEXT NOT NULL, btc_reserved TEXT NOT NULL, cost_basis TEXT NOT NULL,
    realized_pnl TEXT NOT NULL, fees_paid TEXT NOT NULL, epoch INTEGER NOT NULL, created_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS orders(
    order_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, epoch INTEGER NOT NULL, side TEXT NOT NULL,
    type TEXT NOT NULL, qty TEXT, quote_amount TEXT, price TEXT, stop_price TEXT,
    reduce_only INTEGER NOT NULL, parent_id INTEGER, role TEXT NOT NULL, armed INTEGER NOT NULL,
    status TEXT NOT NULL, filled_qty TEXT NOT NULL, reserved_usd TEXT NOT NULL, reserved_btc TEXT NOT NULL,
    reason TEXT, seq INTEGER NOT NULL, created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS orders_by_account ON orders(account_id, epoch, status);
CREATE TABLE IF NOT EXISTS fills(
    account_id TEXT NOT NULL, epoch INTEGER NOT NULL, trade_id INTEGER NOT NULL, order_id INTEGER NOT NULL,
    side TEXT NOT NULL, role TEXT NOT NULL, price TEXT NOT NULL, qty TEXT NOT NULL, fee TEXT NOT NULL,
    ms INTEGER NOT NULL, PRIMARY KEY(account_id, trade_id, order_id)
);
CREATE TABLE IF NOT EXISTS ledger(
    entry_id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, asset TEXT NOT NULL, amount TEXT NOT NULL,
    kind TEXT NOT NULL, ref TEXT NOT NULL, ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_by_account ON ledger(account_id);
CREATE TABLE IF NOT EXISTS trades(
    trade_id INTEGER PRIMARY KEY, ms INTEGER NOT NULL, price TEXT NOT NULL, qty TEXT NOT NULL,
    buy_order_id INTEGER NOT NULL, sell_order_id INTEGER NOT NULL, buy_account_id TEXT NOT NULL,
    sell_account_id TEXT NOT NULL, maker_side TEXT NOT NULL, buy_fee TEXT NOT NULL, sell_fee TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

ACCOUNT_COLS = (
    "account_id kind usd btc usd_reserved btc_reserved cost_basis realized_pnl fees_paid epoch created_ms".split()
)
ORDER_COLS = (
    "order_id account_id epoch side type qty quote_amount price stop_price reduce_only parent_id role armed "
    "status filled_qty reserved_usd reserved_btc reason seq created_ms updated_ms".split()
)
FILL_COLS = "account_id epoch trade_id order_id side role price qty fee ms".split()
LEDGER_COLS = "entry_id account_id asset amount kind ref ms".split()
TRADE_COLS = (
    "trade_id ms price qty buy_order_id sell_order_id buy_account_id sell_account_id maker_side buy_fee sell_fee"
).split()

LIVE_SQL = "('new','open','partially_filled')"


class Store(Protocol):
    async def open(self) -> None: ...

    async def load(self) -> dict | None: ...

    async def commit(self, batch) -> None: ...

    async def close(self) -> None: ...


def _insert(verb: str, table: str, cols: list[str]) -> str:
    return f"{verb} INTO {table}({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"


def _rows(records: list[dict], cols: list[str]) -> list[tuple]:
    return [tuple(r[c] for c in cols) for r in records]


class SqliteStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.executescript(SCHEMA)
        await db.commit()
        self._db = db

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("store is not open")
        return self._db

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def load(self) -> dict | None:
        db = self.db
        accounts = [dict(r) for r in await db.execute_fetchall("SELECT * FROM accounts ORDER BY account_id")]
        if not accounts:
            return None
        cols = ",".join(f"o.{c}" for c in ORDER_COLS)
        join = "JOIN accounts a ON a.account_id = o.account_id AND a.epoch = o.epoch"
        # Only module constants (column names, status list) are interpolated; values use "?".
        live = await db.execute_fetchall(
            f"SELECT {cols} FROM orders o {join} WHERE o.status IN {LIVE_SQL}"  # nosec B608
        )
        done = await db.execute_fetchall(
            f"SELECT {','.join(ORDER_COLS)} FROM (SELECT {cols}, ROW_NUMBER() OVER "  # nosec B608
            f"(PARTITION BY o.account_id ORDER BY o.order_id DESC) AS rn FROM orders o {join} "
            f"WHERE o.status NOT IN {LIVE_SQL}) WHERE rn <= ?",
            (ORDERS_KEPT,),
        )
        fcols = ",".join(f"f.{c}" for c in FILL_COLS)
        fills = await db.execute_fetchall(
            f"SELECT {','.join(FILL_COLS)} FROM (SELECT {fcols}, ROW_NUMBER() OVER (PARTITION BY f.account_id "  # nosec B608
            "ORDER BY f.trade_id DESC, f.order_id DESC) AS rn FROM fills f JOIN accounts a "
            "ON a.account_id = f.account_id AND a.epoch = f.epoch) WHERE rn <= ? "
            "ORDER BY account_id, trade_id, order_id",
            (FILLS_KEPT,),
        )
        trades = await db.execute_fetchall("SELECT * FROM trades ORDER BY trade_id DESC LIMIT 500")
        meta = {r["key"]: json.loads(r["value"]) for r in await db.execute_fetchall("SELECT key, value FROM meta")}
        if "next_order_id" not in meta:
            return None
        return {
            "accounts": accounts,
            "orders": [dict(r) for r in (*live, *done)],
            "fills": [dict(r) for r in fills],
            "trades": [dict(r) for r in reversed(trades)],
            "meta": meta,
        }

    async def iter_trades(self, chunk: int = 50_000) -> AsyncIterator[list[tuple[int, Decimal, Decimal]]]:
        """``(ms, price, qty)`` for every trade ever made, oldest first, in chunks."""
        async with self.db.execute("SELECT ms, price, qty FROM trades ORDER BY trade_id") as cur:
            while True:
                rows = await cur.fetchmany(chunk)
                if not rows:
                    return
                yield [(r["ms"], Decimal(r["price"]), Decimal(r["qty"])) for r in rows]

    async def commit(self, batch) -> None:
        """Write one matcher batch (an engine ``Journal``) in a single transaction."""
        db = self.db
        try:
            if batch.accounts:
                await db.executemany(_insert("INSERT OR REPLACE", "accounts", ACCOUNT_COLS), _rows(batch.accounts, ACCOUNT_COLS))
            if batch.orders:
                await db.executemany(_insert("INSERT OR REPLACE", "orders", ORDER_COLS), _rows(batch.orders, ORDER_COLS))
            if batch.deleted_orders:
                await db.executemany("DELETE FROM orders WHERE order_id = ?", [(i,) for i in batch.deleted_orders])
            if batch.fills:
                await db.executemany(_insert("INSERT OR REPLACE", "fills", FILL_COLS), _rows(batch.fills, FILL_COLS))
            if batch.trades:
                await db.executemany(_insert("INSERT OR REPLACE", "trades", TRADE_COLS), _rows(batch.trades, TRADE_COLS))
            if batch.ledger:
                await db.executemany(_insert("INSERT OR REPLACE", "ledger", LEDGER_COLS), _rows(batch.ledger, LEDGER_COLS))
            if batch.meta:
                await db.executemany(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    [(k, json.dumps(v)) for k, v in batch.meta.items()],
                )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
