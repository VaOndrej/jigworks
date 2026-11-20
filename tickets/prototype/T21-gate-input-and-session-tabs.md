# T21 · Gate input, honest gate states, session tabs, a run that looks alive

| Field | Value |
|---|---|
| Status | review |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no |
| Depends on | T16, T20 |
| Human time | 5 min |

## Goal

The run view and the editor tabs tell the truth at a glance: text typed at a gate is never lost
by an Approve, a gate where changes were requested never looks approved, every session tab shows
its state, and a step that is working looks like it is working. Extension only: no runner or
contract change.

## Acceptance criteria

### 1. Gate decision: typing text never approves
- [x] Enter in the gate textarea sends Request changes with the text (non-empty only); Shift+Enter is a newline; no submit during IME composition; Enter on an empty field does nothing.
- [x] Approve is disabled while the field has text; a hint says so; Request changes is the primary button when there is text, Approve when it is empty.
- [x] After a decision is sent, the three buttons and the textarea are disabled until the state changes; Reject works regardless of the text.
- [x] The text is cleared when it is sent, and every new gate (new interrupt) starts with an empty, enabled field.

### 2. Graph: Request changes does not look approved
- [x] A gate whose latest decision is `request_changes` is shown as "↺ changes requested · user, time", not green ✓; `reject` is red; only `approve` is green.
- [x] A new attempt of the gate (`node_status` running / waiting) clears the old decision; the latest `review_decision` wins.
- [x] The progress card's "your approval ≈ %" marker and the graph edges do not count such a gate as done.
- [x] Legend entry for the new state.

### 3. Session tabs
- [x] Per-state tab icon (`panel.iconPath`): running, waiting for you, failed, done, stopped; set only when the state changes.
- [x] Title: the session title cut on a word boundary (~24 chars + "…"), then "· plan" / "· review" / "· brainstorm" / "· your turn" when waiting, the current action or step when running (% only when ≥ 5 %), "· failed", "· done".
- [x] Tooltip: **not possible**. `WebviewPanel` has only `title` and `iconPath` (no tooltip or description) in `@types/vscode` 1.100; VS Code's tab hover shows the title.
- [x] Clicking the status bar item reveals the first session that is waiting for you (New session when none).

### 4. A working agent looks alive
- [x] Running node: subtle pulse (off with `prefers-reduced-motion`) and an elapsed timer that ticks every second.
- [x] "Now" card while a step runs: step, attempt, elapsed; latest action in plain words + "x s ago"; the last 5 actions (newest on top, fade in); files touched, tool calls, output tokens for this step; the next review below it, smaller.
- [x] Liveness: one extension-host timer (10 s) reads `.jigworks/runs/<runId>/lock` and checks the PID; the webview shows "Working · m:ss", or "Agent stopped · last activity hh:mm" + Resume only when the PID is definitely gone; missing/unreadable lock → Working.
- [x] Progress bar: an indeterminate shimmer on the running step's segment.
- [x] Event times (`at`) stored in the fold; one ticking `setInterval` in the webview, cleared on unmount.

### Tests and proof
- [x] Unit tests: session fold (request_changes gate), tab title/icon state (incl. word-boundary cut and a Czech title), tool_use → plain language, liveness state.
- [x] Playwright (1440 px): gate with text typed, graph with changes requested, running step with the Now card.
- [x] `pnpm verify:local` passes.
- [ ] Real VS Code tab chrome seen on screen (unverified visually: see Evidence).

## Out of scope / follow-ups

- **Partial messages from `claude -p`.** `stream-json` emits a `tool_use` only once the whole block
  is generated, so a real run can be silent for minutes (`write_tests` emitted nothing from
  13:49:41 to 13:55:07). Passing `--include-partial-messages` in
  `runner/jigworks_runner/adapters/claude.py` would stream text while the model writes. That is a
  runner change and may need a contract change (a delta event kind); proposed in the build log,
  not done here.

## Evidence

```
$ pnpm --filter vscode test:unit
  T21 units  (session fold, tool_use → plain language, tab title and icon, liveness, counters)
  22 passing (7ms)

$ pnpm verify:local
116 passed, 1 skipped, 17 warnings in 247.83s (0:04:07)     # runner, workflows, sample-repo
4/4 bugs caught by the property tests
30 passing (12s), 1 pending                                  # @vscode/test-electron, incl. the 22 units
13 passed (3.0s)                                             # Playwright, standalone webview, 1440 px
== verify:local OK
```

Screenshots (1440 px, standalone webview replaying synthetic fixtures in
`clients/vscode/test-fixtures/runs/`):

- Gate with text typed (Approve disabled, Request changes primary, hint):
  `e2e/local/screenshots/vscode-gate-text-typed-1440.png`
- Graph after Request changes on the plan gate (`↺ changes`, plan `try 2`, legend):
  `e2e/local/screenshots/vscode-gate-changes-requested-1440.png`
- Running step with the Now card, heartbeat, shimmer:
  `e2e/local/screenshots/vscode-running-now-card-1440.png`

Tabs: **not verified visually in real VS Code.** The tab strip in the screenshots is the
standalone harness drawing `tabChrome()` with the real SVGs from `media/`, not VS Code's own
chrome. In the real extension host, `@vscode/test-electron` asserts the title and icon state set
on the actual `WebviewPanel` (waiting → `Task A: write notes · your turn` + `waiting`; finished →
`· done` + `done`), plus the unit tests for every state.
