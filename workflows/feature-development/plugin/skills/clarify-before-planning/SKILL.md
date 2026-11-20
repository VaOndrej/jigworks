---
name: clarify-before-planning
description: Use when planning a change and the task leaves behaviour, scope or an invariant open. How to decide whether to ask the human, and how to ask so one round is enough.
---

# Clarify before planning

The plan is agreed with a human before anyone writes tests or code. A wrong guess here costs a
whole run; a good question costs one round.

## Ask, or decide yourself?

Ask only when **all** of these hold:

- the answer changes the plan (which files, what behaviour, which invariant);
- you cannot find it in the code, the tests, the docs or the git history;
- two reasonable readings of the task lead to different results.

Everything else you decide, and you state the decision in the plan ("Assumption: …").

## How to ask

- At most 5 questions, numbered, most important first.
- Each question is answerable in one line. Offer the options you see and say which you would
  pick: "Round half up or half to even? (I would pick half to even, like the existing P&L.)"
- No questions about style, naming or anything the repo already decides.

## After the answers

Fold every answer into the plan. If an answer opens a new real ambiguity, ask again; otherwise
write the plan. Do not repeat questions the human already answered.
