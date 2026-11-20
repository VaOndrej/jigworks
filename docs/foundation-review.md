# Foundation review (T00–T02), 19 Nov 2026

A 10-minute read before the contracts are frozen and the overnight agents start.
Branch: `feature/hub-and-vs-code-extension`. Every ticket's Evidence section holds the
command output; this page holds only what you need to decide.

## 1. What was built

| Ticket | Status | Result |
|---|---|---|
| T00 | done | `scripts/spike-claude.sh` (asserts every finding, exit 0), 7 scrubbed recordings in `runner/tests/fixtures/stream-json/`, findings in [`docs/spikes/claude-stream-json.md`](spikes/claude-stream-json.md) |
| T01 | done | pnpm + uv workspaces, skeletons (hub-api `/api/health`, Vite hub-web, hello-world extension, Python members), `vercel.json` Services, Docker Postgres, ownership table + check script + PreToolUse guard + pre-commit / pre-push hooks, `.claude/settings.json` allowlist, verify stubs, toolchain smoke test (passed with you present) |
| T11 | done (agent part) | env pulled, Services and Sandbox need no opt-in, skeleton preview serves `/api/health` → `{"ok":true}` and `/` → 200 |
| T02 | **review** | [`packages/contracts/`](../packages/contracts/README.md): one JSON Schema → pydantic models, TS types (ESM + CJS), `openapi.json` (21 operations), validators in both languages, fixtures. 55 Python + 29 TS tests |

## 2. T00 findings that change something

1. **Usage comes from the final `result` event, per model** (`result.modelUsage[model]`). Streamed assistant events repeat the same usage once per content block, and their `output_tokens` is partial (8 vs 201). Summing them would be wrong. Contracts and adapter follow this.
2. **Prices check out exactly.** Haiku 4.5 is $1 / $5 / $0.10 cache read / $2 cache write; Sonnet 5 is $3 / $15 / $0.30 / $6 per MTok. These reproduce the CLI's own `costUSD` to the cent (a test checks it). `claude -p` writes **1-hour** cache, which costs 2× input, not 1.25×.
3. **Preflight:** `claude auth status --json` costs nothing. Exit 0 with `loggedIn: true` means OK. Not logged in gives exit 1 and `loggedIn: false`. A run that is not logged in reports `result.subtype: "success"` with `is_error: true`, so the adapter must check `is_error`. `apiKeySource` is `"none"` even when logged in, so it is useless as a signal.
4. **Usage limits:** every run emits a `rate_limit_event` (`status: allowed`, `rateLimitType: five_hour`, `resetsAt`). The shape at the actual limit (`allowed_warning` / `rejected`) is **inferred**, since we could not trigger it.
5. **Plan mode is unusable in the runner.** It is non-deterministic, wrote plan files under `~/.claude/plans/`, and silently switched `--model haiku` to `claude-sonnet-5` (~$0.43 a tiny run). Restrict tools with `--allowedTools` / `--tools` instead.
6. **User settings leak into `claude -p`.** Your global hooks, plugins and skills load into every run unless the runner passes `--setting-sources project`. `--bare` would isolate fully but rejects the Max subscription login.
7. **Auto-memory writes outside the repo** (`~/.claude/projects/<cwd>/memory/`) when a prompt says "remember". How to switch it off is not verified yet; that is T04's job.
8. **Gotchas for T04:** put the prompt before `--allowedTools` (that flag swallows what follows), close stdin, `--verbose` is required with stream-json, and resume only from the same cwd.

## 3. Decisions I made that the docs left open (please confirm before the freeze)

