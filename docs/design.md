# Jigworks — joint brainstorming and architecture design

- **Version:** 0.9 (project-agnostic workflow, latest models)
- **Last updated:** 20 Nov 2026
- **Status:** working design, not a finished technical specification
- **Context:** take-home case study "Design Your Software Factory" (AI Engineer, FTMO & OANDA); recommended time ~4 h, live demo + backup recording, repo incl. agent instructions, prompts, tests, evals and build log; public/synthetic data only.
- **Primary use:** AI-first software development (target audience = developers)
- **Future use:** other team processes (HR, legal, ops) — in the MVP only as a pointer to the direction
- **License:** FSL-1.1-ALv2 (see `LICENSE.md`)

**Project principle:** We are building a web hub for writing, versioning and distributing existing LangGraph workflows to VS Code, and a local runner that executes them. We are not building our own replacement for LangGraph. The single source of truth is the published version of the executable Python workflow.

**Name:** "Software Factory" collided with the company Factory (factory.ai, AI coding agents). Working name **Jigworks** — a *jig* is a manufacturing fixture that guides the tool so that every cut is the same; a workflow does the same with an agent.

---

## 1. Scope

### Three product parts

1. **Web Hub** (React + TypeScript, Vite): workflows are written as **normal Python code** directly in the web; the graph is **only a read-only visualization** via LangGraph `get_graph()` → React Flow (with running nodes highlighted). Versioning, publishing, and one "Runs & analytics" tab (runs, audit log, cost, version comparison). A text tab "Non-coding teams".
2. **VS Code extension** (TypeScript + React Webview): pick a published workflow, prompt, run, live step progress, Approve/Reject button (human-in-the-loop); several sessions in parallel, each with its own workflow and worktree. Through a local Python runner it executes the LangGraph graph, which calls `claude -p` (other CLIs later).
3. **Hub API** (Python + FastAPI + PostgreSQL) on Vercel: workflow drafts and releases, distribution to the extension, ingest of run events, usage/cost analytics.

### Prototype scope (case study, in build order)

Each step must be demo-able on its own; if we don't make it to 3, the demo stands on 1 + 2 and the Hub appears in the presentation as "what I cut".

1. **Runner + `feature-development` workflow (core)**
   - `plan → tests from the spec (different agent) → implement → independent review → gate → human approval (interrupt) → PR`
   - Sample repo: a small **synthetic order-handling service with invariants** guarded by property tests (the answer to the senior engineer: "agents silently break invariants").
   - Audit log: who started it, workflow version (digest), model, changed files, tokens, cost.
2. **VS Code extension:** workflow picker, prompt, live steps, Approve/Reject.
3. **Hub on Vercel (minimal):** Python editor + publish a version, `get_graph()` graph, "Runs & analytics" tab with audit log and cost, "Non-coding teams" text tab.

### Explicitly out

- Visual graph editing (read-only `get_graph()` only), custom graph engine, DSL, node type catalog.
- Server-side CI/CD gates, automatic production deploy, governance across all tools.
- HR/legal functionality (text tab only), public API, marketplace, JetBrains, cloud runners.
- Integration with an open chat session of the official Claude Code extension.

**Product boundary:** a workflow can require review/tests/approval and the runner enforces that within a controlled run. We cannot claim to prevent using another tool or bypassing checks at merge time.

## 2. Mapping to the people in the brief

| Who | Problem | Answer in the design |
|---|---|---|
| Senior engineer (trading) | agent silently breaks invariants | tests/invariants are written by a different agent from the spec **before** implementation; property tests as a gate |
| Early adopter | large PRs, tests from the same agent, shallow review | independent review node, gate before the human, small steps |
| Team lead | everyone has their own setup and leaves with it; doesn't know if they are faster | workflows shared and versioned in the Hub; version comparison (cost, number of fixes, success rate) |
| Long-task engineer | agent loses context across sessions | LangGraph checkpoint + git snapshot per node; run state lives outside the agent's context |
| Platform engineer | laptops, personal credentials, no record or cost | audit log of every run, cost analytics, isolation in a git worktree; per-release declaration of agent permissions (proposal) |
| Security & compliance | audit trail, approver ≠ author, authorship | run events = audit trail; `interrupt` = human approval; author = the human who started and approved the run |
| Ops analyst (non-engineer) | shadow IT on a laptop | outside the prototype; a tab in the Hub describing the direction (workflow + department variants, running outside the IDE) |

