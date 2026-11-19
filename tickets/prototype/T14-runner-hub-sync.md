# T14 · Runner → hub event sync

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-3` |
| Size | M |
| Demo critical path | no (below the cut line) |
| Depends on | T06, T12 |
| Human time | — |

## Goal

The runner posts events to `POST /api/runs/{id}/events`, queues locally when offline and syncs after recovery.

## Acceptance criteria

- [ ] A test that cuts the network mid-run shows the queued events arriving afterwards; output pasted.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
