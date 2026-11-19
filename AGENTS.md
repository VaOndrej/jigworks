# Repository-wide agent instructions

These instructions apply to the whole repository and to every agent working in
it (Claude Code, Codex, subagents, workflow nodes run by the Jigworks runner).

`docs/design.md` is the canonical design (v0.6). Read the relevant section before
you change anything. Do not re-open decisions recorded there; if something is
ambiguous, ask the human instead of guessing. `docs/plan.md` is the ticket plan.

## Mandatory: English only

Everything committed to this repo is in English: docs, code, identifiers,
comments, prompts, test names, commit messages, issue titles and bodies, PR
descriptions. External reviewers read the whole repo. If you find non-English
content, translate it in the same change.

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
  docs/                # design.md, plan.md
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
  **390 px** (mobile) and **1440 px** (desktop) and attach both screenshots.
  Check for horizontal overflow at 390 px. Save screenshots under
  `e2e/screenshots/` or attach them to the PR, not to the repo root.
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
- Reference the GitHub issue when there is one (`Refs #12`, `Closes #12`).
- Never commit secrets, `.env` files, `.vercel/` or OS files (`.DS_Store`).
- Do not push or open PRs unless the human asks for it.
