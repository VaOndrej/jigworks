# T26 · Fix rounds that end, answers that stick, upgrading a waiting run (`feature-development` 1.8.0)

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | yes (the demo run is stuck on 1.7.0) |
| Depends on | T25 |
| Human time | 5 min |

## Goal

The real run `run_20261120161021_60bbf3` (1.7.0, the BTC/USD paper exchange in `demo/`) went
review → approve_fix → fix → approve_fix → fix → approve_fix → fix → approve_fix. Review ran once;
nothing re-checked the fixes. The human kept answering questions they had already answered.

1. **Loop.** A fix that changed nothing went to `approve_fix` ("no_changes"), and every answer there
   except Reject went back to `fix`. Once the human's answers had settled everything, the fixer
   rightly changed nothing, so `approve_fix ⇄ fix` had no exit except Reject.
2. **Questions asked again.** `review_questions` was never cleared after the answer, and "Latest
   findings" kept showing the first review with its `QUESTION:` lines.
3. **Answers lost.** Only answers to reviewer questions went into the run's agreements
   (`clarifications`). Answers to a blocked fixer or after a no-change fix (the 250-socket limit and
   the scratch files) reached only the next fix, so a new reviewer would re-open them.
4. **Gate dead end.** The human ruled a test from write_tests wrong (option b) and allowed the
   fixer to change it. The gate's protected-tests check rejects that for ever, and the only way out
   it named was "reject the run and start again".
5. **No way to apply a fixed release to a waiting run.** The run's package is pinned; the human
   would have to start the whole build again.

## Acceptance criteria

