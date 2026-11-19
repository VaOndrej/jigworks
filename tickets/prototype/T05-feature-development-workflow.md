# T05 · Workflow `feature-development`

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-1` |
| Size | L |
| Demo critical path | yes |
| Depends on | T03, T04 |
| Human time | 15 min (review the prompts; they are a deliverable) |

## Goal

The LangGraph graph from design.md §9 as a workflow package (design.md §5).

## Acceptance criteria

- [x] `workflows/feature-development/` with `graph.py`, `steps/`, `prompts/`, `workflow.toml`, `requirements.lock`, `README.md`.
- [x] Nodes: plan → approve plan (`interrupt`) → write_tests (separate agent session, from the spec only) → implement → review (independent session) → fix loop with an iteration limit → gate (tests + property tests) → review (`interrupt`: approve / request changes / reject; request changes routes the comment to fix → gate → review again) → open PR → summary.
- [x] `workflow.toml` has `[models]` (default + optional per node); the runner passes them to the adapter. VS Code never chooses the model.
- [x] The runner records `first_result_commit` at the first review and the number of follow-up prompts in the audit log (input for the planned human delta).
- [x] Open PR: pushes a branch `demo/<runId>` to this repo and runs `gh pr create` against it; the agent may only change files under `sample-repo/`.
- [x] The gate also runs a secret scan (gitleaks) and a static security scan (semgrep or bandit) on the diff; a finding fails the gate like a failing test.
- [x] `uv run pytest workflows/feature-development` with a fake adapter covers: review FAIL → fix → PASS, gate FAIL → fix → PASS, iteration limit reached, reject at an interrupt, request changes → fix → gate → review, a planted fake secret in the diff fails the gate.
- [x] `uv run python -m workflows.feature_development.export_graph` prints the `get_graph()` JSON.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Package: `workflows/feature-development/` (`graph.py`, `steps/{nodes,gate,secrets,runtime}.py`,
`prompts/{plan,write_tests,implement,review,fix,summary}.md`, `workflow.toml` 1.4.0,
`requirements.lock`, `README.md`). Runner side used by the tests: `runner/jigworks_runner/`
`engine.py` (drives the graph, injects the runtime, one git commit per node), `ledger.py`
(audit record and summary folded from the events: `firstResultCommit`, `followUpPrompts`,
`fixLoops`), `package.py` (loader, digest), `adapters/fake.py`.

`uv run pytest workflows -v` (fake adapter, a real git repo with a copy of sample-repo, the
**real** gate; every event checked against the `RunEvent` contract, seq without gaps, progress
never backwards, `AuditRecord` valid):

```
test_happy_path_approved_first_time PASSED
test_one_git_commit_per_node PASSED
test_models_come_from_the_release PASSED
test_tests_and_review_run_in_separate_sessions PASSED
test_review_fail_then_fix_then_pass PASSED
test_gate_fail_on_broken_invariant_then_fix_then_pass PASSED
test_fix_loop_limit_ends_the_run_failed PASSED
test_reject_at_the_plan PASSED
test_reject_at_the_pr_review PASSED
test_request_changes_goes_fix_gate_review PASSED
test_planted_secret_fails_the_gate PASSED
test_security_finding_fails_the_gate PASSED
test_change_outside_sample_repo_fails_the_gate PASSED
test_open_pr_pushes_demo_branch PASSED
test_usage_limit_pauses_and_resumes PASSED
test_agent_failure_fails_the_run PASSED
test_export_graph_prints_graph_json PASSED
======================== 17 passed in 85.79s (0:01:25) =========================
```

In `test_gate_fail_on_broken_invariant_then_fix_then_pass` the fake implementer applies the
`overfill` bug from T03: the plain tests pass, the property tests fail, the gate routes to fix.

`uv run python -m workflows.feature_development.export_graph | jq -c ...`:

```
{"nodes":["__start__:start","plan:step","approve_plan:interrupt","write_tests:step","implement:step","review:step","fix:step","gate:step","approve_pr:interrupt","open_pr:step","summary:step","__end__:end"],"edges":18,"release":"feature-development@1.4.0"}
```

## Notes

- **gitleaks and semgrep are not installed** on this machine. The gate uses gitleaks when it is
  on PATH, otherwise built-in gitleaks-style rules (`steps/secrets.py`: AWS key id, private key,
  GitHub/Slack/Anthropic tokens, generic secret assignment). The static scan is bandit
  (installed through uv), medium severity and up, B101 skipped. The gitleaks branch is untested.
- `gh pr create` is implemented in `engine.default_pr_opener` (only when the remote is on
  GitHub) but **not exercised**: the tests and the T06 live proof push `demo/<runId>` to a local
  bare remote, and the PR URL is then `<remote>#demo/<runId>`.
- Version is **1.4.0** (the hub fixtures already hold 1.2.0 and 1.3.0 of the sample package, and
  releases are immutable). The graph adds one edge to the fixture graph: `fix → __end__` when
  the fix loop limit (3) is reached.
- Request changes **at the plan** does not re-plan; the comment is appended to the plan.
- The suite takes ~85 s because the real gate runs the Hypothesis property tests every time.
