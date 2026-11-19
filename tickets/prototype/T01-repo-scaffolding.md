# T01 · Repo scaffolding

| Field | Value |
|---|---|
| Status | todo |
| Owner | foundation (before the split) |
| Label | `milestone-0` |
| Size | S |
| Demo critical path | yes |
| Depends on | none (parallel with T00) |
| Human time | 5 min |

## Goal

The folder skeleton from design.md §12 with working workspaces. One repo holds everything (hub, runner, VS Code extension, sample-repo, demo) so it can be shared as a single repo.

## Acceptance criteria

- [ ] `pnpm-workspace.yaml` (apps/hub-web, clients/vscode, packages/contracts) and root `package.json`; `pnpm install` succeeds.
- [ ] Root `pyproject.toml` as a uv workspace (runner, apps/hub-api, sample-repo, workflows/feature-development); `uv sync` succeeds.
- [ ] `vercel.json` declares Vercel Services (Beta) `hub-web` and `hub-api` with route prefixes (`/` and `/api`), following https://vercel.com/docs/services.
- [ ] `docker-compose.yml` with Postgres for the hub; `scripts/check-ownership.sh`, the ownership `PreToolUse` hook, a git `pre-push` hook (no `main`, no force), `scripts/overnight.sh` and `prompts/overnight-{hub,local}.md` (see docs/two-agent-build.md).
- [ ] Toolchain smoke test, run with the human present: a Playwright headless screenshot, a hello-world extension under `@vscode/test-electron`, `docker compose up -d db` plus one query, `vercel deploy` of the skeleton, `claude -p` login check. Output pasted.
- [ ] `pnpm -r test` and `uv run pytest` both run (trivially green); output pasted in the ticket's evidence section.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
