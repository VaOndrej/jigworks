"""Invariant 17: the same seed and command sequence give identical trades, events and records
(the engine and the sim feed)."""

from hypothesis import given
from hypothesis import strategies as st

from bpt_helpers import T0, apply_engine_command, command_strategy, new_prop_engine


def _run(commands):
    eng = new_prop_engine()
    state = {"now": T0}
    log = []
    for cmd in commands:
        r = apply_engine_command(eng, state, cmd)
        if r is None:
            continue
        log.append(
            (
                r.reason,
                None if r.order is None else (r.order.order_id, r.order.status, r.order.filled_qty),
                [(t.trade_id, t.price, t.qty, t.buy_order_id, t.sell_order_id, t.buy_fee, t.sell_fee) for t in r.trades],
                repr(r.events),
                list(r.triggered_order_ids or []),
            )
        )
    return log, eng.to_records()


@given(commands=st.lists(command_strategy(), max_size=40))
def test_same_commands_give_identical_trades_events_and_records(commands):
    assert _run(commands) == _run(commands)


@given(seed=st.integers(min_value=0, max_value=2**31 - 1), n=st.integers(min_value=1, max_value=100))
def test_sim_feed_with_the_same_seed_gives_the_same_ticks(seed, n):
    from btc_paper_trader.feeds.sim import SimFeed

    async def sleep(_):
        return None

    def ticks():
        f = SimFeed(seed=seed, start_ms=T0, tick_ms=500, clock=lambda: T0, sleep=sleep)
        return [(t.price, t.ts_ms) for t in (f.step() for _ in range(n))]

    assert ticks() == ticks()