## 3. Technology

| Layer | Technology | Status |
|---|---|---|
| Web Hub frontend | React + TypeScript (Vite) | Approved |
| Graph | React Flow (`@xyflow/react`), read-only from `get_graph()` | Approved |
| Hub API | Python + FastAPI | Approved |
| Hosting | Vercel, one project `jigworks`, **Vercel Services** (Beta) for web + API | Approved |
| Database | PostgreSQL (Neon via Vercel Marketplace) | Approved |
| Package storage | Vercel Blob | Proposal |
| Isolated validation of workflow code | Vercel Sandbox | Proposal |
| Workflow execution | LangGraph (Python) | Approved |
| Python environment | `uv`, one venv per release digest | Approved |
| IDE client | VS Code extension (TS) + React Webview, installed locally via `.vsix` | Approved |
| Agent | `claude -p --output-format stream-json`; Codex later | Approved |
| Accounts | primarily a company API key; Pro accounts have a separate programmatic credit for `claude -p` (verify at code.claude.com/docs/en/legal-and-compliance) | To verify |
| Rust | do not use | Decided |

Langflow / LangSmith Studio: inspiration only. LangSmith Studio already visualizes and traces the graph, but it is tied to LangSmith (self-hosting only on Enterprise). We differentiate: VS Code + local CLI agents + distribution of versions to the team + department variants.

## 4. Architecture

```
                 WEB HUB (React, Vite)            ┐
        Python editor | get_graph() graph | runs  │ Vercel project "jigworks"
        runs & analytics | non-coding tab         │ (Vercel Services)
                        |                         │
                 HUB API (FastAPI)                │
        Postgres | releases | channels | events   ┘
                        |
              HTTPS REST (+ SSE with reconnect / polling)
                        |
              VS CODE EXTENSION (TS)
        Webview: workflow | prompt | steps | Approve
                        |
                 local process
                        |
              LOCAL RUNNER (Python, uv venv per digest)
        LangGraph graph | checkpoint + git snapshot | audit log
                        |
              CLI AGENT ADAPTERS
        claude -p (stream-json) | Codex later
                        |
              repo | git worktree | tests | Playwright
```

- The Hub owns published versions, assignments and the summary history. It needs no access to the code or to CLI credentials.
- The runner owns execution; it streams events to the extension and to the hub. When the connection drops, it queues locally and syncs after recovery.
- SSE on Vercel functions has a time limit → the client must handle reconnects (or polling).
- **Human delta loop (architecture only, §8):** after a human approves, whatever they change before the code is merged flows back to the Hub as a diff. That closes the loop from a published workflow, through runs and human edits, back to an improved workflow.

## 5. Web Hub: workflow as Python

- A workflow is written as standard Python LangGraph (`StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`, `interrupt`).
- The graph is displayed **read-only**: the code is compiled in an isolated environment, `get_graph()` → JSON → React Flow. No roundtrip, no silent rewriting of the code.
- Before saving, syntax/import/compile checks run in isolation. There is no AI edit box in the hub editor; workflows are edited as code (or in the connected repo).
- The editor has a Code / Graph toggle; switching to Graph compiles the draft in Vercel Sandbox and renders `get_graph()`.
- Files and folders of the package can be created from templates (node function, prompt).
- **GitHub source (shown, not built in the MVP):** a workflow can be connected to a GitHub repo; the editor then works as a richer view on that repo: a push to the repo updates the draft, a save in the editor commits to the repo. In the MVP the package is stored in the Hub.

### Workflow package

```
feature-development/
  graph.py            # StateGraph, entry point
  steps/              # node functions
  prompts/            # phase prompts
  workflow.toml       # name, entrypoint, min runner version, inputs, agent permissions (proposal)
  requirements.lock   # uv lock
  README.md
```

The code of published workflows is never executed in the Hub API process.

**Every workflow agrees its plan with the human before it builds anything.** Request changes at
the plan approval goes back to the planner, which resumes its own agent session, so it remembers
the conversation; the planner may reply with `QUESTIONS:` instead of a plan; approving open
questions sends the planner back to state its assumptions. The planning conversation is passed
on with the approved plan to every agent after it. Planning rounds are limited (5 in
`feature-development`). Agreeing on the plan is not a follow-up prompt: it comes before the first
result, the baseline of the human delta (§8).

