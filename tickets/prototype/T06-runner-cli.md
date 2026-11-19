# T06 · Runner CLI: execution, checkpoints, worktree, audit log

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-1` |
| Size | L |
| Demo critical path | yes |
| Depends on | T05 |
| Human time | 15 min (watch the first live run) |

## Goal

Run a pinned workflow against a repo, isolated and auditable.

## Acceptance criteria

- [ ] `uv run jigworks run --workflow workflows/feature-development --repo sample-repo --prompt "<task>"` runs in a fresh git worktree and emits JSONL events on stdout.
- [ ] LangGraph checkpoint + git commit per node; the commit hash is stored in the graph state.
- [ ] Resume after a restart (design.md §11.1): kill the runner mid-node, then `uv run jigworks resume <runId>` continues from the last checkpoint; a node whose git commit already exists is not executed twice. Test output pasted.
- [ ] `uv run jigworks approve <runId>`, `request-changes <runId> --comment "…"` and `reject <runId>` resume the interrupt; request changes counts as a follow-up prompt.
- [ ] Parallel sessions: two runs started at the same time (same or different workflow) each get their own worktree, checkpoint store and event stream, and do not touch each other's files. `uv run jigworks ls` lists them with status. Test output pasted.
- [ ] Progress estimate: every event carries `progress` (0–100) = weight of finished nodes / weight of the planned path. Weights come from durations in past local audit logs of the same release digest; with no history they fall back to `weight` per node in `workflow.toml`. A fix loop never moves progress backwards. Unit test with a recorded run.
- [ ] `uv run jigworks graph <workflow>` prints the `get_graph()` JSON locally (the runner executes the workflow code anyway), so the extension can draw the graph without the hub.
- [ ] Audit log `.jigworks/runs/<runId>/audit.jsonl`: who started (`git config user.email`), workflow digest, model, steps, changed files, gate results, who approved and when, tokens, cost.
- [ ] Live proof: one real run on `sample-repo` that goes through at least one fix loop (design.md §9 acceptance) and opens a PR against a local bare remote (no push to GitHub during the build); audit log excerpt pasted.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
