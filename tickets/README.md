# Tickets

Work items live here as Markdown files, one file per ticket, grouped by plan:

- [`prototype/`](prototype/): the case study prototype; the overview, build order and cut line are in [`docs/plan.md`](../docs/plan.md).

## Conventions

- File name: `<ID>-<slug>.md`, e.g. `T05-feature-development-workflow.md`. IDs never change; `T` = build ticket, `P` = presentation ticket.
- Each ticket has a field table (Status, Owner, Label, Size, Demo critical path, Depends on, Human time), **Goal**, **Acceptance criteria** as a checklist, and **Evidence**.
- Status values: `todo` → `in-progress` → `review` → `done` (or `blocked`, with the reason in Notes).
- A ticket moves to `done` only when every acceptance criterion is ticked and the **Evidence** section holds the proof: command output, Playwright screenshots at 1440 px for visual work, or links.
- Commits reference the ticket ID in the subject or body (`Refs T05`).
