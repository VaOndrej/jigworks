# T12 · hub-api (FastAPI + Postgres)

| Field | Value |
|---|---|
| Status | todo |
| Owner | hub |
| Label | `milestone-3` |
| Size | L |
| Demo critical path | no (below the cut line) |
| Depends on | T02, T11 |
| Human time | — |

## Goal

The subset of design.md §8 that the minimal hub needs: workflows, draft, publish (bundle `.zip` to Blob + digest), releases, channel resolution, bundle download, runs + events ingest, usage analytics.

## Acceptance criteria

- [ ] Every endpoint except `/api/health` requires the hub password: a valid session cookie from the web login or the `X-Jigworks-Key` header equal to `HUB_PASSWORD` (env only, never in the repo). Tests cover 401 without it.
- [ ] `POST /api/auth/login` checks the password and sets the HTTP-only cookie; `POST /api/auth/logout` clears it.
- [ ] Draft files: list, read, create, rename and delete files and folders of a workflow package (for the editor's new file / new folder).
- [ ] `POST /api/workflows/{id}/validate` compiles the draft in Vercel Sandbox and returns syntax/import results and the `get_graph()` JSON (used by the editor's Graph view). Locally Sandbox is mocked with the contract fixture.
- [ ] Analytics endpoints for the Runs & analytics tab: key numbers, cost per day by token type, version comparison per workflow, runs list, run detail with the audit trail. Human-delta outcomes come from contract fixtures and are flagged as sample data.
- [ ] The database is seeded from `packages/contracts/fixtures/` so the hub shows realistic data before any real run.
- [ ] `uv run pytest apps/hub-api` passes against a local Postgres.
- [ ] A curl transcript against the preview deploy covers publish → resolve `stable` → download bundle → post run events → read usage.
- [ ] Workflow code is never executed in the API process.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