1. **`kind` defaults to `node_status`**, so the design.md §8 example validates unchanged. Each other kind requires its own payload object (`interrupt`, `reviewDecision`, …). Pydantic cannot express that rule, so the boundary code calls `validate()` / `parse_event()`.
2. **Extra kinds** beyond the ticket: `run_started`, `gate_result` (audit needs gate results) and `run_finished` (carries the summary).
3. **`seq` per run is optional in the schema but required at ingest.** The hub dedupes on `(runId, seq)`, so replaying the offline queue is safe. The runner generates `runId`, so events can be queued before the hub knows the run.
4. **`workflow.toml` gains `plannedPath` and `interruptNodes`.** `get_graph()` cannot see `interrupt()` inside a node, and % of plan needs the happy path. Keys are camelCase, like the contracts.
5. **Cache writes are priced as 1-hour cache** (one `cache_write` token type, no 5m/1h split).
6. **Emails are a loose `x@y` pattern.** An unconfigured git reports `dev@MacBook.local`, and strict validation would reject runs at ingest.
7. **API additions** beyond the design table: `POST/DELETE /api/session` (password → cookie), `GET /api/runs`, `GET /api/runs/{id}`, polling `GET /api/runs/{id}/events?after=`, `PUT …/channels/{name}` (rollback), `GET /api/analytics/releases` (version comparison), `GET /api/analytics/outcomes` (Planned human delta, sample data). HUB does not have to implement every endpoint tonight; T12 decides.
8. **Bundle digest = sha256 of the zip bytes.** The zip is built deterministically (sorted paths, fixed timestamp), and `jigworks_contracts.bundle` is the shared implementation for publish (HUB) and verify (LOCAL, T10).
9. **The extension's npm package is named `vscode`** (extension id `jigworks.vscode`), so the `pnpm --filter vscode` used in the docs works.

## 4. What I am unsure about, ordered by severity

1. **The fixture runs are synthetic.** They come from a scripted simulator in `make_fixtures.py`, not from a runner, which doesn't exist yet. They validate and are internally consistent, but the real runner may emit things the simulator didn't anticipate. Mitigation: contracts are permissive where it is cheap (free-form `error.code`, `rateLimitType`).
2. **The contracts are large** (62 schemas, 21 operations). A larger surface frozen tonight means more chances that an agent wants a change at 2 a.m. and blocks itself. The trade-off was deliberate: missing a field blocks a ticket, an unused one costs nothing.
3. **The ownership guard was tested by piping hook JSON, not inside a real Claude Code session** with `JIGWORKS_AGENT` set. The pre-commit hook path was not exercised by a real agent commit either. I will check both in the worktrees (step 4) before you sleep.
4. **The Vercel Git integration preview has not been seen yet.** It triggers on the first push of the branch; I check it right after pushing.
5. **Vercel Sandbox** ran in `vercel-sandbox-default-project`, not `jigworks`. HUB has to create sandboxes from the deployed API with the project OIDC token. Not tried yet.
6. **`dist/` of contracts is not committed.** Hub-web and the extension must run `pnpm --filter contracts build` first; both verify scripts do.
7. **Foundation work touched later-owned paths** (allowed before the split): `apps/hub-api` (health uses the contracts model, which proves Vercel's uv build resolves the workspace package), `clients/vscode/src/test/runTest.ts`, and the T11 ticket.
8. **The allowlist** in `.claude/settings.json` adds `curl`, `jq`, `ls`, `cat`, `mkdir`, `gh pr`, `bash scripts/*` and `bash e2e/*` beyond the list in two-agent-build.md §5. It denies the Read tool on `.env.local` and blocks force pushes and pushes to main.
9. **The toolchain is bleeding edge** (pnpm 12, TypeScript 7, Node 26, Vite 8/rolldown). It all works today; TS 7 already removed `moduleResolution: node10`, which cost one iteration.

## 5. Verify it yourself (≈ 2 min)

```bash
cd ~/Development/jigworks && git log --oneline main..feature/hub-and-vs-code-extension
uv run pytest -q                              # 59 passed
pnpm -r test                                  # contracts 29/29, hub-web 1/1, vscode 1 passing (opens a VS Code window)
uv run python packages/contracts/scripts/generate.py --check
bash scripts/check-ownership.sh hub; echo $?  # 0 with nothing staged
```

## 6. After your approval

Steps 4–5 of your prompt: worktrees `../jigworks-hub` (`agent/hub`) and `../jigworks-local` (`agent/local`) with `JIGWORKS_AGENT` in each `.claude/settings.local.json`, then `docs/kickoff-hub.md` and `docs/kickoff-local.md`. Still on you before the start: `caffeinate -dimsu`, laptop on power, Docker running.
