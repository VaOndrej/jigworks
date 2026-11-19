# T13 · hub-web (Vite + React + React Flow)

| Field | Value |
|---|---|
| Status | done |
| Owner | hub |
| Label | `milestone-3` |
| Size | L |
| Demo critical path | no (below the cut line) |
| Depends on | T12 |
| Human time | — |

## Goal

Visual spec: [`docs/mockups/jigworks-ui.html`](../../docs/mockups/jigworks-ui.html).

Three tabs, as in the mockups: **Workflows** (overview with weekly numbers, the workflow table with step shape, live sessions with the Review badge, recent releases; Python editor with a Code / Graph toggle (no separate graph button), new file and folder from templates, `[models]` in `workflow.toml`, a "Connect GitHub repo" source bar marked Planned, publish; read-only `get_graph()` graph), **Runs & analytics** (key numbers, cost per day by token type, version comparison, runs table, run detail with the audit trail) and **Non-coding teams** (text tab describing the direction).

## Acceptance criteria

- [x] The editor's Code / Graph toggle switches to the React Flow graph from `POST /api/workflows/{id}/validate` (Vercel Sandbox). The graph is only computed on Vercel, never in the API process and never on the client. No AI edit box.
- [x] A password screen guards the whole hub; a correct `HUB_PASSWORD` sets an HTTP-only cookie. Playwright reads the password from the environment.
- [x] Human-delta numbers and the human-delta box in run detail are shown with a "Planned" label and recorded sample data; they are not computed (design.md §8).
- [x] Playwright e2e on the preview URL; screenshots at **1440 px** for Workflows, the editor, the graph and Runs & analytics.

## Notes

- **Stack:** React 19, `@xyflow/react` 13 for the graph (planned path as one column, `fix` to the side, conditional edges dashed, PASS/FAIL and approve/request changes/reject labels, run overlay), CodeMirror 6 for Python with the mockup's colours, `smol-toml` to read `[models]`. Types come type-only from `packages/contracts/src/generated/types.ts` (tsconfig `paths`), so the Vercel build (`vite build`) does not need a built contracts package; `tsc -b` runs in `pnpm --filter @jigworks/hub-web test`.
- **Local stack** for screenshots: uvicorn (hub-api) behind Vite's `/api` proxy, the same routing as `vercel.json`, on a fresh seeded database; Sandbox is mocked there with the contract graph. Not `vercel dev` (decision in the build log).
- **Deviations from the mockup, on purpose:** the header's `team: trading-platform` became **Sign out** (there are no teams; the hub needs a logout). The seed has one workflow (the contracts have one), not three. "Merged" is shown as **PR opened** (the hub does not know about merges until human-delta capture exists). The version table shows the contract's columns plus gate pass on the first try and median time to PR from the hub-only overview; "Worked first time" is Planned sample data everywhere. Audit-trail times are UTC.
- **Non-coding teams text** was written by the agent from design.md §10 (CV screening, contract review, incident write-ups, base workflow + department variant). design.md says Ondřej describes the use cases: please rewrite or confirm.

## Evidence

`pnpm verify:hub --preview https://jigworks-4ssz529wq-<team>.vercel.app` (19 Nov 2026, 22:06 UTC):

```
== hub-web typecheck + unit tests
      Tests  9 passed (9)
== Playwright on localhost (1440 px)
  6 passed (5.3s)
== API transcript against the preview
preview-api: OK (https://jigworks-4ssz529wq-<team>.vercel.app)
== Playwright on the preview (1440 px)
  ✓  1 e2e/hub/hub.spec.ts:22:1 › password screen guards the hub and sets an HTTP-only cookie (1.6s)
  ✓  2 e2e/hub/hub.spec.ts:38:1 › Workflows: weekly numbers, workflow table with step shape, live sessions, releases (1.8s)
  ✓  3 e2e/hub/hub.spec.ts:50:1 › Editor: Python code, files from templates, GitHub source planned, models in workflow.toml (4.8s)
  ✓  4 e2e/hub/hub.spec.ts:81:1 › Graph: the Code/Graph toggle renders get_graph() from Sandbox with a live overlay (1.8s)
  ✓  5 e2e/hub/hub.spec.ts:103:1 › Runs & analytics: key numbers, cost per day, planned outcomes, versions, runs, audit trail (1.6s)
  ✓  6 e2e/hub/hub.spec.ts:124:1 › Non-coding teams: text tab (733ms)
  6 passed (12.7s)
verify:hub passed
```

What the suite checks: wrong password → "Wrong password.", right password → `jigworks_session` cookie with `httpOnly: true`, not readable from `document.cookie`, value ≠ password; workflow row with `stable 1.3.0` and the shape "Agent steps, 2 human reviews, 1 gate"; Review badge in Live now; new file `steps/security_scan.py` from the node-function template, autosave, Validate → "10 nodes", no AI/prompt textbox; Graph toggle → 12 React Flow nodes incl. every workflow node, overlay of the live run highlights exactly one running node; Runs & analytics key numbers with "API equivalent", cost bars, outcomes panel "PLANNED" + "Sample data", version table, run_fd_0002 audit trail with "requested changes" and a PLANNED human-delta box.

Screenshots (1440 px), preview: [workflows](../../e2e/hub/screenshots/preview-workflows-1440.png) · [editor](../../e2e/hub/screenshots/preview-editor-1440.png) · [new file](../../e2e/hub/screenshots/preview-editor-new-file-1440.png) · [graph](../../e2e/hub/screenshots/preview-graph-1440.png) · [runs & analytics](../../e2e/hub/screenshots/preview-runs-1440.png) · [non-coding](../../e2e/hub/screenshots/preview-non-coding-1440.png) · [login](../../e2e/hub/screenshots/preview-login-1440.png). Localhost: the same names with `local-`.
