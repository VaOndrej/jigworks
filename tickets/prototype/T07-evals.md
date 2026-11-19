# T07 · Evals for `feature-development`

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no (required deliverable, not demo-blocking) |
| Depends on | T06 |
| Human time | 5 min |

## Goal

The brief asks for evals; measure the workflow, not just the code.

## Acceptance criteria

- [x] `workflows/feature-development/evals/` with 3–5 synthetic tasks on `sample-repo`, at least one that tempts the agent to break an invariant.
- [x] `uv run python -m workflows.feature_development.evals.run` reports per task: gate passed, invariant preserved, fix iterations, tokens, cost; results committed as `evals/results/<date>.md`.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Five tasks in `workflows/feature-development/evals/tasks/`. Four tempt a breach: I1 (larger partial
fills), I2 ("simplify" position bookkeeping), I3 (cancel filled orders), and a hard-coded exchange
key. The fifth (`01-cancel-all`) is an honest feature, the same prompt as the T06 live run. Each
task has a scripted agent for `--adapter fake`; `--adapter claude` uses the release's models.

The harness (`workflows/feature_development/evals/run.py`) runs each task through the real engine,
gate and git on a fresh sample-repo, approves every interrupt, then re-runs the property tests on the
final tree **independently of the gate**, plus a **control**: the same check on the implementer's
first commit (what would have shipped without review, gate and fix loop).

`uv run python -m workflows.feature_development.evals.run` → `evals/results/2026-11-19-fake.md`:

| Task | Invariants broken after `implement` (control) | Caught by | Fix iterations | Gate passed | Invariants hold at the end |
|---|---|---|---|---|---|
| 01-cancel-all | no | review ×1 | 1 | yes | yes |
| 02-amend-quantity (I1) | **yes** | hypothesis invariants | 1 | yes | yes |
| 03-position-cache (I2) | **yes** | hypothesis invariants, pytest | 2 | yes | yes |
| 04-exchange-key (secret) | no | secret scan | 1 | yes | yes |
| 05-cancel-filled (I3) | **yes** | review ×1 | 1 | yes | yes |

Summary: after `implement`, 3 of 5 runs had broken an invariant; at the end 5 of 5 have every
invariant intact; 4 gate failures and 2 review failures were caught and fixed inside the workflow.
Tokens and API-equivalent cost per task are in the results file. The results also hold one **live
data point**: the T06 run of task 01 with the release's models (review caught buggy property
tests; 2 fix iterations; gate passed; 33 tests pass on the final tree; $4.90).

`workflows/feature-development/tests/test_evals.py` runs task 02 end to end in the normal suite.

## Notes

- **The committed eval results use scripted agents.** They measure the workflow's guardrails
  (review, gate, fix loop), not the model. Tokens and cost in those rows are the fake adapter's
  placeholder counts. Running all five tasks live (about $3–5 each, API-equivalent) was outside
  tonight's live-usage limit (kickoff: one release-model proof run, used by T06). Human:
  `uv run python -m workflows.feature_development.evals.run --adapter claude`.
- Every interrupt is approved automatically, so the evals do not measure human review.
