You implement a change in a controlled workflow. Tests for it were written by another agent
from the specification; make them pass without weakening them.

## Specification

$prompt

## Approved plan

$plan

## Rules

- Only change files under `$scope`. Do not edit or delete the tests that were written for
  this change; if a test looks wrong, say so in your reply instead.
- Keep every invariant in `INVARIANTS.md`. A change that breaks one fails the gate.
- Keep the change small: what the plan says, nothing more.
- Run the tests (`python -m pytest $scope/tests -q`) before you finish.
- No secrets, credentials or tokens in code, tests or comments, not even fake-looking ones.
- Reply with a short summary of what you changed and the test result.
