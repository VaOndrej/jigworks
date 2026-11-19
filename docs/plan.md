# Jigworks — ticket plan

- **Source of truth:** [`docs/design.md`](design.md) v0.6, §1 "Prototype scope". This plan only orders and slices that scope; it adds no new product decisions.
- **Status:** proposal, awaiting approval. GitHub issue links are added once the issues exist.
- **Human time budget:** ~4 h total; 1 h 40 min spent before this plan → **~2 h 20 min left**. Agent time is unlimited and logged separately in [`BUILD_LOG.md`](../BUILD_LOG.md).

Labels: `milestone-0` (foundation), `milestone-1` (runner + workflow + sample-repo), `milestone-2` (VS Code extension), `milestone-3` (minimal hub), `presentation`.
Size: **S** ≤ 1 h agent, **M** 1–3 h agent, **L** > 3 h agent. "Human" = my review/decision time.

## Build order at a glance

```
T0 spike ──► T1 scaffold ──► T2 contracts ─┬─► T3 sample-repo ─┐
                                           └─► T4 claude adapter ┴─► T5 workflow ─► T6 runner CLI ─► T7 evals
                                                                                        │
                                                         T8 extension bridge ◄──────────┘
                                                                │
                                                         T9 webview UI ─► T10 .zip import
──────────────────────────────── CUT LINE ────────────────────────────────
T11 Vercel setup (human) ─► T12 hub-api ─► T13 hub-web ─► T14 runner→hub sync ─► T15 extension sync
Presentation: P1 answers doc · P2 demo script · P3 backup recording · P4 final build log/README
```

## Milestone 0 — foundation

### T0 · Spike: `claude -p --output-format stream-json` · S · critical path
- **Goal:** confirm the facts the runner and analytics depend on, before any code is written (this is "spike B" in design.md §8 and §11.4).
- **Acceptance criteria:**
  - `scripts/spike-claude.sh` reproduces every observation below; `bash scripts/spike-claude.sh` exits 0.
  - Recorded, scrubbed transcripts in `runner/tests/fixtures/stream-json/` (one plain run, one `--resume` run, one denied tool).
  - `docs/spikes/claude-stream-json.md` documents: the exact path and names of the usage fields (input, output, cache write, cache read), `total_cost_usd`, `session_id`, model name; whether usage is reported per message or only in the final `result` event.
  - Confirms `--resume <session_id>` continues the session (second run sees context from the first).
  - Confirms `--allowedTools` blocks a non-listed tool and shows what the denial event looks like; same for `--permission-mode`.
- **Dependencies:** none. **Human:** 5 min to read the findings.

### T1 · Repo scaffolding · S · critical path
- **Goal:** the folder skeleton from design.md §12 with working workspaces.
- **Acceptance criteria:**
  - `pnpm-workspace.yaml` (apps/hub-web, clients/vscode, packages/contracts) and root `package.json`; `pnpm install` succeeds.
  - Root `pyproject.toml` as a uv workspace (runner, apps/hub-api, sample-repo, workflows/feature-development); `uv sync` succeeds.
  - `vercel.json` declares Vercel Services (Beta) `hub-web` and `hub-api` with route prefixes (`/` and `/api`), following https://vercel.com/docs/services.
  - `pnpm -r test` and `uv run pytest` both run (trivially green) — output pasted in the PR.
- **Dependencies:** none (parallel with T0). **Human:** 5 min.

### T2 · `packages/contracts`: run event + audit schema · S · critical path
- **Goal:** one schema for run events (design.md §8) shared by runner (Python) and extension/hub-web (TS).
- **Acceptance criteria:**
  - JSON Schema for `RunEvent`, `UsageRecord` (`runId, node, attempt, model, adapter, input, output, cache_write, cache_read`) and `AuditRecord`.
  - Generated TS types and Python (pydantic) models; `pnpm --filter contracts build` and `uv run pytest packages/contracts` validate the example event from design.md §8.
  - Usage field mapping uses the names confirmed in T0.
- **Dependencies:** T0, T1. **Human:** 5 min.

## Milestone 1 — runner + `feature-development` + sample-repo

### T3 · `sample-repo`: synthetic order-handling service with invariants · M · critical path
- **Goal:** the target repo of the demo; makes "agents silently break invariants" visible.
- **Acceptance criteria:**
  - Small Python service (orders, fills, partial fills, cancels, positions) with documented invariants in `sample-repo/INVARIANTS.md` (e.g. filled ≤ ordered, position = Σ fills, no transition out of a terminal state).
  - Hypothesis property tests per invariant; `uv run pytest sample-repo` is green.
  - `bash sample-repo/scripts/break-invariant.sh` applies a plausible-looking bug and the property tests fail (output pasted).
  - Synthetic data only, no real instruments or accounts.
- **Dependencies:** T1. **Human:** 10 min (review invariants — this is what the senior engineer will poke at).

