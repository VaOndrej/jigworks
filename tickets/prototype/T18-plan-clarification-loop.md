# T18 · Plan agreed with the human (`feature-development` 1.5.0)

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-1` |
| Size | S |
| Demo critical path | no |
| Depends on | T05 |
| Human time | 2 min |

## Goal

Before anything is built, the human and the planner understand each other: the planner can ask
questions, the human can comment on the plan as many rounds as it takes, and the planner
remembers the conversation. Rule for every workflow: design.md §5.

## Acceptance criteria

- [x] Request changes at `approve_plan` goes back to `plan`, which resumes the planner's own session with the comment; nothing after the plan runs meanwhile.
- [x] The planner may reply `QUESTIONS:`; the plan interrupt then says it has questions. Approving open questions sends the planner back to state its assumptions.
- [x] `write_tests`, `implement` and `review` get the approved plan plus the planning conversation.
- [x] At most 5 planning rounds (`max_plan_rounds` option), then the run fails with a clear error.
- [x] Plan discussion is not counted as a follow-up prompt (runner ledger: only `request_changes` at the PR stage).
- [x] `workflow.toml` is 1.5.0; README, design.md §5/§9/§13 and T17 updated.
- [ ] Published to the hub as 1.5.0 (human).
- [ ] One real `claude -p` run through a questions round (unverified: only the fake adapter so far).

## Evidence

```
$ uv run pytest workflows/feature-development runner -q -p no:cacheprovider
72 passed, 1 skipped, 17 warnings in 216.70s (0:03:36)

$ uv run pytest workflows/feature-development -q -p no:cacheprovider   # after the docstring update
26 passed, 17 warnings in 158.95s (0:02:38)
```

New tests in `workflows/feature-development/tests/test_workflow.py`:
`test_request_changes_at_the_plan_replans_in_the_same_session`,
`test_planner_asks_questions_before_it_plans`,
`test_approving_open_questions_does_not_start_the_build`,
`test_planning_round_limit_ends_the_run_failed`.

## Notes

- No contract change: the questions travel in the existing `plan` field of the interrupt and
  the answers in the existing Request changes comment. The extension needs no change.
