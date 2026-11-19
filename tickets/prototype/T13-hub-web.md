# T13 · hub-web (Vite + React + React Flow)

| Field | Value |
|---|---|
| Status | todo |
| Owner | hub |
| Label | `milestone-3` |
| Size | L |
| Demo critical path | no (below the cut line) |
| Depends on | T12 |
| Human time | — |

## Goal

Visual spec: [`docs/mockups/jigworks-ui.html`](../../docs/mockups/jigworks-ui.html).

Three tabs, as in the mockups: **Workflows** (overview with weekly numbers, workflow cards, live sessions, recent releases; Python editor with a Code / Graph toggle (no separate graph button), new file and folder from templates, `[models]` in `workflow.toml`, a "Connect GitHub repo" source bar marked Planned, publish; read-only `get_graph()` graph), **Runs & analytics** (key numbers, cost per day by token type, version comparison, runs table, run detail with the audit trail) and **Non-coding teams** (text tab describing the direction).

## Acceptance criteria

- [ ] The editor has a "Show graph" CTA that compiles the current code in Vercel Sandbox, calls `get_graph()` and switches the view to the React Flow graph. The graph is only computed on Vercel, never in the API process and never on the client.
- [ ] Human-delta numbers and the human-delta box in run detail are shown with a "Planned" label and recorded sample data; they are not computed (design.md §8).
- [ ] Playwright e2e on the preview URL; screenshots at **390 px and 1440 px** for Workflows, the editor, the graph and Runs & analytics.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
