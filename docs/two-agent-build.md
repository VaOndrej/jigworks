# Two-agent overnight build

- **Status:** agreed rules are mirrored in `AGENTS.md` ("Parallel build"); this file keeps the rationale, the overnight procedure and the open points.
- **Goal:** two AI agents build the prototype end to end overnight, unattended, one for the Vercel hub (**HUB**) and one for the local side (**LOCAL**: runner, workflows, sample-repo, VS Code extension). Each proves its own work. In the morning the human reviews one PR into `main` and merges it.

## 1. Branch and push model

- One shared branch: **`feature/hub-and-vs-code-extension`**. Nothing is pushed to `main`; the human merges the PR in the morning.
- Git does not allow the same branch in two worktrees, so each agent works in its own worktree on a local branch and pushes to the shared remote branch:
  - HUB: `../jigworks-hub`, local branch `agent/hub`
  - LOCAL: `../jigworks-local`, local branch `agent/local`
  - push: `git pull --rebase origin feature/hub-and-vs-code-extension && git push origin HEAD:feature/hub-and-vs-code-extension`
- Every push triggers a Vercel preview deploy through the GitHub integration, which HUB uses for its preview tests.
- Never `--force`, never push to `main`, never rewrite pushed history.

## 2. Ownership

| | **HUB** | **LOCAL** |
|---|---|---|
| Writes | `apps/hub-api/`, `apps/hub-web/`, `vercel.json`, `e2e/hub/` | `runner/`, `workflows/`, `sample-repo/`, `clients/vscode/`, `e2e/local/`, `e2e/integration/` |
| Tickets | T12, T13, agent part of T11 | T03–T10, T14, T15, T16, T17 |
| Log | `build-log/agent-hub.md` | `build-log/agent-local.md` |

- **Foundation (T00–T02) is built before the split** and reviewed by the human; after that, `packages/contracts/` is frozen. If an agent needs a change overnight, it writes the proposal in its log and marks the ticket `blocked`; neither agent edits contracts. Exception: HUB regenerates `packages/contracts/openapi.json` from FastAPI.
- The hub side of event ingest is part of T12 (`POST /api/runs/{id}/events`); T14 is only the runner side. The workloads do not have to be equal.
- **Shared files:**
  - `pnpm-lock.yaml`, `uv.lock`: on a rebase conflict, take the remote version, re-run `pnpm install` / `uv lock`, commit.
  - Ticket files: each agent edits only its own tickets (status, checkboxes, evidence).
  - Nobody edits `BUILD_LOG.md` overnight; the human folds the two agent logs into it in the morning.
- **Enforcement:**
  - `scripts/check-ownership.sh <hub|local>` runs before every commit.
  - A Claude Code `PreToolUse` hook blocks Edit/Write outside the agent's paths (agent from `JIGWORKS_AGENT`).
  - A git `pre-push` hook blocks pushes to `main` and force pushes.

## 3. The seam: contracts and recorded runs

- `packages/contracts/`: schemas (`RunEvent`, `UsageRecord`, `AuditRecord`, API shapes) → generated TS + Python types.
- `packages/contracts/fixtures/runs/*.jsonl`: recorded runs (from T00, later T06). HUB seeds Runs & analytics with them; LOCAL replays them in the extension without spending tokens.
- Until a preview deploy of the hub exists, LOCAL tests T14/T15 against a mock server generated from `openapi.json`.

## 4. Self-testing

One entry point per side; its output is pasted into the ticket's Evidence.

**LOCAL — `pnpm verify:local`**
- `uv run pytest runner workflows sample-repo`: fake adapter, recorded fixtures. Includes the property tests, the planted-secret gate test and the kill-and-resume test.
- `pnpm --filter vscode test`: `@vscode/test-electron` drives the real extension headless: two sessions in parallel, events, request changes, approve.
- `pnpm --filter vscode test:ui`: the webview runs standalone with recorded runs; Playwright screenshots at 390 px and 1440 px → `e2e/local/screenshots/`.
- `JIGWORKS_LIVE=1 uv run pytest -m live`: one real `claude -p` run on `sample-repo`, plus the extension's login preflight. Uses the Max subscription.

