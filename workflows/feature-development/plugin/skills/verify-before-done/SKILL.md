---
name: verify-before-done
description: Use before you write a reply that says a change works, a test passes or a finding is fixed. Evidence before claims - run the command, read its output, report the real state.
---

# Verify before done

Your reply goes to a reviewer and then to a human. A claim without evidence costs a full review
round when it turns out false, and the reviewer does not trust your report anyway. So every
claim in your reply rests on a command you ran in this session, after your last edit.

## Before any claim

1. **Identify** the command that proves it (the gate's test command, a single test, a build).
2. **Run** the whole command, fresh, after your last change. An earlier run does not count.
3. **Read** the output: the exit code, the number of passed, failed, skipped and errored tests.
4. **Compare** it with the claim. If they do not match, report what the output says.
5. Only then write the claim, with the command and its summary line.

| Claim | Needs | Is not enough |
|-------|-------|---------------|
| Tests pass | the gate's test command: 0 failed, 0 errors | one test file, "should pass" |
| Bug fixed | the test of the original symptom passes | the code changed |
| Regression test works | it failed before the fix and passes after | it passes once |
| Finding F2 fixed | the test or check for F2 passes, and the diff shows the change | "addressed F2" |
| Plan done | each plan line checked against the diff | the tests are green |

## Check against the plan, not only the tests

Green tests prove what the tests check. Re-read the plan (and the findings, in a fix) line by
line and confirm each one in the diff (`git diff`). Anything not done goes into your reply as
not done.

## Words that mean you have not verified

"should", "probably", "seems to", "I believe", "looks correct". Replace them with the command
and its result, or with "not verified: why".

## Reporting

- The exact command you ran and its summary line (`12 passed, 0 failed in 1.4s`).
- What is not done, what you could not run and why, and what you doubt. Unsaid gaps are worse
  than reported ones: the reviewer will find them and the round is lost.
- Never write "all green" or "everything works" unless the output you just read says so.
- Remove temporary debug output and scratch files before you report.
