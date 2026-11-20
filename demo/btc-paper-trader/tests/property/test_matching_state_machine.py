"""Invariants 1-14 and 18 over the pure matching engine, as a Hypothesis state machine.

Four user accounts plus the house. Rules: open_account (idempotent re-open), submit (every type,
flag and size, including off-step and below-minimum inputs, stops, SL/TP and reduce-only),
cancel (own, foreign, unknown), reference_tick (gaps up to +-50%), advance time (stale gaps),
house_requote, reset and close_position. One ``inv_NN_*`` method per invariant.
"""

from collections import defaultdict
from decimal import Decimal as D

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from bpt_helpers import (
    GAP_FACTORS,
    PRICE_FACTORS,
    PROP_USERS,
    QTYS,
    T0,
    TERMINAL,
    apply_engine_command,
    new_prop_engine,
    order_snap,
    snap,
)

ACCOUNTS = PROP_USERS + ["house", "fees", "treasury"]
OPEN = {"open", "partially_filled"}
TRANSITIONS = {
    "new": {"new", "open", "partially_filled", "filled", "cancelled", "rejected"},
    "open": {"open", "partially_filled", "filled", "cancelled"},
    "partially_filled": {"partially_filled", "filled", "cancelled"},
}
TOL = D("0.000001")


class ExchangeMachine(RuleBasedStateMachine):
    @initialize()
    def setup(self):
        self.clock = {"now": T0}
        self.eng = new_prop_engine(T0)
        self.status = {}
        self.order_fields = {}
        self.fills = defaultdict(D)
        self.fee_sum = D(0)
        self.last = None
        self._record(None, "init", None, self._capture())

    # --- capture helpers ------------------------------------------------------------------

    def _all_orders(self):
        out = {}
        for a in ACCOUNTS:
            if self.eng.account(a) is None:
                continue
            for o in self.eng.orders(a, open_only=False):
                out[o.order_id] = o
        return out

    def _capture(self):
        eng = self.eng
        orders = self._all_orders()
        return {
            "accounts": {a: snap(eng.account(a)) for a in ACCOUNTS},
            "orders": {oid: order_snap(o) for oid, o in orders.items()},
            "order_obj": {
                oid: (o.account_id, o.side, o.type, o.price, o.reduce_only, o.qty, o.filled_qty)
                for oid, o in orders.items()
            },
            "open_by_account": {
                a: tuple(order_snap(o) for o in eng.orders(a, open_only=True))
                for a in ACCOUNTS
                if eng.account(a) is not None
            },
            "book": {s: [o.order_id for o in eng.book.iter_makers(s)] for s in ("buy", "sell")},
            "free_btc": {a: eng.account(a).free_btc for a in PROP_USERS},
        }

    def _record(self, issuer, kind, result, before):
        after = self._capture()
        trades = list(result.trades) if result is not None and result.trades else []
        for t in trades:
            self.fills[t.buy_order_id] += t.qty
            self.fills[t.sell_order_id] += t.qty
            self.fee_sum += t.buy_fee + t.sell_fee
        self.last = {
            "issuer": issuer,
            "kind": kind,
            "result": result,
            "trades": trades,
            "before": before,
            "after": after,
            "ref": self.eng.reference_price,
        }
        # status transitions are checked here because they need the previous state
        self.transition_errors = []
        for oid, o in self._all_orders().items():
            prev = self.status.get(oid)
            fields = (o.status, o.filled_qty, o.qty, o.reason)
            if prev is not None:
                if prev in TERMINAL:
                    if fields != self.order_fields[oid]:
                        self.transition_errors.append((oid, self.order_fields[oid], fields))
                elif o.status not in TRANSITIONS[prev]:
                    self.transition_errors.append((oid, prev, o.status))
            self.status[oid] = o.status
            self.order_fields[oid] = fields

    def _run(self, issuer, kind, cmd):
        before = self._capture()
        result = apply_engine_command(self.eng, self.clock, cmd)
        self._record(issuer, kind, result, before)
        return result

    # --- rules ----------------------------------------------------------------------------

    @rule(
        i=st.integers(0, 3),
        side=st.sampled_from(["buy", "sell"]),
        type_=st.sampled_from(["market", "limit", "limit", "stop"]),
        size=st.sampled_from(["qty", "qty", "qty", "quote", "max", "both", "none"]),
        qty=st.sampled_from(QTYS),
        pf=st.sampled_from(PRICE_FACTORS),
        sf=st.sampled_from(PRICE_FACTORS),
        off_tick=st.sampled_from([False] * 9 + [True]),
        ro=st.sampled_from([False, False, False, True]),
        sl=st.sampled_from([None, None, "0.98", "0.995", "1.01"]),
        tp=st.sampled_from([None, None, "1.02", "1.005", "0.99"]),
    )
    def submit(self, i, side, type_, size, qty, pf, sf, off_tick, ro, sl, tp):
        cmd = ("submit", i, side, type_, size, qty, pf, sf, off_tick, ro, sl, tp)
        free_before = self.eng.account(PROP_USERS[i]).free_btc
        r = self._run(PROP_USERS[i], "submit", cmd)
        assert r is not None and r.order is not None
        if r.order.status != "rejected":
            # 11: an accepted sell never exceeds the free BTC at submission
            if side == "sell" and r.order.qty is not None:
                assert r.order.qty <= free_before, (r.order.qty, free_before)
            sold = sum(t.qty for t in r.trades if t.sell_order_id == r.order.order_id)
            if side == "sell":
                assert sold <= free_before, (sold, free_before)
            # 12: reduce-only buys are refused
            if ro and side == "buy":
                raise AssertionError("reduce-only buy accepted")
        else:
            assert r.reason, "a rejection carries a reason"

    @rule(i=st.integers(0, 3), kind=st.sampled_from(["own", "own", "foreign", "unknown"]), n=st.integers(0, 50))
    def cancel(self, i, kind, n):
        r = self._run(PROP_USERS[i], "cancel", ("cancel", i, kind, n))
        if kind != "own":
            assert r.reason == "not_found"
            assert self.last["after"]["accounts"] == self.last["before"]["accounts"]
            assert self.last["after"]["orders"] == self.last["before"]["orders"]

    @rule(f=st.sampled_from(GAP_FACTORS))
    def reference_tick(self, f):
        self._run(None, "tick", ("tick", f))

    @rule(ms=st.sampled_from([1, 500, 2_000, 9_000, 10_500, 15_000]))
    def advance_time(self, ms):
        self.clock["now"] += ms

    @rule()
    def house_requote(self):
        self._run("house", "requote", ("requote",))

    @rule(i=st.integers(0, 3))
    def reset(self, i):
        a = PROP_USERS[i]
        epoch = self.eng.account(a).epoch
        self._run(a, "reset", ("reset", i))
        # 14: a reset equals a fresh account and touches no other account
        acct = self.eng.account(a)
        assert (acct.usd, acct.btc, acct.usd_reserved, acct.btc_reserved) == (D(100), 0, 0, 0)
        assert (acct.realized_pnl, acct.fees_paid, acct.cost_basis) == (0, 0, 0)
        assert acct.epoch == epoch + 1
        assert acct.equity == D(100)
        assert self.eng.orders(a, open_only=False) == []
        before, after = self.last["before"], self.last["after"]
        for other in PROP_USERS + ["house", "fees"]:
            if other != a:
                assert after["accounts"][other] == before["accounts"][other], other
                assert after["open_by_account"][other] == before["open_by_account"][other], other

    @rule(i=st.integers(0, 3))
    def close_position(self, i):
        a = PROP_USERS[i]
        had_btc = self.eng.account(a).btc > 0
        r = self._run(a, "close", ("close", i))
        if not had_btc:
            assert r.reason == "nothing_to_reduce"

    @rule(i=st.integers(0, 3))
    def reopen_account(self, i):
        a = PROP_USERS[i]
        before = self._capture()
        r = self.eng.open_account(a, kind="user", now_ms=self.clock["now"])
        self._record(a, "open", r, before)
        assert self.last["after"]["accounts"] == before["accounts"], "open_account must be idempotent"

    # --- invariants -----------------------------------------------------------------------

    @invariant()
    def inv_01_balances_never_negative(self):
        for a in PROP_USERS + ["house", "fees"]:
            v = self.eng.account(a)
            for f in ("usd", "btc", "available_usd", "free_btc", "usd_reserved", "btc_reserved"):
                assert getattr(v, f) >= 0, (a, f, getattr(v, f))

    @invariant()
    def inv_02_reservations_equal_open_orders(self):
        from btc_paper_trader.fees import buy_reservation

        for a in PROP_USERS + ["house"]:
            usd = D(0)
            btc = D(0)
            for o in self.eng.orders(a, open_only=True):
                if o.type != "limit" or o.status not in OPEN:
                    continue
                rem = o.qty - o.filled_qty
                if o.side == "buy":
                    usd += buy_reservation(rem, o.price)
                else:
                    btc += rem
            v = self.eng.account(a)
            assert v.usd_reserved == usd, (a, v.usd_reserved, usd)
            assert v.btc_reserved == btc, (a, v.btc_reserved, btc)

    @invariant()
    def inv_03_ledger_is_conserved(self):
        entries = list(self.eng.ledger())
        groups = defaultdict(D)
        per_account = defaultdict(D)
        for e in entries:
            groups[(e.ref, e.asset)] += e.amount
            per_account[(e.account_id, e.asset)] += e.amount
        bad = {k: v for k, v in groups.items() if v != 0}
        assert not bad, bad
        for a in ACCOUNTS:
            v = self.eng.account(a)
            assert per_account[(a, "usd")] == v.usd, a
            assert per_account[(a, "btc")] == v.btc, a

    @invariant()
    def inv_04_global_conservation(self):
        usd = sum(self.eng.account(a).usd for a in ACCOUNTS)
        btc = sum(self.eng.account(a).btc for a in ACCOUNTS)
        assert usd == 0 and btc == 0, (usd, btc)
        t = self.eng.totals()
        assert t["usd"]["total"] == 0 and t["btc"]["total"] == 0

    @invariant()
    def inv_05_book_never_crossed(self):
        bid, ask = self.eng.book.best_bid(), self.eng.book.best_ask()
        assert not self.eng.book.is_crossed()
        if bid is not None and ask is not None:
            assert bid < ask, (bid, ask)

    @invariant()
    def inv_06_price_time_priority(self):
        if not self.last or not self.last["trades"]:
            return
        before_book = self.last["before"]["book"]
        after_ids = set(self.last["after"]["book"]["buy"]) | set(self.last["after"]["book"]["sell"])
        for side in ("buy", "sell"):
            queue = before_book[side]
            makers = set()
            for t in self.last["trades"]:
                if t.maker_side == side:
                    makers.add(t.buy_order_id if side == "buy" else t.sell_order_id)
            idx = [queue.index(m) for m in makers if m in queue]
            if not idx:
                continue
            last = max(idx)
            skipped = [oid for oid in queue[:last] if oid in after_ids and oid not in makers]
            assert not skipped, f"{side}: better-priority orders {skipped} left while a worse one filled"
        # within one taker, fills go best price first
        by_taker = defaultdict(list)
        for t in self.last["trades"]:
            taker = t.sell_order_id if t.maker_side == "buy" else t.buy_order_id
            by_taker[taker].append(t.price)
        for taker, prices in by_taker.items():
            o = self.last["after"]["order_obj"].get(taker)
            if o is None:
                continue
            side = o[1]
            assert prices == (sorted(prices) if side == "buy" else sorted(prices, reverse=True)), (taker, prices)

    @invariant()
    def inv_07_trades_at_maker_price_within_limit_and_band(self):
        if not self.last or not self.last["trades"]:
            return
        ref = self.last["ref"]
        before = self.last["before"]["order_obj"]
        after = self.last["after"]["order_obj"]
        for t in self.last["trades"]:
            maker = t.buy_order_id if t.maker_side == "buy" else t.sell_order_id
            taker = t.sell_order_id if t.maker_side == "buy" else t.buy_order_id
            m = before.get(maker) or after.get(maker)
            if m is not None and m[2] == "limit":
                assert t.price == m[3], (t.price, m)
            tk = after.get(taker)
            if tk is not None and tk[2] == "limit":
                if tk[1] == "buy":
                    assert t.price <= tk[3]
                else:
                    assert t.price >= tk[3]
            assert ref * D("0.95") <= t.price <= ref * D("1.05"), (t.price, ref)

    @invariant()
    def inv_08_quantities_and_status_transitions(self):
        assert not self.transition_errors, self.transition_errors
        for t in self.last["trades"] if self.last else []:
            assert t.qty > 0
        for oid, o in self._all_orders().items():
            assert o.filled_qty == self.fills.get(oid, D(0)), (oid, o.filled_qty, self.fills.get(oid))
            if o.qty is not None:
                assert o.filled_qty <= o.qty, oid
            if o.status in ("new", "open", "rejected"):
                assert o.filled_qty == 0, (oid, o.status)
            if o.status == "partially_filled":
                assert o.filled_qty > 0, oid

    @invariant()
    def inv_09_fees_follow_maker_taker_and_sum_to_fee_account(self):
        from btc_paper_trader.fees import MAKER, TAKER, fee

        for t in self.last["trades"] if self.last else []:
            maker_fee, taker_fee = fee(t.qty, t.price, MAKER), fee(t.qty, t.price, TAKER)
            if t.maker_side == "buy":
                assert (t.buy_fee, t.sell_fee) == (maker_fee, taker_fee)
            else:
                assert (t.sell_fee, t.buy_fee) == (maker_fee, taker_fee)
        assert self.eng.account("fees").usd == self.fee_sum

    @invariant()
    def inv_10_quantization_and_minimum(self):
        step, tick, usd_q = D("0.00001"), D("0.01"), D("0.00000001")
        for a in ACCOUNTS:
            v = self.eng.account(a)
            assert v.usd % usd_q == 0 and v.btc % step == 0, a
            assert v.usd_reserved % usd_q == 0 and v.btc_reserved % step == 0, a
        for t in self.last["trades"] if self.last else []:
            assert t.qty % step == 0 and t.price % tick == 0
            assert t.buy_fee % usd_q == 0 and t.sell_fee % usd_q == 0
        for o in self._all_orders().values():
            if o.status == "rejected":
                continue
            assert o.qty is None or o.qty % step == 0, o.order_id
            assert o.filled_qty % step == 0, o.order_id
            if o.price is not None:
                assert o.price % tick == 0, o.order_id
            if o.stop_price is not None:
                assert o.stop_price % tick == 0, o.order_id
            user_order = o.account_id in PROP_USERS and o.parent_id is None and o.role == "entry" and not o.reduce_only
            if user_order and o.type == "limit":
                assert o.qty * o.price >= 1, o.order_id
            if user_order and o.type == "stop":
                assert o.qty * o.stop_price >= 1, o.order_id

    @invariant()
    def inv_11_long_only(self):
        for a in PROP_USERS + ["house"]:
            v = self.eng.account(a)
            assert v.btc >= 0 and v.free_btc >= 0 and v.btc_reserved <= v.btc

    @invariant()
    def inv_12_reduce_only_never_increases_and_flat_has_none(self):
        info = {**self.last["before"]["order_obj"], **self.last["after"]["order_obj"]} if self.last else {}
        for t in self.last["trades"] if self.last else []:
            b = info.get(t.buy_order_id)
            assert b is None or not b[4], f"reduce-only order {t.buy_order_id} bought"
        for a in PROP_USERS:
            if self.eng.account(a).btc != 0:
                continue
            for o in self.eng.orders(a, open_only=True):
                if o.status in OPEN:
                    assert not o.reduce_only, (a, o.order_id, o.role)
                    assert not (o.parent_id is not None and o.armed), (a, o.order_id)

    @invariant()
    def inv_13_pnl_identity(self):
        for a in PROP_USERS:
            v = self.eng.account(a)
            lhs = v.realized_pnl + v.unrealized_pnl - v.fees_paid
            assert abs(lhs - (v.equity - 100)) <= TOL, (a, lhs, v.equity)
            assert abs(v.return_pct - (v.equity - 100)) <= TOL

    @invariant()
    def inv_14_reset_checked_in_rule(self):
        # Checked inside the ``reset`` rule against the snapshot taken just before it.
        if self.last and self.last["kind"] == "reset":
            a = self.last["issuer"]
            assert self.eng.account(a).usd == D(100)

    @invariant()
    def inv_18_account_isolation(self):
        if not self.last or self.last["kind"] == "init":
            return
        before, after = self.last["before"], self.last["after"]
        allowed = {"fees", "treasury"}
        if self.last["issuer"]:
            allowed.add(self.last["issuer"])
        if self.last["kind"] == "requote":
            allowed.add("house")
        for t in self.last["trades"]:
            allowed |= {t.buy_account_id, t.sell_account_id}
        res = self.last["result"]
        for oid in (getattr(res, "triggered_order_ids", None) or []):
            o = before["order_obj"].get(oid) or after["order_obj"].get(oid)
            if o is not None:
                allowed.add(o[0])
        for a in ACCOUNTS:
            if a in allowed:
                continue
            assert after["accounts"][a] == before["accounts"][a], (self.last["kind"], a)
            assert after["open_by_account"].get(a) == before["open_by_account"].get(a), (self.last["kind"], a)


TestExchangeMachine = ExchangeMachine.TestCase
