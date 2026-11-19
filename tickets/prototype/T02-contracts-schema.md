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
- [ ] Fixtures in `packages/contracts/fixtures/`: recorded runs (`runs/*.jsonl`), a sample workflow bundle (`.zip` + digest) and its `get_graph()` JSON, so HUB and LOCAL can work without each other.
- [ ] API request/response shapes for the endpoints in design.md §8, so HUB's `openapi.json` and LOCAL's mock agree.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
