# Invariants of the order-handling service

`sample-repo` is a small, **synthetic** order-handling service: made-up instruments
(`SYN-A`, `SYN-B`, …) and made-up accounts (`acc-1`, …). It exists to make one claim
visible: *agents silently break invariants*. Each invariant below is guarded by a
Hypothesis property test in `tests/test_invariants.py` (test names start with the id), and
by the stateful model test `TestServiceStateMachine`, which drives random sequences of
place / fill / cancel and checks every invariant after every step.

| Id | Invariant | Why it matters |
|---|---|---|
| **I1** | `0 ≤ filled_quantity ≤ quantity` for every order. A fill larger than `remaining` is rejected with `Overfill` and changes nothing. | An overfill creates exposure nobody asked for. |
| **I2** | `position(account, instrument) = Σ side.sign × fill.quantity` over all fills of that account and instrument (buy = +, sell = −). | Risk and P&L read positions, not fills; they must agree. |
| **I3** | No transition out of a terminal state (`filled`, `cancelled`, `rejected`). Fill, cancel or reject of a terminal order raises `InvalidTransition` and changes nothing. Only the edges in `ALLOWED_TRANSITIONS` exist. | A cancelled order that still fills is the classic silent bug. |
| **I4** | Status agrees with quantities: `filled` ⇔ `filled_quantity == quantity`; `partially_filled` ⇒ `0 < filled_quantity < quantity`; `new` ⇒ `filled_quantity == 0`; `rejected` ⇒ `filled_quantity == 0`. | The UI and downstream systems trust the status field. |
| **I5** | Fills are append-only: an order's fills are numbered `0..n-1` without gaps, every fill has `quantity > 0` and `price > 0`, and the service-wide fill log is exactly the concatenation (by time) of the orders' fills. | The fill log is the audit trail; positions are rebuilt from it. |
| **I6** | A limit order never fills at a worse price than its limit (buy: `price ≤ limit`, sell: `price ≥ limit`). | Executing through the limit is a client-facing breach. |
| **I7** | A rejected operation leaves the whole service unchanged (orders, fills, positions). | Errors must not leave half-applied state. |

## Commands

```bash
uv run pytest sample-repo                      # all property tests, green
bash sample-repo/scripts/break-invariant.sh    # applies a plausible-looking bug in a temp copy;
                                               # exits 0 only if the property tests catch it
bash sample-repo/scripts/break-invariant.sh --list   # list the available bugs
```

The bugs in `break-invariant.sh` look like reasonable refactors (an off-by-one in the
remaining check, cancel moved before the terminal check, a sign flip on sells). None of them
fails the plain example tests in `tests/test_examples.py`; only the property tests catch them.
That gap is the point of the demo.
