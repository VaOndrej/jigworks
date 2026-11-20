---
name: tests-from-the-spec
description: Use when writing tests for a change before it is implemented. How to test behaviour from the specification through public interfaces so another agent cannot pass them with a shortcut.
---

# Tests from the spec

You write the tests; another agent implements against them and may not change them later.
Your tests are the specification it sees.

## What to test

- Behaviour the specification and the approved plan name, through the public interface the
  plan names (a function, an endpoint, a CLI command), never through private helpers.
- One test per behaviour, named as a sentence: `test_cancel_of_a_filled_order_is_refused`.
- Expected values from the specification, a worked example or a known-good literal, never
  recomputed the way the code would compute them (`assert total(items) == sum(i.price for i in
  items)` passes by construction and can never catch a bug).
- Edge cases the plan mentions, and the failure path: what is refused, with which error.
- For every invariant the plan touches, a property-based test (Hypothesis for Python,
  fast-check for TypeScript) that generates many inputs, not one example.

## What not to do

- Do not mock the module under test or its internals; mock only what crosses the process
  boundary (network, clock), and only if the repo already does.
- Do not write tests that pass before the feature exists, except tests of behaviour that
  must not change.
- Do not weaken, skip or delete existing tests.
- Do not assert on call counts or call order, or check results through a side channel (reading
  the database or a file directly) when the interface can show them.

## Watch them fail

Run the new tests before you reply. Each must fail because the behaviour is missing (an
assertion, or "no such function"), not because of a typo or a broken fixture. A new test that
passes now tests nothing new: fix it. Keep a missing import from failing the whole file at
collection time where you can (import inside the test, or one file per new module), so the
existing tests keep running. Say in your reply which tests fail and why.

## Setup

Use the test runner the repo already has. If there is none, set up the smallest one that fits
the stack and make the gate's test command run it; implement cannot change it afterwards.
