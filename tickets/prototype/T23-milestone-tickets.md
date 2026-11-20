# T23 · Milestones as tickets, review every few tickets

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-1` |
| Size | L |
| Demo critical path | no |
| Depends on | T22 |
| Human time | — |

## Goal

A large change (a new product, many modules) is not built in one `implement` step and one review
of the whole diff: that is where the fix loop stops converging (seen in the first real
brainstorming run, 2026-11-20: 60 files, review FAIL four times). The plan splits the work into
tickets, each with its own acceptance criteria, and the workflow builds them one after another.
The independent review runs after a group of tickets that makes sense to review together (a
milestone), not after each one and not once at the end. The same workflow runs from the hub,
so the hub's run view must show the tickets too.

## Acceptance criteria

- [ ] `plan` (and `plan_from_design`) returns the work as tickets in a machine-readable block: ID, title, acceptance criteria, files it may touch, dependencies, and the milestone it belongs to. The `slice-the-plan` skill already describes vertical slices; the format is new.
- [ ] `approve_plan` shows the tickets and milestones; the human can merge, split or reorder them with Request changes.
- [ ] The graph loops over tickets: `write_tests → implement` per ticket (the tests from that ticket's criteria), a git commit per ticket.
- [ ] `review → fix` (with T22's escalation) runs at the end of each milestone, on the diff of that milestone, against the criteria of its tickets; the gate runs the whole test suite at the same point.
- [ ] Progress (% of plan) counts tickets inside the implement phase; the extension's graph and Now card show "ticket 3 of 9 · milestone 1 of 3".
- [ ] Runs survive a new process between tickets (checkpoint holds the ticket list and the current index).
- [ ] The hub's run view (apps/hub-web) shows the ticket list with each ticket's state from the events. Needs a contract change (a ticket ID on node events, or a new event field): propose it in `packages/contracts/` first.
- [ ] A test with the fake adapter: 3 tickets in 2 milestones, the second milestone's review fails once and passes after one fix.

## Evidence

(none yet)
