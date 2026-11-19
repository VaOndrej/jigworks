# T02 · `packages/contracts`: run event and audit schema

| Field | Value |
|---|---|
| Status | review |
| Owner | foundation (before the split) |
| Label | `milestone-0` |
| Size | S |
| Demo critical path | yes |
| Depends on | T00, T01 |
| Human time | 5 min |

## Goal

One schema for run events (design.md §8) shared by the runner (Python) and the extension and hub-web (TS).

## Acceptance criteria

- [x] JSON Schema for `RunEvent`, `UsageRecord` (`runId, node, attempt, model, adapter, input, output, cache_write, cache_read`) and `AuditRecord`.
- [x] Generated TS types and Python (pydantic) models; `pnpm --filter contracts build` and `uv run pytest packages/contracts` validate the example event from design.md §8.
- [x] The usage field mapping uses the names confirmed in T00.
- [x] `RunEvent` covers every decision taken after the plan, so nothing has to change once contracts are frozen:
  - `progress` (0–100) and the current step (`step`, `stepsPlanned`);
  - `kind`: node status, `interrupt` (with `stage`: plan / pr), `review_decision` (`approve | request_changes | reject`, with the comment), `agent_output` (text and tool calls passed through from `stream-json`), `usage`, `usage_limit`, `error`;
  - `firstResultCommit` and `followUpPrompts` on the run summary (input for the planned human delta);
  - `authorEmail` / `approverEmail` from `git config user.email`;
  - `models` per node as set by the workflow release.
- [x] `AuditRecord` and a planned `HumanDelta` shape (`outcome: worked_first_time | corrected_by_prompt | edited_by_hand | rejected`) so the hub can show sample data now.
- [x] The API description states the auth rule: every endpoint except `/api/health` needs the session cookie or the `X-Jigworks-Key` header.
- [x] Fixtures in `packages/contracts/fixtures/`: recorded runs (`runs/*.jsonl`), a sample workflow bundle (`.zip` + digest) and its `get_graph()` JSON, so HUB and LOCAL can work without each other.
- [x] API request/response shapes for the endpoints in design.md §8, so HUB's `openapi.json` and LOCAL's mock agree.

## Evidence

Package: [`packages/contracts/`](../../packages/contracts/README.md). Source of truth: `schema/jigworks.schema.json`. Pydantic models, TS types and `openapi.json` are generated from it; a test fails if `models.py` or `openapi.json` is stale.

**How each criterion is met**

| Criterion | Where |
|---|---|
| JSON Schema `RunEvent`, `UsageRecord`, `AuditRecord` | `$defs` in `schema/jigworks.schema.json` |
| Generated TS + pydantic; design example validates | `src/generated/types.ts`, `jigworks_contracts/models.py`; `test_design_example_event_validates_as_is` and `esm/cjs: design.md §8 example validates as-is` |
| Usage names from T00 | `UsageRecord` field descriptions map to `result.modelUsage[m].*`; `test_usage_mapping_from_real_stream_json_matches_cli_cost` maps every T00 recording and reproduces the CLI's `costUSD` from `fixtures/prices.json` |
| `progress`, `step`, `stepsPlanned` | `RunEvent` and `RunSummary` |
| `kind` values incl. `interrupt` (`stage` plan/pr), `review_decision` (approve / request_changes / reject + comment), `agent_output`, `usage`, `usage_limit`, `error` | `EventKind` (+ `run_started`, `gate_result`, `run_finished`); one required payload per kind, enforced by `allOf` if/then; `test_every_kind_requires_its_payload` |
| `firstResultCommit`, `followUpPrompts` on the run summary | `RunSummary`; `test_fix_loop_run_counts_follow_ups_and_first_result` |
| `authorEmail` / `approverEmail` | `RunStartedPayload`, `ReviewDecisionPayload`, `RunSummary`, `AuditRecord` |
| `models` per node | `ModelAssignment {default, nodes}` in run_started, summary, audit, `WorkflowManifest` |
| `AuditRecord` + planned `HumanDelta` (4 outcomes) | `$defs`; `fixtures/audit/`, `fixtures/human-deltas.json` (`sample: true`) |
| Auth rule in the API description | `openapi.json`: global `security` = `X-Jigworks-Key` header or `jigworks_session` cookie; only `GET /api/health` and `POST /api/session` have `security: []`; `test_openapi_states_the_auth_rule` |
| Fixtures: runs, bundle `.zip` + digest, `get_graph()` JSON | `fixtures/runs/` (7 synthetic runs), `fixtures/bundles/` (1.2.0, 1.3.0, tampered), `fixtures/graph/` (raw from LangGraph 1.2.23 + normalized) |
| API request/response shapes for design.md §8 | `openapi.json`, 21 operations (design table + session, run list/detail, polling, channel update, release comparison, outcomes); `test_openapi_covers_the_design_endpoints`; examples in `fixtures/api/` |

