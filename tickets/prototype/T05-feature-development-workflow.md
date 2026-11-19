# T05 · Workflow `feature-development`

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-1` |
| Size | L |
| Demo critical path | yes |
| Depends on | T03, T04 |
| Human time | 15 min (review the prompts; they are a deliverable) |

## Goal

The LangGraph graph from design.md §9 as a workflow package (design.md §5).

## Acceptance criteria

- [ ] `workflows/feature-development/` with `graph.py`, `steps/`, `prompts/`, `workflow.toml`, `requirements.lock`, `README.md`.
- [ ] Nodes: plan → approve plan (`interrupt`) → write_tests (separate agent session, from the spec only) → implement → review (independent session) → fix loop with an iteration limit → gate (tests + property tests) → review (`interrupt`: approve / request changes / reject; request changes routes the comment to fix → gate → review again) → open PR → summary.
- [ ] `workflow.toml` has `[models]` (default + optional per node); the runner passes them to the adapter. VS Code never chooses the model.
- [ ] The runner records `first_result_commit` at the first review and the number of follow-up prompts in the audit log (input for the planned human delta).
- [ ] Open PR: pushes a branch `demo/<runId>` to this repo and runs `gh pr create` against it; the agent may only change files under `sample-repo/`.
- [ ] The gate also runs a secret scan (gitleaks) and a static security scan (semgrep or bandit) on the diff; a finding fails the gate like a failing test.
- [ ] `uv run pytest workflows/feature-development` with a fake adapter covers: review FAIL → fix → PASS, gate FAIL → fix → PASS, iteration limit reached, reject at an interrupt, request changes → fix → gate → review, a planted fake secret in the diff fails the gate.
- [ ] `uv run python -m workflows.feature_development.export_graph` prints the `get_graph()` JSON.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
