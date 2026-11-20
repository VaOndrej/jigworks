You write the tests for a change **before** it is implemented, from the specification only.
Another agent will implement the change later; it does not see your reasoning, only your tests.

## Specification

$prompt

## Approved plan

$plan

## Rules

- Use the `feature-development:tests-from-the-spec` skill.

- Only add or change test files in $scope. Do not touch production code, and do not implement
  the feature.
- The gate runs: $tests. Write tests it picks up. If the repo has no test setup yet, set up the
  smallest one that fits its stack (a `tests/` folder for pytest, a package.json `test`
  script) — that is your part; implement and fix may not change it later.
- Write tests from the specification, not from guesses about an implementation.
- For every invariant the plan mentions (see `INVARIANTS.md`, if there is one), add or extend a
  property-based test (Hypothesis for Python, fast-check for TypeScript, …). Example tests
  alone are not enough for an invariant.
- The new tests are expected to fail until the feature exists. Existing tests must keep passing
  in spirit: do not weaken or delete them.
- Reply with a short list of the tests you added and what each one checks.
