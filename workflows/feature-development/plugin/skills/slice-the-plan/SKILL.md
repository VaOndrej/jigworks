---
name: slice-the-plan
description: Use when turning a task or an approved design into an implementation plan. How to cut the work into vertical slices (milestones), each verifiable on its own with its own acceptance criteria, in an order that keeps the tests green.
---

# Slice the plan

The plan is what test writers, implementers and reviewers check against. A plan cut by layer
("first all models, then all endpoints, then the UI") cannot be verified until the end, so a
mistake shows up only at the last step. Cut it by behaviour instead.

## Vertical slices

- Each slice is a narrow but **complete** path through every layer it needs (data, logic,
  interface, tests). When it is done, something works end to end that did not before.
- Each slice is verifiable on its own: name the behaviour in terms a test can check, as its
  acceptance criteria ("cancelling a filled order returns an error and leaves it filled").
- Each slice is small enough for one implementer pass. If a slice needs more than a handful of
  files, split it.
- The first slice is a tracer bullet: the thinnest path that proves the architecture works.
  Later slices widen it.

## Order

1. **Prefactor first.** If the existing code makes the change hard, the first slice reshapes it
   without changing behaviour (existing tests stay green). Make the change easy, then make the
   easy change.
2. Then slices in dependency order: a slice only depends on slices before it.
3. Name, per slice, which invariants it touches and which property test guards each.

## Wide refactors

A mechanical change whose blast radius fans across many files (rename a field used everywhere,
retype a shared value) cannot be one green vertical slice. Sequence it as **expand, migrate,
contract**: add the new form beside the old, move callers over in batches that each stay green,
then delete the old form once nothing uses it.

## What a plan line says

- Files to create or change, only in the run's scope.
- The behaviour, in terms a test can check.
- The invariants touched, and any new invariant.
- What is explicitly out of scope or left for later, so nobody builds it "while they are there".

Keep to the length limit the prompt gives; a quick change is usually one slice. Do not pad the
plan with steps nobody can verify ("clean up", "polish").
