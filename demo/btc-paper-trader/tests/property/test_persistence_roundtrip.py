"""Invariant 15: after any command sequence, a restart on the same SQLite file restores the
engine exactly (``to_records()`` equal: accounts, open orders, book order, stops, seq counters,
last trade). Commands go through the real ExchangeTask and SqliteStore (temporary DB).

ExchangeTask contract used here: ``submit(req)``, ``cancel(account_id, order_id)``,
``reset(account_id)``, ``close_position(account_id)``, ``open_account(account_id)``.
"""

import asyncio
import uuid
from decimal import Decimal as D

from hypothesis import given, settings
from hypothesis import strategies as st

from bpt_helpers import (
    PROP_USERS,
    REF,
    FakeClock,
    build_request,
    command_strategy,
    pick_cancel_target,
    quantize_price,
)


async def _apply(service, clock, cmd):
    kind = cmd[0]
    ex = service.exchange
    if kind == "submit":
        await ex.submit(build_request(service.engine.reference_price, cmd))
    elif kind in ("tick", "requote"):
        ref = service.engine.reference_price or REF
        f = D(cmd[1]) if kind == "tick" else D(1)
        await service.tick(max(quantize_price(ref * f), D("1000")))
    elif kind == "advance":
        await clock.advance(cmd[1])
    elif kind == "cancel":
        acct, oid = pick_cancel_target(service.engine, cmd)
        await ex.cancel(acct, oid)
    elif kind == "reset":
        await ex.reset(PROP_USERS[cmd[1]])
    elif kind == "close":
        await ex.close_position(PROP_USERS[cmd[1]])
    await ex.idle()


async def _roundtrip(make_config, db, commands):
    from btc_paper_trader.service import Service

    clock = FakeClock()
    svc = Service(make_config(db=db, clock=clock.now, sleep=clock.sleep))
    async with svc.running():
        for u in PROP_USERS:
            await svc.exchange.open_account(u)
        await svc.tick(D("100000"))
        for cmd in commands:
            await _apply(svc, clock, cmd)
        await svc.exchange.idle()
        expected = svc.engine.to_records()
        expected_state = {u: svc.engine.account(u) for u in PROP_USERS}
        expected_state = {u: (v.usd, v.btc, v.usd_reserved, v.btc_reserved, v.epoch) for u, v in expected_state.items()}
        expected_book = (svc.engine.book.levels("buy", 50), svc.engine.book.levels("sell", 50))
        expected_last = svc.engine.last_trade_price

    again = Service(make_config(db=db, clock=clock.now, sleep=clock.sleep))
    async with again.running():
        got = again.engine.to_records()
        got_state = {
            u: (v.usd, v.btc, v.usd_reserved, v.btc_reserved, v.epoch)
            for u, v in ((u, again.engine.account(u)) for u in PROP_USERS)
        }
        got_book = (again.engine.book.levels("buy", 50), again.engine.book.levels("sell", 50))
        got_last = again.engine.last_trade_price
    return expected, got, expected_state, got_state, expected_book, got_book, expected_last, got_last


@settings(max_examples=25, stateful_step_count=20)
@given(commands=st.lists(command_strategy(), min_size=1, max_size=25))
def test_restart_restores_the_engine_exactly(make_config, tmp_path, commands):
    db = tmp_path / f"roundtrip-{uuid.uuid4().hex}.db"
    exp, got, exp_state, got_state, exp_book, got_book, exp_last, got_last = asyncio.run(
        _roundtrip(make_config, db, commands)
    )
    assert got_state == exp_state
    assert got_book == exp_book
    assert got_last == exp_last
    assert got == exp


def test_engine_from_records_of_to_records_is_identity():
    from btc_paper_trader.matching import Engine

    from bpt_helpers import apply_engine_command, new_prop_engine, T0

    eng = new_prop_engine()
    state = {"now": T0}
    cmds = [
        ("submit", 0, "buy", "market", "quote", "0.0003", "1", "1", False, False, "0.98", "1.02"),
        ("submit", 1, "buy", "limit", "qty", "0.0002", "0.999", "1", False, False, None, None),
        ("submit", 0, "sell", "stop", "qty", "0.0001", "1", "0.97", False, True, None, None),
        ("submit", 0, "sell", "limit", "qty", "0.0001", "1.03", "1", False, False, None, None),
    ]
    for c in cmds:
        apply_engine_command(eng, state, c)
    restored = Engine.from_records(eng.to_records())
    assert restored.to_records() == eng.to_records()
    for u in PROP_USERS:
        a, b = eng.account(u), restored.account(u)
        assert (a.usd, a.btc, a.usd_reserved, a.btc_reserved) == (b.usd, b.btc, b.usd_reserved, b.btc_reserved)
    assert restored.book.levels("buy", 50) == eng.book.levels("buy", 50)
    assert [o.order_id for o in restored.book.iter_makers("sell")] == [o.order_id for o in eng.book.iter_makers("sell")]
