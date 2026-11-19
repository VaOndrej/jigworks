# T03 · `sample-repo`: synthetic order-handling service with invariants

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | yes |
| Depends on | T01 |
| Human time | 10 min (review the invariants; this is what the senior engineer will poke at) |

## Goal

The target repo of the demo. It lives in this repo and makes "agents silently break invariants" visible.

## Acceptance criteria

- [ ] Small Python service (orders, fills, partial fills, cancels, positions) with the invariants documented in `sample-repo/INVARIANTS.md` (e.g. filled ≤ ordered, position = Σ fills, no transition out of a terminal state).
- [ ] Hypothesis property tests per invariant; `uv run pytest sample-repo` is green.
- [ ] `bash sample-repo/scripts/break-invariant.sh` applies a plausible-looking bug and the property tests fail (output pasted).
- [ ] Synthetic data only, no real instruments or accounts.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
