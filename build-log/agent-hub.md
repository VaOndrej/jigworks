# Build log: HUB agent (overnight, 19–20 Nov 2026)

Agent: Claude Code (Opus 5.5), worktree `~/Development/jigworks-hub`, branch `agent/hub`, pushing to
`feature/hub-and-vs-code-extension`. Session started in the main checkout (`JIGWORKS_AGENT` empty);
after the human's update every command ran in the HUB worktree and `scripts/check-ownership.sh hub`
ran before every commit.

## Time

| | Human | Agent |
|---|---|---|
| T12 hub-api | 0 (asleep) | ~45 min |
| T13 hub-web | 0 (asleep) | ~40 min |
| Infra detours (Sandbox SDK, Docker down) | 0 | ~10 min (inside the above) |
| **Session** | **0** (the 10 min launch fix is in BUILD_LOG.md) | **~1 h 25 min** (≈ 22:05–23:30 CET) |

## Decisions taken without the human

### D1 · Login paths follow the frozen contract, not the ticket text
T12 says `POST /api/auth/login` / `logout`; `openapi.json` and `PUBLIC_ENDPOINTS` say `POST /api/session`
and `DELETE /api/session`. The contract is frozen and LOCAL codes against it, and
`test_openapi_states_the_auth_rule` allows exactly two public operations, so: contract paths, no aliases.

### D2 · Draft file operations through the contract's full-replacement PUT
No per-file endpoints in the contract. Create/rename/delete files and folders are list edits sent with
`PUT /draft`; an empty folder is `<folder>/.gitkeep`. `PUT` on an unknown id creates the workflow from a
minimal LangGraph template (the "New workflow" button). No contract change needed.

### D3 · Hub-only `GET /api/analytics/overview`
"Key numbers" and "cost per day by token type" have no contract endpoint (`UsageReportRow` has one
`costUsd`, not a split per token type). Added a hub-only endpoint with its own pydantic model
(`hub_api/extensions.py`); only hub-web reads it, `openapi.json` documents it, the stub compatibility
test stays green. Not a contract change: nothing on the seam uses it.

### D4 · Validation: parse in the API, execute only in Vercel Sandbox
Manifest (`tomllib` + `WorkflowManifest`) and syntax (`ast.parse`) run in the API process (parsing,
not executing); imports, `compile()` and `get_graph()` run in a fresh Vercel Sandbox. Results are cached
per draft content hash, so the Graph toggle and Publish do not pay the sandbox twice. Without an OIDC
token (tests, local dev) the sandbox checks return the contract's recorded `get_graph()`, labelled
"mocked locally".

### D5 · Sandbox SDK 1.x: default image, uv venv
`vercel-sandbox` 1.0.1 removed `runtime=` (first preview: `TypeError`); `image=python3.13` 404s. The
default image has Python 3.14 and `uv` (checked with `vercel sandbox run`), and its working directory is
not `/vercel/sandbox` (second preview: `chdir` error). Now: default image, `sb.cwd`, `uv venv` +
`uv pip install -r requirements.lock`. The real sandbox reproduces the contract graph exactly.

### D6 · Bundles: Blob when the token is set, Postgres bytea otherwise
Preview/Production write to the private Blob store (`blob-ls.sh` lists them); tests and local dev keep
bytes in a `bundles` table. Every read re-checks the digest. Blob pathnames contain the digest, so
overwrite is safe for re-seeding.

### D7 · Seed through the real ingest path; channels from `release-list.json`
Fixture runs are registered and ingested like runner traffic, so the seeded hub exercises the projection.
The two fixtures disagree on channels (`workflow-list.json`: beta 1.3.0; `release-list.json`: 1.3.0 on
stable only); I followed `release-list.json`. Fixtures are copied into `hub_api/seed_data/` because the
Vercel function only ships `apps/hub-api`; a test fails if the copy drifts.

