# T02 · `packages/contracts`: run event and audit schema

| Field | Value |
|---|---|
| Status | todo |
| Owner | foundation (before the split) |
| Label | `milestone-0` |
| Size | S |
| Demo critical path | yes |
| Depends on | T00, T01 |
| Human time | 5 min |

## Goal

One schema for run events (design.md §8) shared by the runner (Python) and the extension and hub-web (TS).

## Acceptance criteria

- [ ] JSON Schema for `RunEvent`, `UsageRecord` (`runId, node, attempt, model, adapter, input, output, cache_write, cache_read`) and `AuditRecord`.
- [ ] Generated TS types and Python (pydantic) models; `pnpm --filter contracts build` and `uv run pytest packages/contracts` validate the example event from design.md §8.
- [ ] The usage field mapping uses the names confirmed in T00.
- [ ] `RunEvent` covers every decision taken after the plan, so nothing has to change once contracts are frozen:
  - `progress` (0–100) and the current step (`step`, `stepsPlanned`);
  - `kind`: node status, `interrupt` (with `stage`: plan / pr), `review_decision` (`approve | request_changes | reject`, with the comment), `agent_output` (text and tool calls passed through from `stream-json`), `usage`, `usage_limit`, `error`;
  - `firstResultCommit` and `followUpPrompts` on the run summary (input for the planned human delta);
  - `authorEmail` / `approverEmail` from `git config user.email`;
  - `models` per node as set by the workflow release.
- [ ] `AuditRecord` and a planned `HumanDelta` shape (`outcome: worked_first_time | corrected_by_prompt | edited_by_hand | rejected`) so the hub can show sample data now.
- [ ] The API description states the auth rule: every endpoint except `/api/health` needs the session cookie or the `X-Jigworks-Key` header.
- [ ] Fixtures in `packages/contracts/fixtures/`: recorded runs (`runs/*.jsonl`), a sample workflow bundle (`.zip` + digest) and its `get_graph()` JSON, so HUB and LOCAL can work without each other.
- [ ] API request/response shapes for the endpoints in design.md §8, so HUB's `openapi.json` and LOCAL's mock agree.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
