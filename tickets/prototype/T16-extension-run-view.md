# T16 · Extension run view: graph position, % of plan, approvals

| Field | Value |
|---|---|
| Status | review |
| Owner | local |
| Label | `milestone-2` |
| Size | M |
| Demo critical path | yes |
| Depends on | T06, T09 |
| Human time | 10 min |

## Goal

Visual spec: [`docs/mockups/jigworks-ui.html`](../../docs/mockups/jigworks-ui.html).

While a session runs, the engineer sees where it is in the workflow graph and how far along it is, as a share of the whole plan rather than a time estimate (mockup "VS Code — running session").

## Acceptance criteria

- [x] The run view draws the workflow graph from `jigworks graph` JSON (read-only, same shape as the hub's graph view) and highlights nodes live from runner events: done and approved green, the current node blue and enlarged with a "NOW" marker, nodes that need the human amber dashed, future nodes dimmed; fix loops show the attempt number.
- [x] A progress block shows `progress` from the runner as "48 % of the plan", the current step ("step 5 of 9 · review, attempt 2"), and a marker for where the next human approval will happen.
- [x] Activity list of the latest events and a "Next for you" card; at an interrupt it becomes Approve / Request changes (comment box) / Reject, with links to the diff, the audit log and the test report, and resumes the run.
- [x] "Agent output" tab, off by default: live text and tool calls of the current node from `stream-json`, with "Follow live".
- [x] Tokens and cost of the session are shown and update live.
- [ ] Screenshot or recording of the real extension in VS Code with two sessions: one running with the graph and %, one waiting for approval. Playwright screenshots of the standalone run view at **1440 px**.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`. Status `review`: the last criterion needs a real
VS Code screenshot, which two-agent-build.md §10.6 leaves to the human. The standalone half is done.

Code: `clients/vscode/webview/RunView.tsx`, `Graph.tsx`, `src/shared/session.ts`, `src/shared/cost.ts`.
The graph is the `GraphJSON` from `jigworks inspect` / `jigworks graph`: the planned path in one
row, off-path steps (`fix`) below with FAIL edges from review and gate.

`pnpm --filter vscode test:ui` (Playwright, 1440 px, recorded runs):

```
  ✓  2 › running session: NOW on implement, % of plan, live agent output
  ✓  3 › review: Review badge instead of %, Approve / Request changes / Reject
  ✓  4 › finished run with fix loops: fix node done, progress at 100 %
```

- `e2e/local/screenshots/vscode-running-session-1440.png` (run_fd_0007): plan / approve plan
  (with approver and time) / write tests green, `implement` blue, enlarged, NOW marker; "30 % of
  the plan done · step 4 of 9 · implement · 0 fix loops so far"; amber tick "your review ≈ 86 %";
  Agent output tab with Follow live; "Next for you" preview; tokens and API-equivalent cost.
- `e2e/local/screenshots/vscode-review-1440.png` (run_fd_0005): `approve PR` amber dashed with a
  YOU marker; Review badge in the sidebar and the tab; decision card with diff stat and commit,
  "Test report: gate PASS (4/4 checks)", links Diff (worktree) / Audit log, comment box,
  Approve / Request changes (enabled once a comment is typed) / Reject.
- `e2e/local/screenshots/vscode-fix-loops-activity-1440.png` (run_fd_0002): 100 %, `fix` "3 loops",
  Activity tab with the review FAIL, gate FAIL and "requested changes" lines.
- Live: the extension test (T08) drives Approve and Request changes through the same commands the
  buttons post (`decide` → `jigworks approve|request-changes`), and the run resumes.

## Notes

- **Open:** real VS Code screenshot with two sessions (human, morning). Suggested: open this repo
  in VS Code with the installed `.vsix`, set `"jigworks.adapter": "fake"` and
  `"jigworks.fakeScript"` to a script, start two sessions.
- Fix-loop attempts show as "try N" on the running node and "✗ failed · try N" on failed
  attempts; the fix node shows the loop count.
- Cost is computed in the webview from `packages/contracts/fixtures/prices.json` (bundled), the
  same price table the hub seeds; the CLI cost is not shown.
