---
name: brainstorm-before-planning
description: Use when a larger change (new feature, product, module or service) needs a complete design agreed with the human before planning. How to work the design tree in rounds of questions until nothing that changes the design is open, and how to write the design.
---

# Brainstorm before planning

A larger change fails on what nobody asked: who it is for, what is in scope, what must always
hold. Brainstorming closes those gaps with the human before anyone plans or builds. It takes as
many rounds as it needs; it ends when the design is complete, not after a fixed number of
questions.

## Facts are yours, decisions are the human's

Read the repo first: its README, docs, existing apps and their stacks, test setup, CI, and
`INVARIANTS.md`. Never ask for a fact you can look up ("Which test runner?" when there is a
`pytest.ini`). Prefer what the repo already uses unless the task says otherwise. What you put to
the human are **decisions**: choices between reasonable options that change the design.

If the task describes several independent subsystems, say so in the first round and propose an
order; design the first one fully and list the rest under `## Out of scope`.

## The design tree

Every decision branches into the decisions that hang off it (the stack decides the test runner,
the data model decides the invariants). The **frontier** is every open decision whose
prerequisites are settled: what you can ask now without guessing an answer you have not heard.

- Ask the **whole frontier** in one round. Do not drip one question per round.
- A question that depends on another question still open in this round belongs to a later round.
- Each answer moves the frontier. Recompute it and ask the next round.

## What a complete design covers

Walk these branches and ask about each that is open and changes the design:

1. **Goal**: what success looks like, and for whom (demo, internal tool, product).
2. **Users and scenarios**: the main flows, step by step.
3. **Scope**: the smallest version that meets the goal; what is explicitly out (cut features
   nobody asked for).
4. **Where it lives**: the folder, how it is started, how it relates to the rest of the repo.
5. **Architecture and stack**: components, languages, frameworks, storage, external services
   (and whether they may be called at all: offline, synthetic data, no secrets). For a real
   choice, name two or three approaches with their trade-off and lead with your pick.
6. **Data model**: the entities, their states and transitions.
7. **Invariants**: the rules that must always hold. Each one becomes a property test.
8. **Analytics and observability**: what is measured, shown or logged, when the task asks for it.
9. **Quality**: tests the gate runs, performance or security needs.
10. **Milestones**: an order of shippable vertical slices.

## How to ask

- Number every question across the round (1, 2, 3 …), grouped under short headings, most
  important group first.
- Each question gives the options and your recommended answer with a reason, worded so that
  "yes" or "agree" accepts it: "Prices: a seeded random walk, or a replay of a bundled CSV?
  (I would pick the random walk: no data files, deterministic tests.)"
- After the questions, list what you already decided, so the human can correct it.

## When to stop asking

Stop when the frontier is empty: every branch above is answered, found in the repo, or decided
by you and listed under assumptions, and no answer opened a new question. Nothing is silently
assumed.

## Before you send the design

Read it once more: no `TBD` or vague requirement, no section that contradicts another, no
requirement with two readings (pick one and state it), every invariant testable, every
milestone with its own acceptance criteria.

## If the human approves without answering

Decide the open points yourself, choosing the option you recommended, list them under
`## Decisions and assumptions`, and write the design.
