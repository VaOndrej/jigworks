# T11 · Vercel setup: Services, Neon, Blob

| Field | Value |
|---|---|
| Status | done |
| Owner | human (dashboard) + hub |
| Label | `milestone-3` |
| Size | S |
| Demo critical path | no (below the cut line) |
| Depends on | T01 |
| Human time | ~10 min (dashboard steps) |

## Goal

The existing Vercel project `jigworks` (Hobby, linked to this repo) gets Postgres and Blob and serves the T01 skeleton.

## Acceptance criteria

- [x] `vercel env ls` lists the Neon and Blob variables (`DATABASE_URL`, `BLOB_READ_WRITE_TOKEN`).
- [x] `curl -s <preview-url>/api/health` returns `{"ok":true}` and `/` returns 200.

## Steps

| Step | Who | State (19 Nov 2026) |
|---|---|---|
| `vercel login` + `vercel link` (repo-linked, project `jigworks`) | Ondřej | done |
| Blob store `jigworks-bundles` (private, all environments) | Ondřej (CLI) | done |
| Neon Postgres via Marketplace (Preview + Production) | Ondřej (dashboard) | done |
| `HUB_PASSWORD` (secret in Production + Preview, plain in Development) | Ondřej (CLI) | done |
| Protection Bypass for Automation secret in `.env.local` | Ondřej (dashboard) | optional; without it use `vercel curl` |
| Vercel Services (Beta) and Sandbox: confirm no opt-in is needed | agent, in the T01 smoke test | done: both work without opt-in |
| `vercel env pull .env.local`; verify the variables | agent | done |
| Preview deploy of the skeleton | agent | done |

Local development uses Postgres in Docker; Neon is only in Preview and Production.

Note: Hobby function duration limits SSE, so the client uses reconnect/polling (design.md §4).

## Evidence

Done by the foundation session on 19 Nov 2026 (team slug replaced by `<team>`; values never printed).

**`vercel env ls`** (names and environments only)

```
BLOB_READ_WRITE_TOKEN       Production, Preview, Development
HUB_PASSWORD                Development (plain) / Preview (secret) / Production (secret)
DATABASE_URL                Preview, Production
DATABASE_URL_UNPOOLED, POSTGRES_*, PG*, NEON_*  Preview, Production
```

`vercel env pull .env.local --yes` → exit 0. `.env.local` has no `DATABASE_URL`, as intended: local development uses Docker Postgres (`docker compose up -d db`, port 54329).

**Preview deploy of the T01 skeleton** (Services, no opt-in needed)

```
preview: https://jigworks-orrb6m0q1-<team>.vercel.app
$ vercel curl /api/health --deployment <preview>      → {"ok":true}
$ vercel curl / --deployment <preview>                → HTTP 200, <title>Jigworks Hub</title>
$ vercel curl /runs/deep-link --deployment <preview>  → HTTP 200 (index.html, SPA rewrite works)
$ curl -s -o /dev/null -w "%{http_code}" <preview>/api/health  → 302 (Deployment Protection)
```

Plain `curl` gets 302 because previews are protected; use `vercel curl` or the bypass header (`VERCEL_AUTOMATION_BYPASS_SECRET`, not set yet).

**Vercel Sandbox** (no opt-in needed)

```
$ vercel sandbox run --rm --runtime python3.13 -- python3 -c "print('sandbox ok', ...)"
✅ Sandbox scarlet-wilful-quail-youzPK created.  region: iad1  project: vercel-sandbox-default-project
sandbox ok 3.13.1
```

Note for HUB (T12): the CLI ran the sandbox in `vercel-sandbox-default-project`, not in `jigworks`; from the deployed API, create sandboxes with the project's OIDC token so they are billed and listed under `jigworks`.
