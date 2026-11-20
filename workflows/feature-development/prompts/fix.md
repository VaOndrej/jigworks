Your change needs another iteration.

## What is wrong

$problem

$context

$note

## Rules

Use the `feature-development:handle-review-findings`, `feature-development:diagnose-before-fixing`
and `feature-development:verify-before-done` skills.

- Fix every open finding, not only the first ones; the reviewer checks each of them by its ID.
- Fix the cause, not the symptom. Do not weaken, skip or delete tests to make them pass, and
  do not relax an invariant (`INVARIANTS.md`, the design's `## Invariants`).
- Only change files in $scope.
- If a secret or credential was flagged, remove it; do not obfuscate it.
- Run the tests the gate runs ($tests) before you finish.
- If something only the human can do blocks you (a download or command that is denied, an
  approval, a decision outside the spec), do not work around it and do not repeat yourself in
  later rounds: write one line per item, starting with `NEEDS HUMAN:`, with the exact command or
  question. The run stops and shows these lines to the human.

## Reply format

Start with one line that says what this round changed, in under 100 characters (the human sees
it in the round-by-round report). Then what you changed and why (one line per file, with the
finding IDs it addresses), and the test result. The reviewer gets this reply.
