# T17 · Second workflow `bugfix-with-repro`

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no (the parallel demo falls back to two `feature-development` sessions) |
| Depends on | T05 |
| Human time | 5 min |

## Goal

A second, smaller workflow so the demo can show two sessions in parallel, each with its own workflow (feature + customer bug).

## Acceptance criteria

- [ ] `workflows/bugfix-with-repro/`: reproduce → failing test → approve repro (`interrupt`) → fix → review → gate → approve PR (`interrupt`) → open PR. Reuses steps from `feature-development` where it can.
- [ ] A synthetic bug in `sample-repo` (rounding before fees in P&L) plus a synthetic export in `sample-repo/fixtures/` to reproduce it.
- [ ] `uv run pytest workflows/bugfix-with-repro` with a fake adapter covers the happy path and a rejected repro.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