### T4 · Runner: Claude CLI adapter · M · critical path
- **Goal:** `run(prompt, cwd, options) → result + events` (design.md §7) over `claude -p --output-format stream-json`.
- **Acceptance criteria:**
  - Adapter streams normalized `RunEvent`s and returns a `UsageRecord` per call; supports `--resume`, `--allowedTools`, `--permission-mode`, model.
  - `uv run pytest runner -k adapter` passes against the T0 fixtures (no live call in tests).
  - Cost is computed from a price table with validity (`model, token_type, price_per_mtok, valid_from`), cache tokens priced separately; `total_cost_usd` is only compared as a cross-check.
- **Dependencies:** T0, T2. **Human:** 5 min.

### T5 · Workflow `feature-development` · L · critical path
- **Goal:** the LangGraph graph from design.md §9 as a workflow package (design.md §5).
- **Acceptance criteria:**
  - `workflows/feature-development/` with `graph.py`, `steps/`, `prompts/`, `workflow.toml`, `requirements.lock`, `README.md`.
  - Nodes: plan → approve plan (`interrupt`) → write_tests (separate agent session, from the spec only) → implement → review (independent session) → fix loop with an iteration limit → gate (tests + property tests) → approve (`interrupt`) → open PR → summary.
  - `uv run pytest workflows/feature-development` with a fake adapter covers: review FAIL → fix → PASS, gate FAIL → fix → PASS, iteration limit reached, reject at an interrupt.
  - `uv run python -m workflows.feature_development.export_graph` prints `get_graph()` JSON.
- **Dependencies:** T3, T4. **Human:** 15 min (review prompts; they are a deliverable).

### T6 · Runner CLI: execution, checkpoints, worktree, audit log · L · critical path
- **Goal:** run a pinned workflow against a repo, isolated and auditable.
- **Acceptance criteria:**
  - `uv run jigworks run --workflow workflows/feature-development --repo sample-repo --prompt "<task>"` runs in a fresh git worktree, emits JSONL events on stdout.
  - LangGraph checkpoint + git commit per node; commit hash stored in graph state.
  - `uv run jigworks approve <runId>` / `reject <runId>` resumes the interrupt.
  - Audit log `.jigworks/runs/<runId>/audit.jsonl`: who started, workflow digest, model, steps, changed files, gate results, who approved and when, tokens, cost.
  - **Live proof:** one real run on `sample-repo` that goes through at least one fix loop (design.md §9 acceptance); audit log excerpt pasted.
- **Dependencies:** T5. **Human:** 15 min (watch the first live run).

### T7 · Evals for `feature-development` · M · required deliverable, not demo-blocking
- **Goal:** the brief asks for evals; measure the workflow, not just the code.
- **Acceptance criteria:**
  - `workflows/feature-development/evals/` with 3–5 synthetic tasks on `sample-repo`, at least one that tempts the agent to break an invariant.
  - `uv run python -m workflows.feature_development.evals.run` reports per task: passed gate, invariant preserved, fix iterations, tokens, cost; results committed as `evals/results/<date>.md`.
- **Dependencies:** T6. **Human:** 5 min.

## Milestone 2 — VS Code extension

### T8 · Extension scaffold + runner bridge · M · critical path
- **Goal:** extension spawns the local runner and consumes its JSONL events.
- **Acceptance criteria:**
  - `clients/vscode` builds; `pnpm --filter vscode package` produces a `.vsix` installable via `code --install-extension`.
  - Integration test (`@vscode/test-electron`) starts a run with a fake-adapter workflow and receives events; `pnpm --filter vscode test` output pasted.
- **Dependencies:** T2, T6. **Human:** 5 min.

### T9 · Webview UI: picker, prompt, live steps, Approve/Reject · L · critical path
- **Goal:** design.md §7 minus hub sync.
- **Acceptance criteria:**
  - Workflow picker (local workflows), prompt box, live step list with status, tokens and cost, Approve/Reject buttons that resume the interrupt.
  - Webview React app also runs standalone with recorded events; Playwright screenshots at **390 px and 1440 px** in the PR.
  - Screenshot/recording of the real extension in VS Code driving one run to the approval step.
- **Dependencies:** T8. **Human:** 10 min.

### T10 · "Import workflow from file" (.zip fallback) · S · not critical
- **Goal:** the distribution fallback from design.md §6, so the demo story works without the hub.
- **Acceptance criteria:** command imports a `.zip`, verifies the digest, unpacks to the extension cache; test with a valid and a tampered zip.
- **Dependencies:** T9.

## ─────────── CUT LINE ───────────

Everything above the line plus the presentation tickets is the demo. If time runs out, the demo stands on milestones 1 + 2 and the hub is presented as "what I cut" (design.md §1), using the Hub API table and architecture from design.md §4, §8.

