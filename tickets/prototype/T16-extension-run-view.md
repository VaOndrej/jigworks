# T16 · Extension run view: graph position, % of plan, approvals

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-2` |
| Size | M |
| Demo critical path | yes |
| Depends on | T06, T09 |
| Human time | 10 min |

## Goal

While a session runs, the engineer sees where it is in the workflow graph and how far along it is, as a share of the whole plan rather than a time estimate (mockup "VS Code — running session").

## Acceptance criteria

- [ ] The run view draws the workflow graph from `jigworks graph` JSON (read-only, same shape as the hub's graph view) and highlights nodes live from runner events: done and approved green, the current node blue and enlarged with a "NOW" marker, nodes that need the human amber dashed, future nodes dimmed; fix loops show the attempt number.
- [ ] A progress block shows `progress` from the runner as "48 % of the plan", the current step ("step 5 of 9 · review, attempt 2"), and a marker for where the next human approval will happen.
- [ ] Activity list of the latest events and a "Next for you" card; at an interrupt it becomes Approve / Request changes (comment box) / Reject, with links to the diff, the audit log and the test report, and resumes the run.
- [ ] "Agent output" tab, off by default: live text and tool calls of the current node from `stream-json`, with "Follow live".
- [ ] Tokens and cost of the session are shown and update live.
- [ ] Screenshot or recording of the real extension in VS Code with two sessions: one running with the graph and %, one waiting for approval. Playwright screenshots of the standalone run view at **390 px and 1440 px**.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
