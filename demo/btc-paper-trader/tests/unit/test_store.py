"""SqliteStore: WAL, Decimals as TEXT, keyed by account_id, never blocks the loop (A1, store part).

The schema is part of the design (table and column names), so the tests read the database file
directly for the storage-format checks only.
"""

import asyncio
import sqlite3
import uuid
from decimal import Decimal as D


def _query(path, sql, *args):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


async def test_store_opens_the_database_in_wal_mode(make_config):
    from btc_paper_trader.service import Service

    cfg = make_config()
    async with Service(cfg).running():
        pass
    assert _query(cfg.db, "PRAGMA journal_mode")[0][0].lower() == "wal"


async def test_decimals_are_stored_as_text_and_round_trip_exactly(make_config):
    from btc_paper_trader.service import Service

    cfg = make_config()
    aid = uuid.uuid4().hex
    svc = Service(cfg)
    async with svc.running():
        await svc.exchange.open_account(aid)
        await svc.tick(D("100000.01"))
        await svc.exchange.idle()
    rows = _query(cfg.db, "SELECT typeof(usd), usd, typeof(btc) FROM accounts WHERE account_id = ?", aid)
    assert rows, "the account must be persisted in the accounts table"
    usd_type, usd_text, btc_type = rows[0]
    assert usd_type == "text" and btc_type == "text"
    assert D(usd_text) == D("100")

    again = Service(cfg)
    async with again.running():
        acct = again.engine.account(aid)
        assert acct.usd == D("100")
        assert isinstance(acct.usd, D)


async def test_every_account_owned_table_is_keyed_by_account_id(make_config):
    from btc_paper_trader.service import Service

    cfg = make_config()
    async with Service(cfg).running():
        pass
    for table in ("accounts", "orders", "fills", "ledger"):
        cols = {row[1] for row in _query(cfg.db, f"PRAGMA table_info({table})")}
        assert "account_id" in cols, table
    for table in ("trades", "meta"):
        assert _query(cfg.db, f"PRAGMA table_info({table})"), table


async def test_committing_10k_account_rows_never_blocks_the_loop(make_config, loop_lag):
    """A1 (store part): max loop lag < 100 ms while the store writes 10,000 accounts."""
    from btc_paper_trader.service import Service

    svc = Service(make_config())
    async with svc.running():
        ids = [uuid.uuid4().hex for _ in range(10_000)]
        async with loop_lag() as lag:
            await asyncio.gather(*(svc.exchange.open_account(i) for i in ids))
            await svc.exchange.idle()
        assert lag.samples > 0
        assert lag.max_ms < 100, f"loop lag {lag.max_ms:.1f} ms"
        assert all(svc.engine.account(i) is not None for i in ids[:: 997])
