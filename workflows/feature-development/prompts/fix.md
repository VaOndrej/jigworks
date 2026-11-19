Your change needs another iteration.

$problem

## Rules

- Fix the cause, not the symptom. Do not weaken, skip or delete tests to make them pass, and
  do not relax an invariant in `INVARIANTS.md`.
- Only change files under `$scope`.
- If a secret or credential was flagged, remove it; do not obfuscate it.
- Run the tests (`python -m pytest $scope/tests -q`) before you finish.
- Reply with what you changed and why.