**HUB — `pnpm verify:hub`**
- `docker compose up -d db` and `uv run pytest apps/hub-api` against local Postgres.
- `vercel dev` + Playwright on localhost: the three tabs at 390 px and 1440 px → `e2e/hub/screenshots/`.
- After a push: the same Playwright suite against the branch preview URL, through `vercel curl` or a protection-bypass header for the protected deploy.

**Integration — `pnpm verify:e2e`** (LOCAL, last): publish in the hub preview → the extension syncs `stable` → fake-adapter run → events appear in Runs & analytics.

## 5. Overnight loop

`scripts/overnight.sh <hub|local>` keeps an agent working until its tickets are done or blocked:

1. `git pull --rebase` the shared branch.
2. Start a **fresh** `claude -p` session with `prompts/overnight-<agent>.md`: pick the next ticket owned by this agent with status `todo` whose dependencies are `done`; implement it; run the verify command; tick the criteria; paste the evidence; commit; push.
3. One ticket per session, so the context stays small and the state lives in the ticket files and git, not in the agent's memory.
4. A ticket that fails verification three times becomes `blocked` with the reason, and the loop moves to the next independent ticket.
5. If the subscription's usage limit is reached, the loop waits and retries instead of exiting.
6. When nothing is left, the agent writes its summary to its log. The last agent to finish opens a **draft PR** `feature/hub-and-vs-code-extension → main` with a per-ticket table: status, evidence and blocked reasons.

## 6. Before the human goes to sleep

1. Foundation T00–T02 done and reviewed (≈ 10 min).
2. T11 dashboard steps done: Neon, Blob, Sandbox; `vercel link`; env pulled.
3. `claude`, `gh` and `vercel` logged in; Docker running; laptop on power with sleep disabled.
4. Start both loops; after 10 minutes check that both have pushed their first commit.

## 7. Decisions taken (19 Nov 2026)

1. Contracts are frozen after T02; changes only with the human's approval.
2. HUB owns the hub side of event ingest (in T12); LOCAL owns the runner side (T14), T15 and the integration tests. Workloads need not be equal.
3. Live `claude -p` runs use the human's Max subscription: no per-dollar bill, the limit is the subscription's usage window. Live runs stay opt-in (`JIGWORKS_LIVE=1`). The extension verifies it uses the logged-in Claude Code (preflight in T08, check found in T00).
4. Local Postgres for HUB runs in Docker.
5. Both agents push to `feature/hub-and-vs-code-extension`, never to `main`; each pushes only its own files. Pushes produce Vercel preview deploys.
6. The human merges the PR into `main` in the morning.

7. The foundation (T00–T02) is built this evening and reviewed by the human before the overnight start.

## 8. What each agent builds overnight

Visual spec for both: [`docs/mockups/jigworks-ui.html`](mockups/jigworks-ui.html) (open it in a browser). Behaviour spec: `docs/design.md` v0.7 and the tickets.

### Foundation, this evening (one agent, human reviews ≈ 10 min)

| Ticket | Result the night depends on |
|---|---|
| T00 | Facts about `claude -p` stream-json, recorded fixtures, the login check, how usage limits show up |
| T01 | pnpm + uv workspaces, folder skeleton, `vercel.json`, `docker-compose.yml` (Postgres), hooks, `scripts/check-ownership.sh`, `scripts/overnight.sh`, `prompts/overnight-*.md`, and a **toolchain smoke test** (below) |
| T02 | Frozen contracts: schemas, generated types, `openapi` shapes, and fixtures: recorded runs, a sample workflow bundle (`.zip` + digest) and its `get_graph()` JSON |

### HUB (Vercel)