- [x] A fix right after the human's answer goes on to review/gate even if it changed nothing; "no_changes" only escalates when nobody answered since the last check.
- [x] Approve (no comment) at `approve_fix` after a no-change or a blocked (`NEEDS HUMAN`) fix re-runs the check without another fix.
- [x] `approve_fix` clears the reviewer's questions; once the human answered after a check, the report shows that check's findings without their `QUESTION:` lines.
- [x] Every answer at `approve_fix` goes into the run's agreements (`spec()`), shown to the next reviewer and fixer as final decisions; the re-reviewer reports a waived finding as `ACCEPTED` (closed).
- [x] When the gate rejects protected files, `approve_fix` shows their diff since write_tests; Approve accepts exactly that content (git blob hash) and re-runs the gate; a later edit fails it again.
- [x] Runner: `jigworks upgrade <runId> --workflow <dir>` switches a run that is not being worked on to a newer release of the same workflow (same name, no node dropped), keeping state, sessions, commits and answers; recorded in `run.json` `upgrades`.
- [x] Gate: a new suppression marker (`# nosec`, `noqa`, `type: ignore`, `skip`/`xfail`, `eslint-disable`, `@ts-ignore`, …) that implement or fix added since write_tests fails the gate; approve_fix lists it and Approve accepts exactly that line (file + text).
- [x] Agents may delete files (`git rm`) and run the gate's scanners (`bandit`, `gitleaks`); the implement and fix prompts name the scanner commands.
- [x] Only test files written by write_tests are protected (`tests/`, `test_*`, `*_test.*`, `*.test.*`, `*.spec.*`, conftest); its scratch scripts are not. No scratch files in the repo (write_tests, implement, fix prompts).
- [x] A repo rule that needs a change outside the scope is a note for the human, not a finding or a QUESTION (review, re-review, fix prompts).
- [x] A comment at approve_fix does not accept protected files or suppressions; the screen says so, says it again on the next round, and the fixer may not claim they were accepted.
- [x] Extension: at approve_fix the Approve button is named after what it does: "Accept these changes" when protected files or suppressions wait for the human, "Re-run the check" after a no-change or blocked fix, else "Continue fixing" (`src/shared/fixButtons.ts`, read from the workflow's text). The real run stopped because the human read "Continue fixing" as "more fixes" and typed "I agree" instead.
- [x] Rehearsed on a copy of the real run (cloned worktree, fake agent): upgrade → Approve → review → gate; protected test accepted, gate left with only bandit B608.
- [ ] The real run upgraded and continued (human).
- [ ] Published to the hub as 1.8.0 (human).

## Notes

- Found on the real run after the upgrade: the fixer silenced bandit B608 with `# nosec` and could not run bandit itself; it could not delete scratch files (`rm`, `git rm` denied); the test writer's scratch script `check_literals_tmp.py` was "protected"; the human typed "I agree with the change" instead of pressing Approve, and the fixer then said the files were accepted.
- The suppression list is a regex over added lines. It misses suppressions in config files (e.g. a bandit `skips` list in pyproject.toml, an `ignore` list in ruff config) and markers it does not know.
- An accepted suppression is pinned to file and exact line text, not to the line number: the same text added again elsewhere in that file passes.

- `run_started` of an upgraded run still names 1.7.0; later events carry 1.8.0. The hub keeps the run under the release it started with (its `runs.release`), so hub analytics count it as 1.7.0.
- `upgrade` checks only that no graph node disappears. A release that renames a state key or changes what a node expects of the checkpointed state can still break a run; nothing checks that.
- Accepting protected files is a new human power over the read-only tests (design.md: "a wrong test is a human decision"). It is audited (the `review_decision` event, `fix_history`, `clarifications`) but there is no separate audit field for it (frozen contract).
- Approve at `approve_fix` with pending protected files both accepts them and continues; there is no way to continue without accepting except a comment for the fixer.
- The rehearsal used a fake agent, so whether the real fixer writes `NEEDS HUMAN: accept …` for the test (instead of restoring it) depends on the prompt and is unverified.

## Evidence

```
# before the fixes (red), the loop reproduced: review once, then fix ×4
test_a_fixer_that_keeps_changing_nothing_cannot_loop_without_a_check
  AssertionError: every human answer leads to a check: ['triage', 'plan', 'write_tests', 'implement', 'review', 'fix', 'fix', 'fix', 'fix']
test_a_fix_that_changes_nothing_after_the_human_answered_goes_back_to_review   '## Questions from the reviewer' is contained here
test_approve_after_a_fix_that_changed_nothing_rechecks_without_another_fix     message: '… Approve to let it try again …'
test_an_accepted_finding_is_closed                                              assert 1 == 0
test_the_human_can_accept_a_change_to_a_protected_test                          no '## Changes to protected files'
test_an_accepted_protected_change_is_pinned_to_its_contents                     'approve_fix' == 'approve_pr'

# second batch (suppressions, git rm / scanners, scratch files, rules outside the scope, comment ≠ Approve), red first:
test_a_new_suppression_marker_needs_the_human                          TypeError: 'NoneType' object is not subscriptable (no "suppressions" check)
test_fixers_may_delete_files_and_run_the_gate_scanners                 missing 'Bash(git rm:*)', 'Bash(bandit:*)', 'Bash(gitleaks:*)'
test_scratch_files_of_the_test_writer_are_not_protected                'waiting_human' == 'succeeded'
test_agents_are_told_how_to_treat_scratch_files_and_rules_outside_the_scope   'scratch' not in the write_tests prompt

# extension (button labels), red first: units.test.ts  error TS2307: Cannot find module '../../shared/fixButtons'
$ pnpm --filter vscode test:unit     # 26 passing
$ pnpm --filter vscode test:ui       # 16 passed, screenshot e2e/local/screenshots/vscode-approve-fix-protected-1440.png

$ uv run pytest workflows runner -q -p no:cacheprovider
127 passed, 1 skipped, 17 warnings in 364.81s (0:06:04)

# rehearsal on a copy of run_20261120161021_60bbf3 (cloned worktree, fake agent, no hub)
$ jigworks upgrade run_20261120161021_60bbf3 --workflow workflows/feature-development
run_20261120161021_60bbf3: feature-development@1.7.0 → feature-development@1.8.0 (sha256:…), status waiting_human.
$ jigworks approve …   → approve_fix ✓, review ✓ (2), gate ✗ (protected tests, bandit B608), fix, approve_fix (diff of test_sl_tp_api.py)
$ jigworks approve …   → gate: scope ✓, protected tests ✓, tests ✓, gitleaks ✓, bandit ✗ (store.py:118,120,127)
```
