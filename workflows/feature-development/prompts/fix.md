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
- Run the tests the gate runs ($tests) and its scanners, $scanners, before you finish.
- Do not silence a scanner, a type check or a test (`# nosec`, `noqa`, `type: ignore`, `skip`,
  `xfail`, …): fix the cause. If it really is a false positive, keep the marker and write
  `NEEDS HUMAN: accept the suppression in <path>` with why; the gate rejects it until then.
- Leave no scratch or debug files in the repo (one-off scripts, dumps, `dbg_*.py`): use a temporary
  directory outside it, or delete them with `git rm` / Write before you finish. Never hide them
  with a `.gitignore` rule.
- If something only the human can do blocks you (a download or command that is denied, an
  approval, a decision outside the spec), do not work around it and do not repeat yourself in
  later rounds: write one line per item, starting with `NEEDS HUMAN:`, with the exact command or
  question. The run stops and shows these lines to the human.
- What the human already decided (the section "From the human", the agreements in the spec)
  is final: act on it and never ask for it again with `NEEDS HUMAN:`. When the human accepted
  or waived a finding, leave it as it is. If the human's answers leave nothing to change,
  change nothing and say so in the first line: the change then goes back to the check.
- Protected files and suppressions are accepted only by the human pressing Approve when the run
  asks; a comment that agrees is not an acceptance. If the gate still rejects them, never say
  they were accepted: write `NEEDS HUMAN: press Approve to accept <path>` (only Approve does it).
- A rule of the repo (AGENTS.md, CLAUDE.md, CONTRIBUTING) that needs a change outside the scope
  ($scope), e.g. a build log at the root, is the human's job: mention it once at the end of
  your reply as a note for the human. It is not a finding and not a QUESTION.

## Reply format

Start with one line that says what this round changed, in under 100 characters (the human sees
it in the round-by-round report). Then what you changed and why (one line per file, with the
finding IDs it addresses), and the test result. The reviewer gets this reply.
