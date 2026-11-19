# T11 · Vercel setup: Services, Neon, Blob

| Field | Value |
|---|---|
| Status | todo |
| Owner | human (dashboard) + hub |
| Label | `milestone-3` |
| Size | S |
| Demo critical path | no (below the cut line) |
| Depends on | T01 |
| Human time | ~10 min (dashboard steps) |

## Goal

The existing Vercel project `jigworks` (Hobby, linked to this repo) gets Postgres and Blob and serves the T01 skeleton.

## Acceptance criteria

- [ ] `vercel env ls` lists the Neon and Blob variables (`DATABASE_URL`, `BLOB_READ_WRITE_TOKEN`).
- [ ] `curl -s <preview-url>/api/health` returns `{"ok":true}` and `/` returns 200.

## Steps

| Step | Who | State (19 Nov 2026) |
|---|---|---|
| `vercel login` + `vercel link` (repo-linked, project `jigworks`) | Ondřej | done |
| Blob store `jigworks-bundles` (private, all environments) | Ondřej (CLI) | done |
| Neon Postgres via Marketplace (Preview + Production) | Ondřej (dashboard) | done |
| `HUB_PASSWORD` (secret in Production + Preview, plain in Development) | Ondřej (CLI) | done |
| Protection Bypass for Automation secret in `.env.local` | Ondřej (dashboard) | optional; without it use `vercel curl` |
| Vercel Services (Beta) and Sandbox: confirm no opt-in is needed | agent, in the T01 smoke test | todo |
| `vercel env pull .env.local`; verify the variables | agent | todo |
| Preview deploy of the skeleton | agent | todo |

Local development uses Postgres in Docker; Neon is only in Preview and Production.

Note: Hobby function duration limits SSE, so the client uses reconnect/polling (design.md §4).

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
