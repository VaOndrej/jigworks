# T11 · Vercel setup: Services, Neon, Blob

| Field | Value |
|---|---|
| Status | todo |
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

| Step | Who |
|---|---|
| Enable Vercel Services (Beta) for the project, if it needs an opt-in | **Ondřej — dashboard** |
| Marketplace → Neon Postgres → install and connect to `jigworks` (all environments) | **Ondřej — dashboard** (accepts Marketplace terms) |
| Storage → Blob → create store, connect to `jigworks` | **Ondřej — dashboard** |
| Enable Vercel Sandbox for the project (needed by T13) | **Ondřej — dashboard** |
| `vercel link` in the repo | Ondřej once (login), then agent |
| `vercel env pull .env.local`; verify the variables exist | agent |
| Preview deploy of the T01 skeleton | agent |

Note: Hobby function duration limits SSE, so the client uses reconnect/polling (design.md §4).

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
