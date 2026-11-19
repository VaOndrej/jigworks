# Jigworks — joint brainstorming and architecture design

- **Version:** 0.6 (narrowed MVP + prototype scope for the case study)
- **Last updated:** 19 Nov 2026
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

1. **Web Hub** (React + TypeScript, Vite): workflows are written as **normal Python code** directly in the web; the graph is **only a read-only visualization** via LangGraph `get_graph()` → React Flow (with running nodes highlighted). Versioning, publishing, run overview, audit log and cost. A text tab "HR department".
2. **VS Code extension** (TypeScript + React Webview): pick a published workflow, prompt, run, live step progress, Approve/Reject button (human-in-the-loop). Through a local Python runner it executes the LangGraph graph, which calls `claude -p` (other CLIs later).
3. **Hub API** (Python + FastAPI + PostgreSQL) on Vercel: workflow drafts and releases, distribution to the extension, ingest of run events, usage/cost analytics.

### Prototype scope (case study, in build order)

Each step must be demo-able on its own; if we don't make it to 3, the demo stands on 1 + 2 and the Hub appears in the presentation as "what I cut".

1. **Runner + `feature-development` workflow (core)**
   - `plan → tests from the spec (different agent) → implement → independent review → gate → human approval (interrupt) → PR`
   - Sample repo: a small **synthetic order-handling service with invariants** guarded by property tests (the answer to the senior engineer: "agents silently break invariants").
   - Audit log: who started it, workflow version (digest), model, changed files, tokens, cost.
2. **VS Code extension:** workflow picker, prompt, live steps, Approve/Reject.
3. **Hub on Vercel (minimal):** Python editor + publish a version, `get_graph()` graph, list of runs with audit log and cost, HR text tab.

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
        audit | cost | HR tab                     │ (Vercel Services)
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

## 5. Web Hub: workflow as Python

- A workflow is written as standard Python LangGraph (`StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`, `interrupt`).
- The graph is displayed **read-only**: the code is compiled in an isolated environment, `get_graph()` → JSON → React Flow. No roundtrip, no silent rewriting of the code.
- AI edits: the proposed change is shown as a diff; before saving, syntax/import/compile checks run in isolation.

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

- Pick the workspace, workflow (`feature-development@1.3.0`), agent/model.
- Prompt + optional attachments from the workspace.
- Start / stop / resume; live steps, tool calls, tokens, cost, links to the diff and Playwright artifacts.
- **Human-in-the-loop:** LangGraph `interrupt` → Approve/Reject in the extension (plan approval, approval before the PR).
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
START → plan → [human approve plan] → write_tests (different agent, from the spec)
      → implement → review (independent agent)
            review FAIL → fix → review          (iteration limit)
            review PASS → gate (tests + invariant property tests)
            gate FAIL → fix → gate
            gate PASS → [human approve] → open PR → summary → END
```

- Steps are ordinary Python functions via `add_node`; loops via `add_conditional_edges`; LangGraph checkpoints + a git commit per node (hash in the graph state).
- Acceptance: the runner goes through at least one fix loop and the extension shows the progress and the approval.

## 10. Deferred

- HR/legal/ops: only a text tab in the Hub (Ondřej describes the use cases, e.g. automatic CV screening). Future shape: a base workflow + a department variant with added check/approval nodes (subgraphs + `interrupt`) and running outside the IDE.
- Public API, JetBrains, cloud runners, scheduling, marketplace, advanced permissions, billing, server-side CI enforcement.

## 11. Open questions

1. Checkpoint + git snapshot: recovery after an IDE restart without a duplicate side effect.
2. Per-release declaration of agent permissions (`--allowedTools`, network, write) and showing it before installation.
3. Comparing workflow versions from analytics (cost, fixes, success rate).
4. Granularity of `stream-json` telemetry — verify in spike B.
5. Pro account billing for `claude -p` — verify the current terms.

## 12. Repo structure (plan)

```
jigworks/
  AGENTS.md            # agent instructions; mandatory Playwright check of visuals (390 px + 1440 px)
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
