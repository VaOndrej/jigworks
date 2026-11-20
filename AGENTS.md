# Repository-wide agent instructions

These instructions apply to the whole repository and to every agent working in
it (Claude Code, Codex, subagents, workflow nodes run by the Jigworks runner).

`docs/design.md` is the canonical design (v0.7). `docs/mockups/jigworks-ui.html`
is the visual spec for the hub and the extension. Read the relevant section before
you change anything. Do not re-open decisions recorded there; if something is
ambiguous, ask the human instead of guessing. `docs/plan.md` is the ticket plan;
the tickets themselves are Markdown files in `tickets/` (conventions in
`tickets/README.md`). Work on one ticket at a time and keep its Status and
Evidence up to date.

Everything lives in this one repo (hub, runner, VS Code extension, sample-repo,
demo) so it can be shared as a single repo. Do not split anything out.

## Mandatory: English only

Everything committed to this repo is in English: docs, code, identifiers,
comments, prompts, test names, commit messages, issue titles and bodies, PR
descriptions. External reviewers read the whole repo. If you find non-English
content, translate it in the same change.

## Mandatory: the repo is public

Every pushed commit, on every branch, is readable by anyone, including its
history. Secrets live only in ignored `.env*` files (template: `.env.example`),
in Vercel environment variables, or in Claude Code's own auth. Before every
push, scan the whole history and push only on `no leaks found`:

```
gitleaks git --log-opts="--all" --redact .
```

If it finds a real secret, stop and tell the human: the secret must be revoked
and rotated, because rewriting history does not un-leak it. The local Docker
credentials `jigworks:jigworks@localhost` are intentional dev defaults.
Recorded `claude -p` transcripts are committed only in their scrubbed form
(home path, email, org id and signatures replaced; see
`scripts/spike-claude.sh --record`).

## Repo map

```
jigworks/
  AGENTS.md            # this file
  CLAUDE.md            # pointer to AGENTS.md
  LICENSE.md           # FSL-1.1-ALv2
  BUILD_LOG.md         # human vs agent time, delegated/reviewed/hand-written/what went wrong
  vercel.json          # Services: hub-web + hub-api
  apps/hub-api/        # FastAPI (Python)
  apps/hub-web/        # Vite + React + React Flow (TS)
  clients/vscode/      # VS Code extension; later jetbrains/, hr-portal/
  runner/              # local runner + CLI agent adapters (Python)
  packages/contracts/  # event and API schema → TS + Python types
  workflows/feature-development/
  sample-repo/         # synthetic order-handling service with invariants
  demo/                # later
  e2e/                 # Playwright
  docs/                # design.md, plan.md, two-agent-build.md, mockups/
  tickets/             # one Markdown file per ticket
```

Folders that do not exist yet are planned, not missing. Create them only as part
of the ticket that owns them.

## Toolchain

- **TypeScript:** pnpm workspace (`pnpm-workspace.yaml` at the root). Use
  `pnpm`, never `npm` or `yarn`. Add dependencies with
  `pnpm --filter <package> add <dep>`.
- **Python:** uv workspace (root `pyproject.toml`). Use `uv run`, `uv add`,
  `uv sync`; never `pip install` into a global environment. The runner uses one
  venv per release digest (design.md §3, §6).
- **Agent CLI:** `claude -p --output-format stream-json`. Auth belongs to Claude
  Code, not to Jigworks; never commit credentials or API keys.
- **Data:** public or synthetic only. `sample-repo/` is synthetic by design.

## Mandatory: proof before "done"

Work is not reported as done without evidence attached to the summary.

- **Logic change** → paste the test command and its output. "Tests should pass"
  is not evidence. Invariants in `sample-repo/` are guarded by property tests;
  a change there must show them running.
- **Visual change** (hub-web, the extension webview) → verify with Playwright at
  **1440 px** (desktop) and attach the screenshot. Mobile layouts are out of
  scope for the prototype (decided 19 Nov 2026); do not spend time on them.
  Save screenshots under `e2e/screenshots/`, `e2e/hub/screenshots/` or
  `e2e/local/screenshots/` (or attach them to the PR), not to the repo root.
- **Data / infra change** → a dry-run output or three real records after the
  change.
- If something could not be verified, say so explicitly. Never write "all
  clean" unless it is literally true.

## Mandatory: critical self-audit after implementation

After every non-empty change, before handing it over for review, ask yourself
and answer honestly:

> "Is there anything I hacked, cut short, worked around, or left unsaid?"

List real shortcuts, tech debt, unfinished parts and unverified assumptions,
ordered by severity. Distinguish "done and verified", "done but unverified" and
"deliberate trade-off". A green test run does not mean the intent was met.

## Mandatory: build log

Every work session appends an entry to `BUILD_LOG.md` in the same change set,
and updates the summary table. The entry records:

- **Time:** human time vs agent time, as two separate numbers.
- **What I delegated** to agents.
- **What I reviewed / decided myself.**
- **What I wrote by hand.**
- **What went wrong / changed course.**

Be honest: the build log is part of the deliverable and is read by reviewers.

## Commits

- Small, focused commits; one logical change per commit.
- English, imperative subject line (≤ 72 chars), optional body explaining why.
- Reference the ticket ID (`Refs T05`).
- Never commit secrets, `.env` files, `.vercel/` or OS files (`.DS_Store`).
- Never push to `main` and never force-push. Pushing is allowed only to the
  feature branch of the parallel build (below); the human merges into `main`.

## Parallel build (two agents)

The prototype is built by two agents in parallel. Rationale and the overnight
procedure: `docs/two-agent-build.md`.

- **Branch:** both agents push to `feature/hub-and-vs-code-extension`. Each
  works in its own worktree on a local branch (`agent/hub`, `agent/local`) and
  pushes with `git pull --rebase origin feature/hub-and-vs-code-extension &&
  git push origin HEAD:feature/hub-and-vs-code-extension`.
- **Who you are:** read `JIGWORKS_AGENT` (`hub` or `local`). If it is not set,
  you are not part of the parallel build: do not push.
- **Ownership:** write only your own paths and leave the other agent's files
  alone.
  - `hub`: `apps/hub-api/`, `apps/hub-web/`, `vercel.json`, `e2e/hub/`,
    tickets T11–T13, `build-log/agent-hub.md`.
  - `local`: `runner/`, `workflows/`, `sample-repo/`, `clients/vscode/`,
    `e2e/local/`, `e2e/integration/`, tickets T03–T10 and T14–T17,
    `build-log/agent-local.md`.
  - Run `scripts/check-ownership.sh $JIGWORKS_AGENT` before every commit.
- **Contracts are frozen** after T02. If you need a change in
  `packages/contracts/`, do not make it: write the proposal in your build log,
  mark the ticket `blocked`, move on. Exception: `hub` regenerates
  `packages/contracts/openapi.json` from FastAPI.
- **Lockfiles:** on a rebase conflict in `pnpm-lock.yaml` or `uv.lock`, take
  the remote version, re-run `pnpm install` / `uv lock`, commit.
- **Build log:** during the parallel build, write to your own
  `build-log/agent-<name>.md`, not to `BUILD_LOG.md`; the human merges them.
- **One ticket at a time.** Prove it with your verify command
  (`pnpm verify:hub` or `pnpm verify:local`), paste the output into the
  ticket's Evidence, tick the criteria, commit, push. After three failed
  verification attempts mark the ticket `blocked` with the reason and take the
  next independent ticket.
- **Missing the other side:** test against fixtures in
  `packages/contracts/fixtures/` or a mock generated from `openapi.json`;
  never edit the other agent's code to unblock yourself.
