# T03 · `sample-repo`: synthetic order-handling service with invariants

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | yes |
| Depends on | T01 |
| Human time | 10 min (review the invariants; this is what the senior engineer will poke at) |

## Goal

The target repo of the demo. It lives in this repo and makes "agents silently break invariants" visible.

## Acceptance criteria

- [x] Small Python service (orders, fills, partial fills, cancels, positions) with the invariants documented in `sample-repo/INVARIANTS.md` (e.g. filled ≤ ordered, position = Σ fills, no transition out of a terminal state).
- [x] Hypothesis property tests per invariant; `uv run pytest sample-repo` is green.
- [x] `bash sample-repo/scripts/break-invariant.sh` applies a plausible-looking bug and the property tests fail (output pasted).
- [x] Synthetic data only, no real instruments or accounts.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

**Property tests green.** `uv run pytest sample-repo -v`:

```
sample-repo/tests/test_examples.py   7 example tests                                  PASSED
sample-repo/tests/test_invariants.py::test_i1_filled_never_exceeds_ordered             PASSED
sample-repo/tests/test_invariants.py::test_i1_overfill_is_rejected                     PASSED
sample-repo/tests/test_invariants.py::test_i2_position_is_sum_of_signed_fills          PASSED
sample-repo/tests/test_invariants.py::test_i3_cancelled_order_cannot_fill_or_cancel_again PASSED
sample-repo/tests/test_invariants.py::test_i3_filled_order_cannot_be_cancelled         PASSED
sample-repo/tests/test_invariants.py::test_i3_rejected_order_stays_rejected            PASSED
sample-repo/tests/test_invariants.py::test_i3_terminal_states_have_no_outgoing_edges   PASSED
sample-repo/tests/test_invariants.py::test_i4_status_matches_quantities                PASSED
sample-repo/tests/test_invariants.py::test_i5_fill_log_is_append_only                  PASSED
sample-repo/tests/test_invariants.py::test_i6_never_fills_through_the_limit            PASSED
sample-repo/tests/test_invariants.py::test_i7_refused_operation_leaves_state_unchanged PASSED
sample-repo/tests/test_invariants.py::TestServiceStateMachine::runTest                 PASSED
============================== 19 passed in 2.56s ==============================
```

**Bugs are caught.** `bash sample-repo/scripts/break-invariant.sh all` (exit 0; each bug runs in a
temp copy, so the tree stays clean):

```
== bug 'overfill' (I1): 'simplify' the overfill guard to compare against the order size
   sample_repo/orders.py: if quantity > self.remaining:
   -> if quantity > self.quantity:
   example tests:  pass
   property tests: FAIL
     FAILED tests/test_invariants.py::test_i1_filled_never_exceeds_ordered
   => CAUGHT by the property tests
== bug 'cancel-terminal' (I3): 'inline' cancel and skip the transition table
   sample_repo/orders.py: self._transition(OrderStatus.CANCELLED)
   -> self.status = OrderStatus.CANCELLED
   example tests:  pass
   property tests: FAIL
     FAILED tests/test_invariants.py::test_i3_cancelled_order_cannot_fill_or_cancel_again
   => CAUGHT by the property tests
== bug 'position-cumulative' (I2): book the order's filled quantity instead of the fill's quantity
   sample_repo/service.py: order.side.sign * fill.quantity
   -> order.side.sign * order.filled_quantity
   example tests:  pass
   property tests: FAIL
     FAILED tests/test_invariants.py::test_i2_position_is_sum_of_signed_fills
   => CAUGHT by the property tests
== bug 'limit-one-sided' (I6): 'simplify' the limit check to one comparison for both sides
   sample_repo/orders.py: worse = price > self.limit_price if self.side is Side.BUY else price < self.limit_price
   -> worse = price > self.limit_price
   example tests:  pass
   property tests: FAIL
     FAILED tests/test_invariants.py::test_i6_never_fills_through_the_limit
   => CAUGHT by the property tests

4/4 bugs caught by the property tests
```

**`pnpm verify:local`:** `uv run pytest runner workflows sample-repo` → `21 passed in 2.65s`; the
extension skeleton test → `1 passing`, `Exit code: 0`.

## Notes

- Hypothesis runs derandomized (`tests/conftest.py`) so the gate is reproducible and the bugs are caught every run; the price is that it never explores new examples between runs.
- I4, I5 and I7 have no dedicated planted bug; the stateful test `TestServiceStateMachine` checks them after every step.
- `hypothesis` is a runtime dependency of `jigworks-sample-repo` (not a dev group), because the root `pyproject.toml` belongs to neither agent.
