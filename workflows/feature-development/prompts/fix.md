Your change needs another iteration.

## What is wrong

$problem

$context

## Rules

- Fix the cause, not the symptom. Do not weaken, skip or delete tests to make them pass, and
  do not relax an invariant (`INVARIANTS.md`, the design's `## Invariants`).
- Only change files in $scope.
- If a secret or credential was flagged, remove it; do not obfuscate it.
- Run the tests the gate runs ($tests) before you finish.

## Reply format

What you changed and why (one line per file), and the test result. The reviewer gets this reply.
