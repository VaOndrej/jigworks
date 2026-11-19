# T14 · Runner → hub event sync

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-3` |
| Size | M |
| Demo critical path | no (below the cut line) |
| Depends on | T06 (T12 for the live check; until then a mock from `openapi.json`) |
| Human time | — |

## Goal

The runner posts events to `POST /api/runs/{id}/events`, queues locally when offline and syncs after recovery.

## Notes

Only the runner side. The hub's ingest endpoint is part of T12.

## Acceptance criteria

- [ ] A test that cuts the network mid-run shows the queued events arriving afterwards; output pasted.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