## Milestone 3 — minimal hub on Vercel

### T11 · Vercel setup · S · not critical
Project `jigworks` already exists on Hobby and is linked to this repo.

| Step | Who |
|---|---|
| Enable Vercel Services (Beta) for the project, if it needs an opt-in | **Ondřej — dashboard** |
| Marketplace → Neon Postgres → install and connect to `jigworks` (all environments) | **Ondřej — dashboard** (accepts Marketplace terms) |
| Storage → Blob → create store, connect to `jigworks` | **Ondřej — dashboard** |
| `vercel link` in the repo | Ondřej once (login), then agent |
| `vercel env pull .env.local`; verify `DATABASE_URL` and `BLOB_READ_WRITE_TOKEN` exist | agent |
| Preview deploy of the T1 skeleton returns 200 on `/` and `/api/health` | agent |

- **Acceptance criteria:** `vercel env ls` lists the Neon and Blob variables; `curl -s <preview-url>/api/health` returns `{"ok":true}`.
- **Note:** Hobby function duration limits SSE → client uses reconnect/polling (design.md §4).
- **Dependencies:** T1.

### T12 · hub-api (FastAPI + Postgres) · L · not critical
- **Goal:** the subset of design.md §8 that the minimal hub needs: workflows, draft, publish (bundle `.zip` to Blob + digest), releases, channel resolve, bundle download, runs + events ingest, usage analytics.
- **Acceptance criteria:** `uv run pytest apps/hub-api` against a local Postgres; curl transcript against the preview deploy; workflow code never executed in the API process.
- **Dependencies:** T2, T11.

### T13 · hub-web (Vite + React + React Flow) · L · not critical
- **Goal:** Python editor + publish, read-only `get_graph()` graph, runs list with audit and cost, HR text tab.
- **Acceptance criteria:** Playwright e2e on the preview URL; screenshots at **390 px and 1440 px** for editor, graph, runs.
- **Dependencies:** T12. **Open decision:** see Q2.

### T14 · Runner → hub event sync · M · not critical
- **Goal:** runner posts events to `POST /api/runs/{id}/events`, queues locally when offline, syncs after recovery.
- **Acceptance criteria:** test that kills the network mid-run and shows the queued events arrive afterwards.
- **Dependencies:** T6, T12.

### T15 · Extension syncs from the hub `stable` channel · S · not critical
- **Acceptance criteria:** extension resolves `stable`, downloads the bundle, verifies digest, runs the pinned version; rollback of the channel is picked up.
- **Dependencies:** T9, T12.

## Presentation

### P1 · Answers to the brief's 9 questions · M · critical path
- **Goal:** slides/document answering all 9, going deep on 2–3.
- **Proposed deep dives** (pending the question text, see Q1): (a) invariants and independent tests/review — senior engineer; (b) audit trail, approver ≠ author, cost — platform + security; (c) measuring whether the team is faster — team lead (version comparison, design.md §11.3).
- **Acceptance criteria:** `docs/presentation.md` (or slides exported to `docs/`) covers all 9 questions; each deep dive links to the code/eval that backs it; "what I cut" slide.
- **Dependencies:** T6 for evidence. **Human:** 30 min (this is mine to own).

### P2 · Demo script · S · critical path
- **Acceptance criteria:** `demo/SCRIPT.md` with exact commands, expected output at each step, timing, and a fallback path for each live failure (rate limit, network, slow agent).
- **Dependencies:** T9. **Human:** 10 min.

### P3 · Backup recording · S · critical path
- **Acceptance criteria:** recording of the full demo script; link in README; ≤ 10 min.
- **Dependencies:** P2. **Human:** 20 min (recording).

### P4 · Final build log + README · S · critical path
- **Acceptance criteria:** BUILD_LOG.md totals add up (human vs agent); README has quickstart commands that a reviewer can paste.
- **Dependencies:** all done tickets. **Human:** 5 min.

## Human time check

Critical-path human time: T0 5 + T1 5 + T2 5 + T3 10 + T4 5 + T5 15 + T6 15 + T8 5 + T9 10 + P1 30 + P2 10 + P3 20 + P4 5 = **~2 h 20 min** — exactly the remaining budget. Milestone 3 has no human time left unless agent-only work goes well; T11 dashboard steps cost ~10 min.

## Open questions (need Ondřej)

1. **Q1 — the 9 questions:** the brief text is not in the repo. Where is it, or should I add it as `docs/brief.md`?
2. **Q2 — `get_graph()` in the minimal hub:** design.md §5 says compile in isolation (Vercel Sandbox is "Proposal"). For the minimal hub: compute the graph JSON at publish time on the publisher's machine and upload it with the bundle, or use Vercel Sandbox?
3. **Q3 — PR target in the demo:** `open PR` needs a remote. A separate throwaway GitHub repo for `sample-repo`, or a local branch + generated PR body for the demo?
