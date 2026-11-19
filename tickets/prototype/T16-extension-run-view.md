# T16 · Extension run view: graph position, % of plan, approvals

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-2` |
| Size | M |
| Demo critical path | yes |
| Depends on | T06, T09 |
| Human time | 10 min |

## Goal

While a session runs, the engineer sees where it is in the workflow graph and how far along it is, as a share of the whole plan rather than a time estimate (mockup "VS Code — running session").

## Acceptance criteria

- [ ] The run view draws the workflow graph from `jigworks graph` JSON (read-only, same shape as the hub's graph view) and highlights done, running, waiting and pending nodes live from runner events; fix loops show the attempt number.
- [ ] A progress block shows `progress` from the runner as "48 % of the plan", the current step ("step 5 of 9 · review, attempt 2"), and a marker for where the next human approval will happen.
- [ ] Activity list of the latest events and a "Next for you" card; at an interrupt it becomes Approve/Reject (with links to the diff, the audit log and the test report) and resumes the run.
- [ ] Tokens and cost of the session are shown and update live.
- [ ] Screenshot or recording of the real extension in VS Code with two sessions: one running with the graph and %, one waiting for approval. Playwright screenshots of the standalone run view at **390 px and 1440 px**.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
