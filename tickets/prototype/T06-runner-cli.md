# T06 · Runner CLI: execution, checkpoints, worktree, audit log

| Field | Value |
|---|---|
| Status | todo |
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
- [ ] `uv run jigworks approve <runId>` / `reject <runId>` resumes the interrupt.
- [ ] Audit log `.jigworks/runs/<runId>/audit.jsonl`: who started, workflow digest, model, steps, changed files, gate results, who approved and when, tokens, cost.
- [ ] Live proof: one real run on `sample-repo` that goes through at least one fix loop (design.md §9 acceptance) and opens a PR in this repo; audit log excerpt and PR link pasted.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
