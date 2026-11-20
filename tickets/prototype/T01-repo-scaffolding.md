# T01 · Repo scaffolding

| Field | Value |
|---|---|
| Status | done |
| Owner | foundation (before the split) |
| Label | `milestone-0` |
| Size | S |
| Demo critical path | yes |
| Depends on | none (parallel with T00) |
| Human time | 5 min |

## Goal

The folder skeleton from design.md §12 with working workspaces. One repo holds everything (hub, runner, VS Code extension, sample-repo, demo) so it can be shared as a single repo.

## Acceptance criteria

- [x] `pnpm-workspace.yaml` (apps/hub-web, clients/vscode, packages/contracts) and root `package.json`; `pnpm install` succeeds.
- [x] Root `pyproject.toml` as a uv workspace (runner, apps/hub-api, sample-repo, workflows/feature-development); `uv sync` succeeds.
- [x] `vercel.json` declares Vercel Services (Beta) `hub-web` and `hub-api` with route prefixes (`/` and `/api`), following https://vercel.com/docs/services.
- [x] `docker-compose.yml` with Postgres for the hub; `scripts/check-ownership.sh`, the ownership `PreToolUse` hook, a git `pre-push` hook (no `main`, no force), and `.claude/settings.json` with the command allowlist (see docs/two-agent-build.md §5).
- [x] Toolchain smoke test, run with the human present: a Playwright headless screenshot, a hello-world extension under `@vscode/test-electron`, `docker compose up -d db` plus one query, `vercel deploy` of the skeleton, `claude -p` login check. Output pasted.
- [x] Root scripts `verify:hub`, `verify:local` and `verify:e2e` exist (stubs that each agent fills in), so both kickoff prompts can name them.
- [x] `.gitignore` keeps ignoring `.env*` secrets but allows `.env.example`; `.env.example` lists every variable the hub and the runner read (no values).
- [x] `pnpm -r test` and `uv run pytest` both run (trivially green); output pasted in the ticket's evidence section.

## Evidence

Run on 19 Nov 2026 (macOS, pnpm 12.21.0, uv 0.10.10, Node 26.12, Python 3.12, Docker 29.2, Vercel CLI 66.4, Claude Code 2.1.197). Team slug in URLs replaced by `<team>`.

**Workspaces**

```
$ pnpm install                       → Scope: all 4 workspace projects … Done
$ uv sync                            → Checked 23 packages
$ pnpm --filter vscode exec pwd      → <repo>/clients/vscode   (the extension package is named `vscode` so the documented filter works)
```

**`pnpm -r test`** (exit 0)

```
packages/contracts test: ℹ tests 1 / ℹ pass 1 / ℹ fail 0
apps/hub-web test:  Test Files  1 passed (1)   Tests  1 passed (1)
clients/vscode test:   1 passing (64ms)   Exit code:   0
```

**`uv run pytest`** (exit 0)

```
========================= 4 passed, 1 warning in 0.15s =========================
```

**Toolchain smoke test `bash scripts/smoke-toolchain.sh`** (exit 0, run with the human present; noise from the test VS Code host removed)

```
=== 1/5 Playwright headless screenshot (390 px + 1440 px)
  ✓  1 e2e/smoke/screenshot.spec.ts:5:3 › headless screenshot at 390px (152ms)
  ✓  2 e2e/smoke/screenshot.spec.ts:5:3 › headless screenshot at 1440px (65ms)
  2 passed (638ms)
e2e/screenshots/smoke-1440.png
e2e/screenshots/smoke-390.png
=== 2/5 hello-world extension under @vscode/test-electron
$ tsc -p . && node out/test/runTest.js
✔ Validated version: 1.147.0
✔ Found existing install in <repo>/clients/vscode/.vscode-test/vscode-darwin-arm64-1.147.0
    ✔ hello command is registered and runs
  1 passing (56ms)
Exit code:   0
=== 3/5 docker compose up -d db + one query
postgres ok: PostgreSQL 17.12 (Debian 17.12-1.pgdg13+1) on aarch64-unknown-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
=== 4/5 vercel deploy of the skeleton (preview)
preview: https://jigworks-orrb6m0q1-<team>.vercel.app
GET /api/health -> {"ok":true}
GET / -> HTTP 200
=== 5/5 claude login check + one tiny claude -p call
2.1.197 (Claude Code)
loggedIn: True | authMethod: claude.ai | subscription: max
result: ok | is_error: False | cost_usd: 0.030012800000000003
SMOKE TEST PASSED
```

**Ownership enforcement** (`scripts/ownership.sh` is the single path table)

```
hub apps/hub-web/x.ts -> allow            local apps/hub-api/x -> deny
hub runner/a.py -> deny                   hub packages/contracts/openapi.json -> allow
local runner/a.py -> allow                local packages/contracts/schema.json -> deny
local tickets/prototype/T16-x.md -> allow hub tickets/prototype/T16-x.md -> deny
hub uv.lock -> allow                      local AGENTS.md -> deny
$ git add -A && scripts/check-ownership.sh hub   → exit 1, lists .claude/…, .env.example, …
PreToolUse guard, JIGWORKS_AGENT=hub, Write runner/x.py → exit 2 "ownership-guard: agent 'hub' may not edit 'runner/x.py'…"
PreToolUse guard, JIGWORKS_AGENT=hub, Write apps/hub-web/x.ts → exit 0;  Write /tmp/x → exit 0
pre-push: push to main → exit 1; non-fast-forward → exit 1; branch delete → exit 1; fast-forward → exit 0
```

**What broke during the smoke test, and the fix (all committed)**

1. The cached Playwright Chromium was for an older Playwright; `pnpm exec playwright install chromium` fetched build 1255.
2. `@vscode/test-electron` failed with `bad option: --extensionTestsPath` because a terminal inside VS Code exports `ELECTRON_RUN_AS_NODE=1`; `runTest.ts` now deletes it before launching. Agents running in VS Code would have hit the same thing.
3. `vercel deploy` first failed on the root `prepare` script (no git on the build machine; now a no-op there), then on the 100 MB upload limit because of the 375 MB `.vscode-test` download; `.vercelignore` excludes it.

**Not covered here:** `verify:e2e` is a stub that exits 1 on purpose ("Nothing was verified") until LOCAL implements it. `verify:hub` / `verify:local` run only the current unit tests.
