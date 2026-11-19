# T07 · Evals for `feature-development`

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no (required deliverable, not demo-blocking) |
| Depends on | T06 |
| Human time | 5 min |

## Goal

The brief asks for evals; measure the workflow, not just the code.

## Acceptance criteria

- [ ] `workflows/feature-development/evals/` with 3–5 synthetic tasks on `sample-repo`, at least one that tempts the agent to break an invariant.
- [ ] `uv run python -m workflows.feature_development.evals.run` reports per task: gate passed, invariant preserved, fix iterations, tokens, cost; results committed as `evals/results/<date>.md`.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
