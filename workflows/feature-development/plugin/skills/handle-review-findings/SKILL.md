---
name: handle-review-findings
description: Use when a fix round starts from review findings, a failed gate or the human's change request. How to check each finding against the code before acting, fix in the right order, push back with evidence when a finding is wrong, and report per finding ID.
---

# Handle review findings

Findings are claims to check, not orders to follow and not compliments to return. The reviewer
re-checks every finding by its ID after your round, so each one needs a real answer.

## Precedence

1. What the human wrote (answers to `QUESTION:` lines, notes, change requests) wins over the
   findings and over your own judgement.
2. The specification, the approved plan and the invariants come next.
3. The reviewer's suggestions on *how* to fix are suggestions; the problem it names is what
   matters.

## For each finding

1. **Read** it completely, with its file and line.
2. **Restate** the requirement in your own words. If you cannot, read the specification and the
   code around it until you can.
3. **Verify** it against the code: reproduce it with a test or a command where you can. Is it
   true for this codebase, this stack, this specification?
4. **Decide**: fix it, or push back.

## Order of work

Read all findings before changing anything: they are often related, and fixing one in isolation
can break another. Then fix in this order: broken behaviour, broken invariants and security
first, then missing tests, then the rest. Run the relevant test after each fix and the gate's
whole test command at the end. For a failure whose cause is not obvious, use the
`feature-development:diagnose-before-fixing` skill.

## Pushing back

Push back when the finding is technically wrong: it contradicts the specification or the
human's answer, breaks existing behaviour, asks for something nobody uses (search the repo for
callers first), or misreads the code. Push back with evidence (a test, a command output, the
line of the specification), not with opinion, and leave the code as it is for that finding.
If it needs a decision only the human can make, say so plainly in the reply.

Never weaken a test, relax an invariant or silence a check to make a finding go away.

## No performative replies

No "you are right", "great catch", thanks or apologies. State what changed. If you pushed back
in an earlier round and were wrong, say it in one line and fix it.

## Report per finding

Keep the reply format of the prompt (summary line first, one line per file with the finding
IDs it addresses). Make sure every finding ID appears in the reply, so the re-review can match
it; for one you did not change, add a line `F2 not changed: <why, with the evidence>`. Then the
test command you ran and its result.