| Ticket | Builds | Done when |
|---|---|---|
| T11 (agent part) | `vercel env pull`, health endpoint, first preview | preview `/api/health` returns `{"ok":true}` |
| T12 | FastAPI: workflows, draft, validate (Sandbox), publish (bundle → Blob, digest), releases, channels, bundle download, runs + events ingest, usage analytics with a price table; seeded from contract fixtures | `pytest` green on Docker Postgres; curl transcript against the preview |
| T13 | React: **Workflows** (overview, editor with Code/Graph, new file/folder, GitHub bar as Planned), **Runs & analytics** (numbers, cost chart, outcomes as Planned, version comparison, runs, run detail), **Non-coding teams** text tab | Playwright at 390 + 1440 px on localhost and on the preview, matching the mockups |

### LOCAL (runner + VS Code)

| Ticket | Builds | Done when |
|---|---|---|
| T03 | `sample-repo`: order handling with invariants + property tests | tests green; `break-invariant.sh` makes them fail |
| T04 | Claude adapter (stream-json, resume, allowedTools, models from the workflow, usage limit handling) | tests on T00 fixtures |
| T05 | `feature-development` workflow incl. request changes, security scan in the gate, `first_result_commit` | fake-adapter tests for every path |
| T06 | Runner CLI: worktrees, checkpoints, resume, parallel runs, progress %, `jigworks graph`, audit log | tests + one live run with a fix loop |
| T07 | Evals (3–5 tasks) | results file committed |
| T17 | `bugfix-with-repro` workflow + synthetic P&L bug | fake-adapter tests |
| T08 | Extension bridge: several runner processes, login preflight | `@vscode/test-electron` with two runs |
| T09 | Sidebar (workflows, sessions, Review badge), new-session prompt, tabs | standalone webview screenshots 390 + 1440 px |
| T16 | Run view: graph with NOW marker, % of plan, activity / agent output, Approve / Request changes / Reject | same |
| T10 | `.zip` import with digest check | valid + tampered zip tests |
| T14, T15 | Runner → hub sync; extension syncs `stable` | against the OpenAPI mock, then the hub preview |
| e2e | publish in hub → sync → run → events in hub | `pnpm verify:e2e` |

### Human (not overnight)

P01 answers to the brief's 9 questions, P02 demo script, P03 backup recording, P04 final build log and README. These are the presentation, which the human owns; the agents only provide the evidence they cite.

## 9. Human checklist before the overnight start

Things only you can do (logins, dashboards, macOS prompts), checked on 19 Nov 2026:

| Item | State now | What to do |
|---|---|---|
| pnpm | missing | `npm install -g pnpm` (Node 26 no longer ships corepack) |
| Vercel CLI | missing | `npm install -g vercel && vercel login`, then `vercel link` in the repo (project `jigworks`) |
| Docker | installed, **not running** | start Docker Desktop; enable "start at login" |
| Vercel dashboard | — | Neon via Marketplace, Blob store, Sandbox; Deployment Protection → "Protection Bypass for Automation" token |
| Claude Code | installed | `claude -p "say ok"` returns ok on your Max account |
| GitHub | logged in | nothing |
| Playwright Chromium | cached | nothing; the smoke test confirms it |
| Sleep | prevented only while something holds `caffeinate` | `scripts/overnight.sh` wraps itself in `caffeinate -dimsu`; keep the laptop on power |

**Toolchain smoke test (part of T01, run with you watching):** one Playwright headless screenshot, one `@vscode/test-electron` run of a hello-world extension (it downloads its own VS Code; macOS may ask once to allow it), `docker compose up db` + a query, `vercel deploy` of the skeleton, and `claude -p` with the login check. Any macOS permission dialog appears then, while you are there, not at 3 a.m.

## 10. Open points

1. **Identity in the hub:** the MVP has no login. Proposal: the runner sends `git config user.email` as "who started / who approved"; the hub trusts it, and the presentation names this as a known limit.
2. **Live proof overnight (T06):** opening a real PR from the night would push `demo/*` branches to this repo, against the push rule. Proposal: overnight the PR step targets a local bare remote; the real PR happens in the demo rehearsal with you.
3. **Screenshots of the real VS Code window (T09, T16):** taking them unattended needs macOS Screen Recording permission for the terminal. Proposal: the agents prove the UI with standalone Playwright screenshots and `@vscode/test-electron`; you take the real VS Code screenshot in the morning (5 min).