## 6. Versions and distribution

`Draft → Validate → Publish immutable release (workflowId, version, digest) → Channel (stable/beta) → Sync to extension → Run pinned version`

- **Distribution via Hub API:**
  - `GET /api/workflows/{id}/channels/stable` → release id + digest
  - `GET /api/releases/{id}/bundle` → `.zip`
  - the extension verifies the digest, unpacks into its own cache, `uv` venv per digest
- **Fallback:** an "Import workflow from file" command in VS Code (the same `.zip`).
- Rollback = pointing the channel to an older release. A running task never changes to a new version.
- A new version is offered, but it does not run without an explicit mode set by the team.

## 7. VS Code extension

- Sidebar: **Workflows** (the selected one is active for a new session) and **Sessions** (every running or waiting session with its current node and progress).
- A new session opens with the prompt in the middle of the editor area; each session is its own tab and runs in its own git worktree, so an engineer can start a customer bug fix while a feature run continues.
- Run view: the read-only graph with the current node highlighted, and progress as **% of the plan** (weight of finished nodes / weight of the planned path; weights from past runs of the same release, fallback to `workflow.toml`). Not a time estimate; a fix loop never moves it backwards. The graph JSON comes from the local runner, which executes the workflow code anyway.
- Pick the workspace and the workflow (`feature-development@1.3.0`). **Models are not picked in VS Code:** the workflow release sets them (`[models]` in `workflow.toml`, optionally per node), so every run of a release uses the same models.
- Session states are colour-coded: done and approved steps green, the current step blue with a "NOW" marker, steps that need the human amber. A session waiting for review shows a "Review" badge instead of its %.
- Optional live **agent output**: the raw `stream-json` text and tool calls of the current node, for people who like to watch.
- Prompt + optional attachments from the workspace.
- Start / stop / resume; live steps, tool calls, tokens, cost, links to the diff and Playwright artifacts.
- **Human-in-the-loop:** LangGraph `interrupt` → Approve / Request changes / Reject in the extension (plan approval, review before the PR). Request changes sends the human's comment back to the agent as a follow-up prompt (fix → gate → review again), like a PR review.
- Parallel runs in separate git worktrees.
- Remote SSH / Dev Containers: the runner and the CLI must run next to the workspace.

### Agent interface

- `run(prompt, cwd, options) → result + events`
- Claude adapter: `claude -p --output-format stream-json`, `--resume` for a follow-up session, permissions via `--allowedTools` / `--permission-mode`. Auth belongs to Claude Code, not to Jigworks.

## 8. Hub API, analytics, audit

| Endpoint | Use |
|---|---|
| `GET /api/workflows` | list of workflows |
| `GET/PUT /api/workflows/{id}/draft` | draft |
| `POST /api/workflows/{id}/validate` | validation in isolation |
| `POST /api/workflows/{id}/publish` | new release |
| `GET /api/workflows/{id}/releases` | versions |
| `GET /api/workflows/{id}/channels/{name}` | channel resolution |
| `GET /api/releases/{id}/bundle` | download the `.zip` |
| `POST /api/runs` | register a run + pinned release |
| `POST /api/runs/{id}/events` | event ingest |
| `GET /api/runs/{id}/events/stream` | SSE |
| `GET /api/analytics/usage` | reporting |

### Analytics (own, without LangSmith/Langfuse)

- Source: the final `stream-json` message (`usage`, `total_cost_usd`) — verify the exact fields in spike B.
- Store **raw tokens per call**: `runId, node, attempt, model, adapter, input, output, cache_write, cache_read`.
- **Price list as a table with validity:** `model, token_type, price_per_mtok, valid_from`; cost is computed at read time.
- Price cache tokens separately (they make up the majority in agentic loops).
- For Pro accounts, label it "API equivalent". `total_cost_usd` from the CLI only as a cross-check.
- The adapter normalizes into the same fields (Codex reports differently).

### Human delta and supervised workflow learning (architecture only, not in the prototype)

The baseline is the **first result of a session**: the runner records `first_result_commit`, the tree presented at the first review (`approve_pr`). Every later correction is measured against it:

- a **follow-up prompt** (Request changes) in the same session, and
- a **hand edit** before merge (primary capture: a PR-merge webhook to the Hub; fallback: the extension on local push).