**`pnpm --filter contracts build`** (exit 0)

```
$ node scripts/gen-ts.mjs && tsc -p tsconfig.json && tsc -p tsconfig.cjs.json && node -e "…dist/cjs/package.json…" && node --test test/
generated src/generated/types.ts and src/generated/schema.ts
ℹ tests 29
ℹ pass 29
ℹ fail 0
```

**`uv run pytest packages/contracts -v`** (exit 0)

```
test_design_example_event_validates_as_is PASSED
test_node_status_needs_node_and_status PASSED
test_every_kind_requires_its_payload[run_started-runStarted] PASSED
  … (9 kinds, all PASSED)
test_unknown_fields_are_rejected PASSED
test_run_event_covers_every_decision_after_the_plan PASSED
test_usage_record_uses_the_design_names PASSED
test_human_delta_outcomes PASSED
test_usage_mapping_from_real_stream_json_matches_cli_cost PASSED
test_fixture_validates[…] PASSED                         (23 fixture files)
test_recorded_run_is_a_consistent_stream[…] PASSED       (7 runs: seq 0..n, time order, progress never backwards)
test_pydantic_round_trip_keeps_the_wire_format PASSED
test_fix_loop_run_counts_follow_ups_and_first_result PASSED
test_bundle_digests_and_tampering PASSED
test_bundle_build_is_deterministic PASSED
test_graph_fixture_is_normalized_from_real_get_graph PASSED
test_openapi_is_generated_from_the_contracts PASSED
test_openapi_states_the_auth_rule PASSED
test_openapi_covers_the_design_endpoints PASSED
============================== 54 passed in 0.78s ==============================
$ uv run python packages/contracts/scripts/generate.py --check
generated files are up to date
```

**The tests can fail:** a progress regression in run 0002 and a stale `openapi.json`, both introduced on purpose: `2 failed, 52 passed`. After restoring the files: `54 passed`.

**Fixture generator is deterministic:** two runs of `make_fixtures.py` give byte-identical fixtures (md5 of all files compared).

```
bundles: 1.2.0 sha256:7fdedf35076f…, 1.3.0 sha256:e941f267e18b…
graph: 12 nodes, 17 edges
run run_fd_0001: 39 events, status succeeded, progress 100.0 %, cliCost $0.80
run run_fd_0002: 60 events, status succeeded, progress 100.0 %, cliCost $1.37
run run_fd_0003: 11 events, status rejected, progress 11.1 %, cliCost $0.17
run run_fd_0004: 44 events, status succeeded, progress 100.0 %, cliCost $1.10
run run_fd_0005: 30 events, status waiting_human, progress 85.6 %, cliCost $0.78
run run_fd_0006: 15 events, status paused_usage_limit, progress 30.0 %, cliCost $0.23
run run_fd_0007: 16 events, status running, progress 30.0 %, cliCost $0.23
api examples: 12; prices: 8; human deltas: 4
```

**hub-api consumes the contracts on Vercel:** `apps/hub-api` depends on the workspace package `jigworks-contracts`, and `/api/health` returns `HealthResponse`. The preview build log shows `Installing the dependencies of uv workspace member "jigworks-hub-api" only … from uv.lock`, and `vercel curl /api/health` returns `{"ok":true}` with HTTP 200.

**Repo-wide:** `uv run pytest` reports 58 passed; `pnpm -r test` exits 0 (contracts 29/29, hub-web 1/1, vscode 1 passing).

## Notes

- Status is `review`, not `done`: the human reviews the contracts before they are frozen (docs/two-agent-build.md §6.1).
- Decisions made here that the design left open: cache writes are priced as 1-hour cache (`claude -p` writes only 1-hour cache, T00); `workflow.toml` gains `plannedPath` and `interruptNodes` because `get_graph()` cannot see `interrupt()`; the email pattern is loose (`x@y`); `seq` is optional in the schema (so the design example validates) but required at ingest.
- The runs are synthetic (no runner before T06); see `fixtures/README.md`.
