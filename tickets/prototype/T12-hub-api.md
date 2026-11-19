# T12 · hub-api (FastAPI + Postgres)

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-3` |
| Size | L |
| Demo critical path | no (below the cut line) |
| Depends on | T02, T11 |
| Human time | — |

## Goal

The subset of design.md §8 that the minimal hub needs: workflows, draft, publish (bundle `.zip` to Blob + digest), releases, channel resolution, bundle download, runs + events ingest, usage analytics.

## Acceptance criteria

- [ ] `uv run pytest apps/hub-api` passes against a local Postgres.
- [ ] A curl transcript against the preview deploy covers publish → resolve `stable` → download bundle → post run events → read usage.
- [ ] Workflow code is never executed in the API process.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
