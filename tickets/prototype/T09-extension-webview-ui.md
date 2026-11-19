# T09 · Extension UI: workflows, sessions, new-session prompt

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-2` |
| Size | L |
| Demo critical path | yes |
| Depends on | T08 |
| Human time | 10 min |

## Goal

Visual spec: [`docs/mockups/jigworks-ui.html`](../../docs/mockups/jigworks-ui.html).

The engineer starts work from VS Code and runs several sessions in parallel, each with its own workflow (design.md §7, mockup "VS Code — new session"). Example: a feature is being implemented, a customer bug comes in, the engineer starts a second session for the bug and switches between them.

## Acceptance criteria

- [x] Sidebar view with two sections: **Workflows** (local and imported workflows; the selected one is the active workflow for a new session) and **Sessions** (every running or waiting session with title, workflow, current node and progress %; a session waiting for review shows a "Review" badge instead of its %).
- [x] "+ New session" opens an editor-area panel with the prompt in the middle: task text, attachments from the workspace, the active workflow (models come from the workflow, no model picker) and a preview of its steps, permissions and typical cost. "Start session" starts a run in its own worktree.
- [x] Each session is its own editor tab; clicking a session in the sidebar or a tab switches to it. At least two sessions run at the same time without blocking each other.
- [x] Status bar shows "N sessions running · M waiting for you"; a session that reaches an interrupt raises a VS Code notification.
- [x] The webview React app also runs standalone with recorded events; Playwright screenshots at **1440 px** attached as evidence.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Code: `clients/vscode/webview/` (React: `Sidebar.tsx`, `NewSession.tsx`, `RunView.tsx`, `Graph.tsx`,
`styles.css` from the mockup's colours with VS Code theme variables taking over inside VS Code),
`src/shared/session.ts` (pure fold RunEvents → view model, shared by host and webview),
`webview/standalone.tsx` (the same components in a VS Code-like frame, replaying
`packages/contracts/fixtures/runs/*.jsonl`).

`pnpm --filter vscode test:ui` (Playwright, 1440 × 900):

```
  ✓  1 webview.ui.spec.ts › new session: prompt in the middle, workflow from the sidebar, models from the release
  ✓  2 webview.ui.spec.ts › running session: NOW on implement, % of plan, live agent output
  ✓  3 webview.ui.spec.ts › review: Review badge instead of %, Approve / Request changes / Reject
  ✓  4 webview.ui.spec.ts › finished run with fix loops: fix node done, progress at 100 %
  4 passed (1.1s)
```

Screenshots (1440 px):
- `e2e/local/screenshots/vscode-new-session-1440.png`: sidebar (workflows, three sessions:
  one at 30 %, one with the Review badge, one done), prompt in the middle, two attachments,
  "Models are set by the workflow release: Sonnet 5, write tests and summary on Haiku 4.5", the
  step preview with both approvals dashed amber, permissions, typical cost from finished runs.
- `e2e/local/screenshots/vscode-running-session-1440.png`, `vscode-review-1440.png`,
  `vscode-fix-loops-activity-1440.png` (run view, see T16).

In the real VS Code (`pnpm --filter vscode test`, T08): two sessions run at the same time; each
opens its own panel (`openSession` → one `WebviewPanel` per runId, titled "<title> · <%>" or
"· Review"); both interrupts raised a notification ("… needs your review before the PR", with
Open), and the status bar read "0 running · 2 waiting for you" while both waited.

## Notes

- Attachments are workspace paths picked with the VS Code file dialog. They are appended to the
  prompt ("Attached files (read them first): …"); the agent reads them in its worktree, which has
  the same tree. Files that are not committed are not in the worktree.
- "Typical cost" is the median API-equivalent cost of finished sessions of the same release known
  to this machine; with none it says so. The hub's analytics would be the better source (T15+).
- The standalone screenshots are not real VS Code. Real VS Code screenshots are for the human in
  the morning (two-agent-build.md §10.6).