### D8 · UTC on every connection
A Postgres in CET returned `+01:00` timestamps and broke the fixture equality tests. Each transaction now
runs `SET LOCAL TIME ZONE 'UTC'` (a startup option would be rejected by Neon's pooler).

### D9 · Docker Desktop down: private Postgres 16 on port 54329
Mid-session Docker Desktop stopped ("unable to start"). Cause: the disk is **98 % full (≈ 0.5 GB free)**.
I pruned only the uv cache (`uv cache prune`, regenerable) and did not delete anything of yours. Local
tests since then run on a private Postgres 16 from the Homebrew binaries
(`initdb` into the session scratchpad, `pg_ctl … -p 54329`), same credentials as docker-compose. It is
not your Homebrew `postgresql@16` service and does not touch its data. `verify.sh` now uses whatever
listens on 54329 and starts Docker only if nothing does. **Action for you:** free disk space, restart
Docker Desktop; the scratch instance disappears with the scratchpad (stop it with
`/opt/homebrew/opt/postgresql@16/bin/pg_ctl -D <scratchpad>/pgdata stop` if it is still running).

### D10 · Local screenshots with uvicorn + Vite, not `vercel dev`
`local-e2e.sh` runs hub-api under uvicorn and the web under Vite with an `/api` proxy (the same routing
as `vercel.json`) on a fresh seeded database and a local-only password. Reason: deterministic data,
no dependency on the linked project or the real secret, and the deployed path is covered by the same
Playwright suite on the preview.

### D11 · Web build is `vite build`; types come type-only from the contracts' generated file
hub-web imports types from `packages/contracts/src/generated/types.ts` via tsconfig `paths`, so the
Vercel build does not depend on a built workspace package. `tsc -b` runs in the hub-web test script.

### D12 · Mockup deviations
`team: trading-platform` → **Sign out** (no teams, a logout is needed); one seeded workflow, not three;
"Merged" → **PR opened** (no merge signal yet); the version table shows the contract's columns plus gate
pass on the first try and median time to PR; times in the audit trail are UTC. The **Non-coding teams**
text is mine, from design.md §10; design.md says Ondřej describes the use cases, so please rewrite it.

## Ticket entries

### T12 · hub-api — done
- **Built:** FastAPI app on Postgres (psycopg 3): password middleware (cookie = HMAC of the password, or
  `X-Jigworks-Key`), ErrorResponse handlers, drafts, validation (D4/D5), deterministic publish to Blob,
  releases, channels + rollback, bundle download with digest, idempotent run registration, batch ingest
  with JSON-Schema validation and `(runId, seq)` dedupe, a pure projection events → RunSummary/AuditRecord
  (equal to the contract fixtures), polling + SSE with `Last-Event-ID`, usage by release/model/node/day
  priced at read time, version comparison, planned outcomes, overview. `openapi.json` regenerated.
- **Evidence:** 70 hub-api tests (125 with contracts) green; preview transcript publish → stable →
  bundle digest → run + events (dedupe) → usage → SSE; Blob listing; real Sandbox graph = fixture.
- **What went wrong:** Sandbox SDK API change (D5, two preview round trips); UTC (D8); Docker (D9).

### T13 · hub-web — done
- **Built:** password screen; Workflows (weekly numbers, table with step shape, live sessions with the
  Review badge, recent releases, new workflow); editor (file tree with templates, rename/delete, CodeMirror,
  autosave, Validate, `[models]` panel, releases with promote/roll back, GitHub source bar Planned, publish
  dialog); Graph (React Flow from `/validate`, run overlay, selected-node panel); Runs & analytics (key
  numbers, cost per day by token type, outcomes Planned + sample, version comparison, runs, audit trail with
  Planned human delta); Non-coding teams text.
- **Evidence:** 9 unit tests; Playwright 6/6 on localhost and 6/6 on the preview at 1440 px; screenshots in
  `e2e/hub/screenshots/`.
- **What went wrong:** test-only issues (substring link names, hidden hover tools, a nested-button tree row
  that I restructured), a stale selection after deleting the open file (fixed), overlapping edge labels (fixed).

## Summary (queue empty)

| Ticket | Status | Evidence | Blocked |
|---|---|---|---|
| T12 hub-api | done | `pnpm verify:hub`: 125 Python tests; preview curl transcript (publish → resolve stable → download + digest → events → usage → SSE); Blob listing; real Sandbox graph = contract fixture | — |
| T13 hub-web | done | Playwright 6/6 localhost + 6/6 preview at 1440 px, screenshots `e2e/hub/screenshots/{local,preview}-*-1440.png`; 9 unit tests | — |

Human vs agent time: human 0 tonight (launch fix logged in BUILD_LOG.md), agent ≈ 1 h 25 min.

### Self-audit: anything hacked, cut short, worked around or left unsaid?

Ordered by severity.

1. **Disk full, Docker down (worked around, needs you).** Local Postgres is a scratch instance, not the
   compose service (D9). Everything passed on it, and the preview uses Neon, but "Docker Postgres" as
   written in the ticket was not what the final run used.
2. **Shared Preview database collects smoke data (deliberate trade-off).** Every `preview-api.sh` run
   publishes a new `smoke-check@0.1.<epoch>` release (immutable by design) and a cancelled run; the preview
   Workflows tab shows a `smoke-check` workflow. Harmless, but visible in a demo; delete the workflow rows in
   the Preview Neon branch, or point the transcript at a throwaway branch, before showing it.
3. **Publish holds a DB transaction during the sandbox run (done, known limit).** On a cache miss, publish
   validates inside the transaction (~8–15 s). Fine for a prototype; a busy hub would validate first and
   publish in a short transaction. A Blob upload whose transaction later fails leaves an orphan blob.
4. **SSE on Vercel verified only as "replays and ends" (done but partly unverified).** The transcript got
   all 5 events and the stream closed; I did not measure behaviour at the function's real time limit or
   with a client reconnecting in a loop. The web does not use SSE (it loads on navigation); live updates
   in the hub UI are not built.
5. **Unknown models cost $0 (deliberate).** A model missing from the price table is priced at 0 and the
   price list is returned with every report; there is no warning in the UI.
6. **Sandbox failures surface as a failed "imports" check (deliberate).** An outage of Vercel Sandbox is
   shown as `imports: Vercel Sandbox failed: …`, not as a 5xx; the result is not cached.
7. **"Worked first time", the human-delta box and "where humans edit most" are sample data** from
   `human-deltas.json` (4 records), labelled PLANNED everywhere. With 7 seeded runs the analytics numbers
   are small and the "this week" window will empty out a week after 19 Nov (fixture dates are fixed).
8. **No auth rate limiting** on `POST /api/session` (one shared password, public URL).
9. **Non-coding text written by me** (D12), and the workflow table's step shape treats a node named `gate`
   as the gate (no contract field says which node is a gate).
