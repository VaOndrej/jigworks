# T09 · Extension UI: workflows, sessions, new-session prompt

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-2` |
| Size | L |
| Demo critical path | yes |
| Depends on | T08 |
| Human time | 10 min |

## Goal

The engineer starts work from VS Code and runs several sessions in parallel, each with its own workflow (design.md §7, mockup "VS Code — new session"). Example: a feature is being implemented, a customer bug comes in, the engineer starts a second session for the bug and switches between them.

## Acceptance criteria

- [ ] Sidebar view with two sections: **Workflows** (local and imported workflows; the selected one is the active workflow for a new session) and **Sessions** (every running or waiting session with title, workflow, current node and progress %; a session waiting for review shows a "Review" badge instead of its %).
- [ ] "+ New session" opens an editor-area panel with the prompt in the middle: task text, attachments from the workspace, the active workflow (models come from the workflow, no model picker) and a preview of its steps, permissions and typical cost. "Start session" starts a run in its own worktree.
- [ ] Each session is its own editor tab; clicking a session in the sidebar or a tab switches to it. At least two sessions run at the same time without blocking each other.
- [ ] Status bar shows "N sessions running · M waiting for you"; a session that reaches an interrupt raises a VS Code notification.
- [ ] The webview React app also runs standalone with recorded events; Playwright screenshots at **390 px and 1440 px** attached as evidence.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