The Hub stores a **human delta** per session: `runId, release, digest, outcome (worked_first_time | corrected_by_prompt | edited_by_hand | rejected), follow_up_prompts, files, lines_added, lines_removed, diff` (diff in Blob, after a secret scan). A session with no follow-up prompt and no hand edit counts as the workflow working first time.

Uses:

- **Analytics:** share of sessions that worked first time vs corrected by prompt vs edited by hand vs rejected, edit size, where humans edit most (files, node that produced the code), per release. This is the most direct quality signal beyond "it looks right" and feeds version comparison (§11.3).
- **Supervised learning:** the Hub groups similar deltas per workflow; an agent proposes a change to prompts or steps as a **draft release diff**; the workflow owner reviews it, publishes to `beta`, and promotes it only if the metrics improve. Nothing is published automatically.

Constraints: deltas contain company code, so they stay in the company Hub under the same access rules; collection is opt-in per team.

### Access

The Hub is a public URL in the prototype, so web and API sit behind one shared password (`HUB_PASSWORD`, env only). Engineers never log in: the runner reports `git config user.email` as the author and approver. Real SSO is out of scope.

### Audit

Every run: who started it, release + digest, model, steps, changed files (git snapshot per node), gate results, who approved and when, tokens and cost.

### Run events (example)

```json
{
  "runId": "run_123",
  "release": "feature-development@1.3.0",
  "node": "review",
  "status": "running",
  "attempt": 2,
  "at": "2026-11-19T15:00:00Z"
}
```

## 9. First workflow `feature-development`

```
START → plan ⇄ [human approve plan]   (questions / request changes → plan again, same session)
      → write_tests (different agent, from the plan and the planning conversation)
      → implement → review (independent agent; after a fix it re-checks the earlier findings by ID)
            review FAIL → fix → review          (on its own while the open findings shrink)
            review PASS → gate (the repo's own tests + property tests where configured)
            gate FAIL → fix → gate
            no progress in 2 fixes, the fix cap (8), or a reviewer QUESTION → [human: fixes]
                  continue (+3 fixes, optional note or answers) → fix · stop → END
            gate PASS → [human review] → open PR → summary → END
            review: request changes → fix → gate → [human review]   (follow-up prompt, counted in the human delta)
```

- Steps are ordinary Python functions via `add_node`; loops via `add_conditional_edges`; LangGraph checkpoints + a git commit per node (hash in the graph state).
- **A fix loop never just fails** (1.7.0, T22): the human sees every round (what the review or gate found, what the fixer changed, the trend of open problems) and decides. Runs of older releases that ended at the fix loop limit continue from their checkpoint with `jigworks resume <runId> --more-fixes N`, or Continue fixing in the extension.
- Acceptance: the runner goes through at least one fix loop and the extension shows the progress and the approval.
- **Project-agnostic** (v0.9): the repo is the one the run starts in, and the scope is the folder it starts from; the prompt narrows the work, the approved plan names the files. The gate runs the repo's own tests, from `.jigworks/gate.toml` (read from the base commit) or detected (pytest, package.json `test`, go, cargo). `sample-repo/` is one such repo with its own gate config, not a special case.
- **Models:** Opus 5.5 for plan, write_tests and review (review at effort `medium`), Sonnet 5.5 for implement, fix and summary; effort is set per node by the release (`[effort]`), like the models.
- **Skills ship with the release:** a workflow package may contain `plugin/`, a Claude Code plugin with skills; the runner loads it into every agent call (`claude -p --plugin-dir`), so the skills are versioned with the release and covered by its digest. The target repo's project skills and `CLAUDE.md` apply as well (`--setting-sources project`); the personal ones of whoever runs it never do, so a release behaves the same for everyone.
- **Goal:** more consistent and better results than a plain Opus 5.5 session with skills on the same task; to be measured with an A/B eval (open question 7).

## 10. Deferred

- Non-coding teams (HR/legal/ops): only a "Non-coding teams" text tab in the Hub (Ondřej describes the use cases, e.g. automatic CV screening). Future shape: a base workflow + a department variant with added check/approval nodes (subgraphs + `interrupt`) and running outside the IDE.
- Human delta capture and supervised workflow learning (designed in §8, not built).
- Public API, JetBrains, cloud runners, scheduling, marketplace, advanced permissions, billing, server-side CI enforcement.

## 11. Open questions

