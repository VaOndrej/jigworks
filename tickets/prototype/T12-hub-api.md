# T12 · hub-api (FastAPI + Postgres)

| Field | Value |
|---|---|
| Status | done |
| Owner | hub |
| Label | `milestone-3` |
| Size | L |
| Demo critical path | no (below the cut line) |
| Depends on | T02, T11 |
| Human time | — |

## Goal

The subset of design.md §8 that the minimal hub needs: workflows, draft, publish (bundle `.zip` to Blob + digest), releases, channel resolution, bundle download, runs + events ingest, usage analytics.

## Acceptance criteria

- [x] Every endpoint except `/api/health` requires the hub password: a valid session cookie from the web login or the `X-Jigworks-Key` header equal to `HUB_PASSWORD` (env only, never in the repo). Tests cover 401 without it.
- [x] `POST /api/auth/login` checks the password and sets the HTTP-only cookie; `POST /api/auth/logout` clears it. *Implemented at the frozen contract's paths: `POST /api/session` (login) and `DELETE /api/session` (logout); see Notes.*
- [x] Draft files: list, read, create, rename and delete files and folders of a workflow package (for the editor's new file / new folder).
- [x] `POST /api/workflows/{id}/validate` compiles the draft in Vercel Sandbox and returns syntax/import results and the `get_graph()` JSON (used by the editor's Graph view). Locally Sandbox is mocked with the contract fixture.
- [x] Analytics endpoints for the Runs & analytics tab: key numbers, cost per day by token type, version comparison per workflow, runs list, run detail with the audit trail. Human-delta outcomes come from contract fixtures and are flagged as sample data.
- [x] The database is seeded from `packages/contracts/fixtures/` so the hub shows realistic data before any real run.
- [x] `uv run pytest apps/hub-api` passes against a local Postgres.
- [x] A curl transcript against the preview deploy covers publish → resolve `stable` → download bundle → post run events → read usage.
- [x] Workflow code is never executed in the API process.

## Notes

- **Login paths.** The criterion names `/api/auth/login` and `/api/auth/logout`; the frozen contract (`openapi.json`, `PUBLIC_ENDPOINTS`) names `POST /api/session` and `DELETE /api/session`. The contract wins (it is frozen and LOCAL codes against it); no aliases, because `test_openapi_states_the_auth_rule` allows exactly two public operations.
- **Draft files** use the contract's full-replacement `PUT /api/workflows/{id}/draft`: create, rename and delete are list edits (tested one by one); a folder exists through its files (`<folder>/.gitkeep` for an empty one). A PUT to an unknown id creates the workflow from a minimal template ("New workflow").
- **Never executed in the API process:** the API only parses (`tomllib`, `ast.parse`). Imports, `compile()` and `get_graph()` run in Vercel Sandbox (default image, Python 3.14 + uv, package installed from its `requirements.lock`); `test_validation_never_imports_workflow_code` puts an import guard on the API process while validating a draft whose `graph.py` would exit on import. Locally (no OIDC token) the last three checks return the recorded `get_graph()` fixture and say "mocked locally".
- **Real Sandbox proof:** `bash e2e/hub/sandbox-smoke.sh` validated the contract package in a real sandbox in 11.5 s and its normalized graph equals `fixtures/graph/feature-development-1.3.0.graph.json` exactly. On the preview the sandbox is created with the request's OIDC token (project `jigworks`).
- **Key numbers / cost per day by token type** are not in the contract; they come from a hub-only `GET /api/analytics/overview` (model in `hub_api/extensions.py`, documented in `openapi.json`). Only hub-web reads it.
- **Seed:** contract fixtures are copied byte-identically into `hub_api/seed_data/` (the Vercel function only ships `apps/hub-api`); `test_seed_data.py` fails on drift. Seeded runs go through the same register + ingest path as runner traffic. Channels follow `release-list.json` (1.3.0 → stable); `workflow-list.json` also claims `beta 1.3.0` (the fixtures disagree).
- **Local Postgres:** Docker Desktop could not start overnight (disk 98 % full); the tests ran on a private Postgres 16 on the same port 54329 (build log).

## Evidence

**Tests against local Postgres** (`uv run pytest apps/hub-api packages/contracts`, inside `pnpm verify:hub`, 19 Nov 2026 22:06 UTC):

```
== uv run pytest apps/hub-api packages/contracts
125 passed, 17 warnings in 6.01s
```

(70 hub-api tests: 401 on all 21 protected operations, cookie login/logout, fail-closed without `HUB_PASSWORD`, ErrorResponse shape for 422, seeded data equal to `run-list.json`, `run-detail.json`, `release-list.json`, `channel-stable.json`, draft create/rename/delete/bad paths, validate ok/syntax error with file+line/manifest, no import in the API process, publish round trip with deterministic bytes and 409 on re-publish, idempotent run registration, ingest dedupe, kind→payload validation, SSE replay with Last-Event-ID, usage grouping by release/model/node/day with cost equal to the CLI's `costUSD`, version comparison, planned outcomes, overview numbers, committed `openapi.json` equal to the app's. The 17 warnings are a `langsmith` DeprecationWarning under Python 3.14 from LOCAL's workflow dependency.)

`packages/contracts/openapi.json` regenerated from the app (`uv run python apps/hub-api/scripts/export_openapi.py`); the contract compatibility tests stay green:

```
$ uv run pytest packages/contracts -q -k openapi
3 passed, 52 deselected
```

**curl transcript against the preview** (`bash e2e/hub/preview-api.sh https://jigworks-4ssz529wq-<team>.vercel.app`, Neon + Blob + Sandbox, trimmed):

```
# auth
$ curl -X GET /api/health                         → 200 {"ok":true}
$ curl -X GET /api/workflows                      → 401 {"error":{"code":"unauthorized",…}}
$ curl -X POST /api/session (wrong)               → 401 {"error":{"code":"unauthorized","message":"wrong hub password"}}
$ curl -X POST /api/session                       → 204
  set-cookie: jigworks_session=<redacted>; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax; Secure
$ curl -X GET /api/workflows  [X-Jigworks-Key]    → 200 {"workflows":[{"id":"feature-development",…

# publish a smoke workflow (validated in Vercel Sandbox)
$ curl -X POST /api/workflows/smoke-check/validate  → 200 {"ok":true,…}
  checks: manifest=true, syntax=true, imports=true, compile=true, graph=true (3 nodes)
  graph nodes: __start__ → plan → approve_plan → implement → __end__  durationMs=7917
$ curl -X POST /api/workflows/smoke-check/publish   → 201
  release smoke-check@0.1.1795125990 id=rel_bb7c4ad7474c42a7 digest=sha256:62b557be…821343f bundleBytes=1486

# resolve stable → download bundle → check digest
$ curl -X GET /api/workflows/smoke-check/channels/stable → 200 {"releaseId":"rel_bb7c4ad7474c42a7","digest":"sha256:62b557be…",…}
$ curl /api/releases/rel_bb7c4ad7474c42a7/bundle
  → 1486 bytes, X-Jigworks-Digest=sha256:62b557be…821343f, sha256(bytes)=sha256:62b557be…821343f
  files: README.md graph.py prompts/plan.md requirements.lock steps/__init__.py steps/nodes.py workflow.toml

# register a run → post events (twice) → read usage
$ curl -X POST /api/runs                            → 201 {"runId":"run_smoke_1795126001",…}
$ curl -X POST /api/runs/run_smoke_1795126001/events → 200 {"accepted":5,"duplicates":0,"lastSeq":4}
$ curl -X POST /api/runs/run_smoke_1795126001/events → 200 {"accepted":0,"duplicates":5,"lastSeq":4}
$ curl -X GET /api/runs/run_smoke_1795126001        → status=cancelled progress=20.0 costUsd=0.17082
$ curl -X GET /api/analytics/usage?groupBy=release&workflowId=smoke-check
  smoke-check@0.1.1795125990: runs=1 input=40 output=2100 cache_write=18400 cache_read=96000 costUsd=0.17082 (API equivalent)

# SSE stream
$ curl -N /api/runs/run_smoke_1795126001/events/stream?after=-1
  → 5 messages: run_started,node_status,usage,node_status,node_status
preview-api: OK
```

(0.17082 = 40×3 + 2100×15 + 18400×6 + 96000×0.3 per Mtok, the sonnet-5 prices.)

**Bundles really are in Blob** (`bash e2e/hub/blob-ls.sh`):

```
2026-11-19 21:30    3214 B  bundles/feature-development/feature-development-1.2.0-7fdedf35076f54ad.zip
2026-11-19 21:30    3255 B  bundles/feature-development/feature-development-1.3.0-e941f267e18b9756.zip
2026-11-19 21:33    1485 B  bundles/smoke-check/smoke-check-0.1.1795124003-607eebb41a5c436b.zip
…
```

**Real Sandbox from this machine** (`bash e2e/hub/sandbox-smoke.sh`): `ok: true`, checks manifest/syntax/imports/compile/graph (10 nodes), `durationMs: 11451`, `graph equals the contract fixture: True`.
