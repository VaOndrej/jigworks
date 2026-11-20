---
name: brainstorm-before-planning
description: Use when a larger change (new feature, product, module or service) needs a complete design agreed with the human before planning. How to run several rounds of questions until nothing that changes the design is open, and how to write the design.
---

# Brainstorm before planning

A larger change fails on what nobody asked: who it is for, what is in scope, what must always
hold. Brainstorming closes those gaps with the human before anyone plans or builds. It takes as
many rounds as it needs; it ends when the design is complete, not after a fixed number of
questions.

## Before you ask

Read the repo first: its README, docs, existing apps and their stacks, test setup, CI, and
`INVARIANTS.md`. Never ask what the repo already answers ("Which test runner?" when there is a
`pytest.ini`). Prefer what the repo already uses unless the task says otherwise.

## What a complete design covers

Walk through these and ask about each one that is open and changes the design:

1. **Goal**: what success looks like, and for whom (demo, internal tool, product).
2. **Users and scenarios**: the main flows, step by step.
3. **Scope**: the smallest version that meets the goal; what is explicitly out.
4. **Where it lives**: the folder, how it is started, how it relates to the rest of the repo.
5. **Architecture and stack**: components, languages, frameworks, storage, external services
   (and whether they may be called at all: offline, synthetic data, no secrets).
6. **Data model**: the entities, their states and transitions.
7. **Invariants**: the rules that must always hold (balances never negative, no transition out
   of a terminal state, totals add up). Each one becomes a property test.
8. **Analytics and observability**: what is measured, shown or logged, when the task asks for it.
9. **Quality**: tests the gate runs, performance or security needs.
10. **Milestones**: an order of shippable slices.

## How to ask

- Group questions under short headings; most important group first.
- Each question offers options and your pick with a reason: "Prices: a seeded random walk, or a
  replay of a bundled CSV? (I would pick the random walk: no data files, deterministic tests.)"
- Ask everything that is open in this round at once; do not drip one question per round.
- After the questions, list what you already decided, so the human can correct it.

## When to stop asking

Stop when every item above is either answered, found in the repo, or decided by you and listed
under assumptions, and no answer opened a new question. Then write the design.

## If the human approves without answering

Decide the open points yourself, choosing the option you recommended, list them under
`## Decisions and assumptions`, and write the design.
