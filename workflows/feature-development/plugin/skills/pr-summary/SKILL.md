---
name: pr-summary
description: Use when writing the run summary that becomes the pull request description and the audit-log entry. What changed, the evidence that it works, and how risky it is to merge, in a few lines.
---

# PR summary

The human who merges reads this before the diff. It has to say, in a few lines, what changed,
why they can believe it works, and what could go wrong. No preamble, no praise, no repetition
of the task.

## What goes in

1. **What changed**: the behaviour, in the user's or caller's terms, and where it lives (the
   module or folder, not every file). If the shape of the code changed, one short tree or call
   path says more than a sentence.
2. **Evidence**: the gate result as it was reported (tests passed or failed, invariants checked,
   property tests run). Quote numbers from the gate report; do not invent or round them. If
   something was not checked, say so.
3. **How it got there**: the number of fix loops, and the kind of problem they fixed when it
   matters to a reviewer (an invariant that broke and was restored is worth knowing).
4. **Merge danger**:
   - **Door**: two-way (easy to revert: new code, a feature behind a flag) or one-way (hard to
     undo: data migrations, deleted data, changed public interfaces, new external calls).
   - **Blast radius**: who or what is affected if it is wrong, in one or two words (one module,
     every order, the public API).
5. **What a human should still look at**: decisions the agents made on their own (assumptions
   in the plan or design), findings that were pushed back, anything the gate does not check.

## Rules

- Keep to the line limit of the prompt. Cut words, not facts.
- Only state what the inputs in front of you show (the task, the plan or design, the gate
  report, the run numbers). Never claim a check that is not in the gate report.
- Plain Markdown that renders on any code host: short bullets or short lines, no HTML.
- No secrets, tokens, absolute home paths or personal data.
