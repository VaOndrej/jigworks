# T22 · Fix loops that ask the human instead of failing (`feature-development` 1.7.0)

| Field | Value |
|---|---|
| Status | review |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no |
| Depends on | T20 |
| Human time | 5 min |

## Goal

The first real brainstorming run (`run_20261120122836_6ab988`, 1.6.0) ended `failed` at "fix loop
limit reached (3 fixes)" after 64 % of the plan and about $28 of tokens, with no way to go on. A
fix loop must never just end the run: the fixes go on by themselves while they make progress,
the human decides when they stop making it, and sees round by round what happened. Runs that
already failed this way can be continued.

## Acceptance criteria

- [x] Review findings carry stable IDs (`- F1 file:line ...`); after a fix the reviewer re-checks the previous findings by ID (`prompts/rereview.md`) and reports regressions, instead of starting a new review. Every finding must be fixed for PASS.
- [x] The fixer goes on without the human while the open problems (review findings, failed gate checks) go down; two fixes in a row without improvement, the cap (`max_fix_loops`, default 8) or a reviewer `QUESTION:` line → new interrupt `approve_fix`.
- [x] `approve_fix` shows why, the reviewer's questions, a table of every round (what the review/gate found, the fixer's one-line summary, lines changed) and the trend (`3 → 2 → 2`). Continue fixing (+3), Continue with my note (the note or answers go to the fixer, answers also to the reviewer), Stop the run.
- [x] The fixer reads the human's note first; the reviewer gets the answers in the spec.
- [x] Runs of releases before 1.7.0 that ended at the limit: `jigworks resume <runId> --more-fixes N [--comment ...]` forks the checkpoint before the last fix, saves the new limit in `run.json`, and records the decision as a `review_decision` on `fix`. A plain `resume` names this command.
- [x] Extension: Continue fixing card with the rounds and a hint field for such runs; `approve_fix` buttons; the Activity line of every review/gate/fix round carries the trend ("2 open findings (was 3)" · first open finding · fixer summary · files changed).
- [x] Skills adapted from MIT-licensed Matt Pocock skills and Superpowers (attribution in `plugin/THIRD_PARTY_NOTICES.md`): `slice-the-plan`, `deep-modules`, `test-first`, `verify-before-done`, `diagnose-before-fixing`, `handle-review-findings`, `pr-summary`; brainstorming, review, tests and planning skills strengthened.
- [ ] The real run `run_20261120122836_6ab988` continued with `claude -p` (human: costs tokens; a dry run with the fake adapter on a copy of it is below).
- [ ] Published to the hub as 1.7.0 (human).
- [ ] A live `claude -p` run shows the agents loading the new skills (unverified).

## Notes

- `approve_fix` uses the contract's `plan` stage (the contract has only `plan` and `pr`), like `approve_brainstorm`; the node name tells the extension what it is. A `fix` stage would be cleaner but is a contract change.
- "Take it to PR review with open findings" was left out: every finding must be fixed.

## Evidence

```
$ uv run pytest workflows/feature-development/tests -v -p no:cacheprovider
44 passed (stopped at 83 % on request), then the remaining 9:
$ uv run pytest <the 9 remaining tests> -q -p no:cacheprovider
9 passed, 17 warnings in 135.73s (0:02:15)

$ uv run pytest runner -q -p no:cacheprovider
50 passed, 1 skipped, 17 warnings in 86.50s (0:01:26)
# incl. test_cli_continue_a_run_that_failed_at_the_fix_loop_limit, against the real 1.6.0 package (git archive 394d630)

$ pnpm --filter vscode test        # 30 passing, 1 pending
$ pnpm --filter vscode test:ui     # 15 passed
```

Screenshots (1440 px): `e2e/local/screenshots/vscode-fix-limit-continue-1440.png`,
`e2e/local/screenshots/vscode-approve-fix-question-1440.png`.

Dry run on a copy of `run_20261120122836_6ab988` (fake adapter, real gate):
`resume --more-fixes 3` forked the checkpoint before fix #4 → fix #5 → review #5 PASS → gate
FAIL (2 failing tests, INVARIANTS.md/README edited after write_tests, bandit B108) → fixes
#6–#8 (the fake fixer changes nothing) → limit 6. The new limit was saved in `run.json`.
