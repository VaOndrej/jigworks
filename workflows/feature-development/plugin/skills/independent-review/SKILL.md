---
name: independent-review
description: Use when reviewing a change you did not write, before the gate and the human. How to find what breaks the specification or the repo's invariants, and how to report a verdict.
---

# Independent review

You did not write this change and you owe it nothing. The human sees your verdict before the
pull request.

## Order of work

1. Read the specification and the approved plan, then the whole diff against the base commit.
2. For each behaviour in the plan, find the code and the test that cover it. A behaviour with
   no test is a finding.
3. Check the invariants (`INVARIANTS.md`, or the rules the code clearly relies on): state that
   no longer adds up, transitions out of terminal states, half-applied changes on errors.
4. Check the tests themselves: do they test the specification, or the implementation? Were any
   weakened, skipped or deleted?
5. Look for risk: secrets, unsafe input handling, swallowed errors, changes outside the plan.

## Reporting

- A finding names the file and line, what is wrong, and what the specification says instead.
- Do not report style or taste; the gate and the human handle that.
- End with exactly one line: `VERDICT: PASS` when nothing above is wrong, else `VERDICT: FAIL`.
