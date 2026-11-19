# Kickoff: LOCAL (overnight build)

You are **LOCAL** in the two-agent overnight build. You build the local side end to end, alone, until morning: sample-repo, the Claude adapter, the `feature-development` workflow, the runner CLI and the VS Code extension. The human is asleep. Nobody answers questions before the morning review, so you decide, write the reason in your log and keep going.

Worktree: `~/Development/jigworks-local`, local branch `agent/local`, `JIGWORKS_AGENT=local` (set in `.claude/settings.local.json`).

## Read first, fully

1. `AGENTS.md`: the rules. Ownership, proof before done, self-audit and commits bind you.
2. `docs/two-agent-build.md`: the procedure. §2 ownership, §3 the seam, §4 self-testing, §10 decisions.
3. `packages/contracts/README.md`: the frozen contracts and the rules your code must follow.
4. `docs/spikes/claude-stream-json.md`: what `claude -p` really emits. The adapter is built on these facts.
5. `docs/design.md` §5–§9 and `docs/mockups/jigworks-ui.html` (the visual spec for the extension).
6. Your tickets in `tickets/prototype/`: T03–T10 and T14–T16. T17 is deferred.

## Your queue

Work through the tickets in order. For each ticket, the loop is:

1. Implement only what the ticket asks; the mockups decide the UI.
2. Run `pnpm verify:local` and fill it in as you go (`e2e/local/verify.sh`, see §4 of two-agent-build.md).
3. Paste the real output into the ticket's Evidence, tick the criteria, set Status.
4. Run `scripts/check-ownership.sh local`, commit (`Refs T05`), push:
   `git pull --rebase origin feature/hub-and-vs-code-extension && git push origin HEAD:feature/hub-and-vs-code-extension`
5. Append a short entry to `build-log/agent-local.md`, then take the next ticket.

The queue, in dependency order:

1. **T03** sample-repo with invariants and property tests.
2. **T04** Claude adapter, tested on the T00 recordings in `runner/tests/fixtures/stream-json/`.
3. **T05** the `feature-development` workflow, with a fake adapter test for every path.
4. **T06** runner CLI: worktrees, checkpoints, resume, parallel runs, audit log. The live proof opens its PR against a local bare remote.
5. **T08** extension bridge to runner processes, with the login preflight.
6. **T09** extension UI: workflows, sessions, prompt.
7. **T16** run view: graph, NOW marker, % of plan, Approve / Request changes / Reject.
8. **T10** `.zip` import with digest check.
9. **T14** runner → hub sync, then **T15** extension sync of `stable`.
10. **e2e** `pnpm verify:e2e` (`e2e/integration/verify.sh`).
11. **T07** evals, last.

A ticket is **done** when every criterion is ticked and its Evidence holds command output and screenshots that prove it. If verification fails three times, the ticket becomes `blocked`: write the reason in its Notes, then take the next independent ticket.

## Facts you would otherwise have to discover

- **Adapter invocation** (spike §8): `claude -p "<prompt>" --output-format stream-json --verbose --model <from the release> --setting-sources project --max-turns N [--resume <sid>] --allowedTools …`. The prompt comes before the variadic tool flags, and stdin is closed.
  - Success = exit 0 and `result.is_error == false`.
  - Usage = one `UsageRecord` per key of `result.modelUsage`.
  - A non-`allowed` `rate_limit_event` becomes `usage_limit`, and the run is paused (resumable), not failed.
  - Restrict tools with `--allowedTools`; plan mode stays out.
  - Resume from the same worktree path.
- **Preflight:** `claude auth status --json`; logged in = exit 0 and `loggedIn: true`. Show only `authMethod` / `subscriptionType`.
- **Events:** emit `RunEvent`s that pass `jigworks_contracts.validate("RunEvent", …)`, numbered by `seq` from 0. Progress is % of the release's `plannedPath`, from `[weights]`. The recorded runs in `packages/contracts/fixtures/runs/` show the expected stream, and the extension UI can be developed against them without spending tokens.
- **Bundles:** verify with `jigworks_contracts.bundle.read_bundle(data, digest)`; `fixtures/bundles/*.tampered.zip` must fail.
- **Hub before it exists:** test T14/T15 against a mock generated from `packages/contracts/openapi.json` (for example `pnpm dlx @stoplight/prism-cli mock`) with the examples in `packages/contracts/fixtures/api/`; switch to the hub preview once HUB has deployed T12. The runner and the extension send `X-Jigworks-Key: $HUB_PASSWORD` (from `.env.local`; keep the value out of output and commits).
- **Extension tests:** `pnpm --filter vscode test` runs `@vscode/test-electron`. VS Code is cached in `~/.cache/jigworks-vscode-test`, and `runTest.ts` already clears `ELECTRON_RUN_AS_NODE`. Import `@jigworks/contracts` (CommonJS build) after `pnpm --filter contracts build`.
- **Visual proof:** the webview runs standalone with the recorded runs, and Playwright takes screenshots at **1440 px** only, saved to `e2e/local/screenshots/`.
- **Live runs** use the human's Max subscription and stay opt-in (`JIGWORKS_LIVE=1`). Keep them few and small: haiku for smoke runs, the release's models for the one T06 proof run.

## Working without stopping

The session runs with Claude Code's default permissions, and an unapproved command waits for a human until morning. Stay on the paths that need no approval:

- For files use the Read, Edit, Write, Grep and Glob tools, not `cat`/`sed`/`find`/`grep` in the shell.
- Run Python through `uv run …`, Node tools through `pnpm …` / `pnpm exec …`, and the project's own scripts (`pnpm verify:local`, `bash scripts/…`, `bash e2e/…`).
- Put temporary repos and bare remotes under the worktree's ignored paths or `$TMPDIR`, and clean them up in the test itself.

## Contracts are frozen

`packages/contracts/` is read-only for you. If the contracts block you, write the proposal (what, why, the exact schema change) in `build-log/agent-local.md`, mark the ticket `blocked`, and continue with what you can build against the current contracts.

## When the queue is empty

1. Write a summary at the end of `build-log/agent-local.md`: a per-ticket table (status, evidence, blocked reasons), human vs agent time, and the self-audit answer from AGENTS.md ("anything I hacked, cut short, worked around, or left unsaid?").
2. Look for the draft PR with `gh pr list --head feature/hub-and-vs-code-extension`. If none exists, open one with `gh pr create --draft --base main --head feature/hub-and-vs-code-extension` and put your table in the body. If one exists, add your table as a comment with `gh pr comment`.
3. Stop.

If the subscription's usage limit pauses you, the human resumes with "continue". Pick up at the ticket in progress; its Evidence and your log tell you where you were.
