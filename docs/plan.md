# Jigworks — ticket plan

- **Source of truth:** [`docs/design.md`](design.md) v0.6, §1 "Prototype scope". This plan orders and slices that scope; the decisions below only resolve questions the design left open.
- **Tickets:** one Markdown file per ticket in [`tickets/prototype/`](../tickets/prototype/); conventions in [`tickets/README.md`](../tickets/README.md).
- **One repo:** hub, runner, VS Code extension, `sample-repo` and the demo all live in this repo, so the whole thing can be shared as a single repo.
- **Human time budget:** ~4 h total; 1 h 40 min spent before this plan → **~2 h 20 min left**. Agent time is unlimited and logged separately in [`BUILD_LOG.md`](../BUILD_LOG.md).

Labels: `milestone-0` (foundation), `milestone-1` (runner + workflow + sample-repo), `milestone-2` (VS Code extension), `milestone-3` (minimal hub), `presentation`.
Size: **S** ≤ 1 h agent, **M** 1–3 h agent, **L** > 3 h agent.

## Build order

```
T00 spike ─► T01 scaffold ─► T02 contracts ─┬─► T03 sample-repo ─┐
                                            └─► T04 adapter ─────┴─► T05 workflow ─► T06 runner CLI ─► T07 evals
                                                                                          │
                                                             T08 extension bridge ◄───────┘
                                                                    │
                                                             T09 sessions + prompt ─► T16 run view ─► T10 .zip import
                                            (T17 bugfix workflow, parallel to M2)
──────────────────────────────── CUT LINE ────────────────────────────────
T11 Vercel setup ─► T12 hub-api ─► T13 hub-web ─► T14 runner→hub sync ─► T15 extension sync
Presentation: P01 answers · P02 demo script · P03 backup recording · P04 build log/README
```

T00 comes first because the adapter, the contracts and the cost analytics all depend on what `stream-json` actually reports.

## Tickets

| ID | Ticket | Label | Size | Critical | Depends on |
|---|---|---|---|---|---|
| T00 | [Spike: `claude -p` stream-json](../tickets/prototype/T00-spike-claude-stream-json.md) | milestone-0 | S | yes | — |
| T01 | [Repo scaffolding](../tickets/prototype/T01-repo-scaffolding.md) | milestone-0 | S | yes | — |
| T02 | [Contracts: event and audit schema](../tickets/prototype/T02-contracts-schema.md) | milestone-0 | S | yes | T00, T01 |
| T03 | [sample-repo with invariants](../tickets/prototype/T03-sample-repo-invariants.md) | milestone-1 | M | yes | T01 |
| T04 | [Claude CLI adapter](../tickets/prototype/T04-claude-adapter.md) | milestone-1 | M | yes | T00, T02 |
| T05 | [Workflow `feature-development`](../tickets/prototype/T05-feature-development-workflow.md) | milestone-1 | L | yes | T03, T04 |
| T06 | [Runner CLI, checkpoints, audit log](../tickets/prototype/T06-runner-cli.md) | milestone-1 | L | yes | T05 |
| T07 | [Evals](../tickets/prototype/T07-evals.md) | milestone-1 | M | no* | T06 |
| T08 | [Extension: runner bridge](../tickets/prototype/T08-extension-runner-bridge.md) | milestone-2 | M | yes | T02, T06 |
| T09 | [Extension UI: workflows, sessions, prompt](../tickets/prototype/T09-extension-webview-ui.md) | milestone-2 | L | yes | T08 |
| T16 | [Extension run view: graph + % of plan](../tickets/prototype/T16-extension-run-view.md) | milestone-2 | M | yes | T06, T09 |
| T17 | [Second workflow `bugfix-with-repro`](../tickets/prototype/T17-bugfix-workflow.md) | milestone-1 | M | no | T05 |
| T10 | [.zip import fallback](../tickets/prototype/T10-extension-zip-import.md) | milestone-2 | S | no | T09 |
| | **— CUT LINE —** | | | | |
| T11 | [Vercel setup (dashboard steps)](../tickets/prototype/T11-vercel-setup.md) | milestone-3 | S | no | T01 |
| T12 | [hub-api](../tickets/prototype/T12-hub-api.md) | milestone-3 | L | no | T02, T11 |
| T13 | [hub-web](../tickets/prototype/T13-hub-web.md) | milestone-3 | L | no | T12 |
| T14 | [Runner → hub sync](../tickets/prototype/T14-runner-hub-sync.md) | milestone-3 | M | no | T06, T12 |
| T15 | [Extension hub sync](../tickets/prototype/T15-extension-hub-sync.md) | milestone-3 | S | no | T09, T12 |
| P01 | [Answers to the 9 questions](../tickets/prototype/P01-brief-answers.md) | presentation | M | yes | T06 |
| P02 | [Demo script](../tickets/prototype/P02-demo-script.md) | presentation | S | yes | T09 |
| P03 | [Backup recording](../tickets/prototype/P03-backup-recording.md) | presentation | S | yes | P02 |
| P04 | [Final build log + README](../tickets/prototype/P04-final-build-log-readme.md) | presentation | S | yes | all |

\* T07 is a required deliverable (the brief asks for evals), but the live demo does not depend on it.

## Cut line

Everything above the line plus the presentation tickets is the demo. If time runs out, the demo stands on milestones 1 + 2 and the hub is presented as "what I cut", using the architecture and the Hub API table from design.md §4 and §8.

## Human time check

Critical-path human time: T00 5 + T01 5 + T02 5 + T03 10 + T04 5 + T05 15 + T06 15 + T08 5 + T09 10 + T16 10 + P01 30 + P02 10 + P03 20 + P04 5 = **~2 h 30 min**, about 10 min over the remaining budget; T16 is the first thing to simplify if time runs short. Milestone 3 only happens if the agent-only work goes well; the T11 dashboard steps cost ~10 min.

## Decisions taken during planning

- **Tickets live in the repo** (`tickets/prototype/`), not as GitHub issues, so the plan is reviewable with the code.
- **`get_graph()` in the hub (T13):** computed only on Vercel, in Vercel Sandbox, behind a "Show graph" CTA in the editor that switches from the code to the visual graph. This settles the "Proposal" status of Vercel Sandbox in design.md §3 for the graph view.
- **Security in the gate (T05):** secret scan and static security scan run in the gate, because the security lead asks how we know the agent did not add a vulnerability or leak a secret.
- **Resume after restart (T06):** proven by a kill-and-resume test, covering the long-task engineer and design.md §11.1.
- **VS Code extension shape (T09, T16):** sidebar with workflows and parallel sessions, the prompt in the middle, each session in its own tab and worktree. The run view shows the graph position and progress as % of the plan, not remaining time. Progress weights come from local audit logs of the same release, falling back to `workflow.toml` weights. The extension gets the graph from the local runner (`jigworks graph`); only the hub uses Vercel Sandbox.
- **Demo target (T05, P02):** the demo runs in this repo. The workflow changes only `sample-repo/`, pushes a `demo/<runId>` branch and opens the PR against this repo.

- **The brief's 9 questions** are listed in P01, together with the deep dives (Q3, Q6, Q5; may change once the prototype exists).
