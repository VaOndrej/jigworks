---
name: test-first
description: Use when implementing a change against tests written before it, or when adding any behaviour or bug fix. The red-green loop one behaviour at a time, minimal code, and why a test you never saw fail proves nothing.
---

# Test first

If you did not watch a test fail, you do not know that it tests the right thing. The tests for
this change were written before the code; your job is to turn them green honestly, one
behaviour at a time.

## The loop

1. **Pick one failing test** (or one behaviour of the plan, in milestone order).
2. **Red.** Run it and read the failure. It must fail because the behaviour is missing, not
   because of a typo, an import error or broken setup. If it fails for the wrong reason, find
   out why before you write code.
3. **Green.** Write the simplest code that makes it pass. No options, flags or extension points
   the plan does not ask for.
4. **Run it again, and the rest of the suite.** It passes, nothing else broke, the output is
   free of new errors and warnings.
5. Next test. Tidy up only while everything is green, and never change behaviour while tidying.

## When there is no test

If the plan names a behaviour that no test covers, or you fix a bug, write a test for it first,
watch it fail, then write the code. Put it in a new test file or next to the existing ones; do
not edit the tests written for this change.

## Good tests (for the ones you add)

- Test behaviour through the public interface, named as a sentence:
  `test_cancel_of_a_filled_order_is_refused`.
- Expected values come from the specification, a worked example or a known-good literal,
  never recomputed the way the code computes them (`assert add(a, b) == a + b` can never fail).
- Mock only what crosses the process boundary (network, clock), and only if the repo already
  does.

## When a test resists

- **The test fails and you think it is wrong:** do not change it. Make sure you read it right,
  then say in your reply which test, why, and what you think the specification means.
- **The test passes before you wrote any code:** it tests existing behaviour or nothing. Say so
  in your reply.
- **Making one test pass breaks another:** the two together describe the behaviour; find the
  design that satisfies both instead of special-casing one.
- **You cannot make it pass without weakening an invariant:** stop and report it. The gate fails
  a broken invariant anyway.

## Never

- Skip, delete, weaken or rewrite a test to make it pass.
- Detect the test environment in production code.
- Write the whole feature first and run the tests at the end.