1. Checkpoint + git snapshot: recovery after an IDE restart without a duplicate side effect.
2. Per-release declaration of agent permissions (`--allowedTools`, network, write) and showing it before installation.
3. Comparing workflow versions from analytics (cost, fixes, success rate).
4. Granularity of `stream-json` telemetry — verify in spike B.
5. Pro account billing for `claude -p` — verify the current terms.
6. Human delta: capture point (PR-merge webhook vs local push), matching squashed or rebased merges to `ai_final_commit`, and retention of stored diffs.
7. A/B evaluation of a workflow release against a plain agent session (or another release) on the same tasks: variants, a simulated human for the planning questions, hidden tests next to an LLM judge, repetitions and budget.

## 12. Repo structure (plan)

```
jigworks/
  AGENTS.md            # agent instructions; mandatory Playwright check of visuals (1440 px)
  CLAUDE.md            # pointer to AGENTS.md
  LICENSE.md           # FSL-1.1-ALv2
  BUILD_LOG.md         # time and what was delegated/reviewed/hand-written/what went wrong
  vercel.json          # Services: hub-web + hub-api
  apps/hub-api/        # FastAPI
  apps/hub-web/        # Vite + React + React Flow
  clients/vscode/      # extension; later jetbrains/, hr-portal/
  runner/              # local runner + adapters
  packages/contracts/  # event and API schema → TS + Python types
  workflows/feature-development/
  sample-repo/         # synthetic order-handling service with invariants
  demo/                # later
  e2e/                 # Playwright
  docs/
```

Tooling: pnpm workspace (TS), uv workspace (Python).

## 13. Decision history

- **v0.9 (20 Nov 2026):** `feature-development` is project-agnostic (§9): repo = where the run starts, gate runs the repo's own tests (`.jigworks/gate.toml` or detection), `sample-repo/` gets its own gate config, the extension's `repoPath` defaults to the workspace root. Models Opus 5.5 / Sonnet 5.5, reasoning effort per node in the release (`[effort]`, contract `WorkflowManifest.effort`). Skills ship with the release as a Claude Code plugin (`plugin/`, `--plugin-dir`); project skills apply, personal ones do not (T19).
- **v0.8 (20 Nov 2026):** the plan is agreed with the human before any code, in every workflow (§5): request changes at the plan re-plans in the planner's session, the planner may ask questions, the planning conversation goes to the later agents, and plan discussion does not count as a follow-up prompt. `feature-development` 1.5.0 (T18).
- **v0.7 (19 Nov 2026):** human delta loop added to the architecture (§4, §8; not built); its baseline is the first result of a session, and follow-up prompts count as corrections like hand edits. Request changes added to the human review. Models are set by the workflow release, not in VS Code. Editor: Code/Graph toggle, new file/folder, GitHub source shown as planned, no AI edit box. Hub tabs: "Runs & analytics" merged into one, the HR tab renamed "Non-coding teams". VS Code extension: parallel sessions, prompt in the middle, run view with graph position and % of plan (§7). Tickets live in `tickets/`.
- **v0.6 (19 Nov 2026):** project named Jigworks, license FSL-1.1-ALv2. Web Hub = writing Python + read-only `get_graph()` graph (visual editing dropped). Distribution via Hub API + `.zip` import fallback. Own analytics (tokens × price list with validity). Hosting on Vercel Services + Neon. Target audience is developers, HR only as a text tab. Governance elements (audit, independent review, human approval) moved into the core because of the case study brief. Prototype scope: runner → extension → minimal Hub.
- **v0.5:** strictly three-part MVP, no policy engine and no DSL, local execution of a Python LangGraph package.
- **v0.4:** FastAPI REST/SSE hub, VS Code TS/React Webview, releases, live usage.
- **v0.3:** React/TS, React Flow, Python/FastAPI + LangGraph; Rust optional.
- **v0.2:** local execution with centrally published workflows.

## 14. Links

- LangGraph Graph API: https://docs.langchain.com/oss/python/langgraph/graph-api
- LangGraph conditional routing: https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- React Flow: https://reactflow.dev/
- VS Code Extension Host: https://code.visualstudio.com/api/advanced-topics/extension-host
- VS Code Webviews: https://code.visualstudio.com/api/extension-guides/webview
- Vercel Services: https://vercel.com/docs/services
- Claude Code legal & compliance: https://code.claude.com/docs/en/legal-and-compliance
- FSL: https://fsl.software
