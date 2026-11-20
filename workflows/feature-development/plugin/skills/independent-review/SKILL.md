---
name: independent-review
description: Use when reviewing a change you did not write, before the gate and the human. How to review on two separate axes (the specification and the repo's standards), find what breaks the invariants, and report findings, questions and a verdict.
---

# Independent review

You did not write this change and you owe it nothing. The human sees your verdict before the
pull request. Do not trust the implementer's or the fixer's report; check the diff.

## Order of work

1. Read the specification and the approved plan, then the whole diff against the base commit.
2. Review the **spec axis**, then the **standards axis**, separately (below). A change can do
   exactly what was asked and still break the repo's rules, or follow every rule and build the
   wrong thing; reviewing them apart stops one from hiding the other.
3. Check the invariants (`INVARIANTS.md`, or the rules the code clearly relies on): state that
   no longer adds up, transitions out of terminal states, half-applied changes on errors.
4. Check the tests themselves (below).
5. Look for risk: secrets, unsafe input handling, swallowed errors, changes outside the scope.

## Spec axis

For each behaviour in the plan (and each milestone of the design), find the code and the test
that cover it. Report:

- a behaviour that is **missing or partial**, or has no test;
- a behaviour that is **implemented wrong**: it looks done, but does something else than the
  specification line says (quote the line);
- **scope creep**: behaviour, options or abstractions nobody asked for.

## Standards axis

Find what the repo documents about how code is written (`AGENTS.md`, `CONTRIBUTING.md`,
`CODING_STANDARDS.md`, linter and formatter configs, the conventions of neighbouring code) and
check the diff against it. A breach of a documented rule is a finding; cite the rule. Skip what
tooling already enforces.

Code smells (duplicated logic, a name that hides what a thing does, a pass-through module,
speculative generality) are judgement calls. Report one only when it makes the change wrong or
hard to verify, for example duplicated logic that has already diverged.

## The tests

- Do they test the specification through the public interface, or the implementation (mocked
  internals, private helpers, call counts)?
- Are any **tautological**: the expected value is computed the way the code computes it, so the
  test can never fail?
- Is there a property test for every invariant the change touches?
- Were any tests weakened, skipped or deleted, or a check silenced?

## Reporting

- One finding per line, numbered with a stable ID: `- F1 path/file.py:42 what is wrong; what the
  specification says instead`. Every finding must be fixed before the change can pass, so do
  not report style or taste; the gate and the human handle that.
- When a finding cannot be fixed without a decision only the human can make (the specification
  is silent or contradicts itself), add a line `QUESTION: <the question, with the options and
  your recommendation>`. The human sees these lines before the next fix.
- End with exactly one line: `VERDICT: PASS` when nothing above is wrong, else `VERDICT: FAIL`.

## Re-review after a fix

When you get the findings of the previous review, check each of them first and report it
under its old ID as `- F1 FIXED` or `- F1 NOT FIXED: why`. Check it in the code, not in the
fixer's reply. When the fixer pushed back on a finding with evidence, weigh the evidence: if it
holds, report the finding as `FIXED` and say it was withdrawn; if not, `NOT FIXED` and why.
Then look for regressions the fix introduced and number them from the next free ID. Do not
widen the review to code the fix did not touch, unless you find a bug, a broken invariant or a
security problem.
