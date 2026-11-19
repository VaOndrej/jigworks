# @jigworks/contracts (frozen)

The seam between HUB and LOCAL (docs/two-agent-build.md §3). **Frozen after T02.** Neither
agent edits this package overnight. If you need a change, write the proposal in your
`build-log/agent-<name>.md` and mark the ticket `blocked`. The one exception: HUB
regenerates `openapi.json` from the real FastAPI app; it must stay compatible.

## What is here

| Path | What |
|---|---|
| `schema/jigworks.schema.json` | **Source of truth.** JSON Schema 2020-12, one file, everything under `$defs`. |
| `jigworks_contracts/models.py` | Pydantic v2 models, generated. `import jigworks_contracts as c` |
| `jigworks_contracts/__init__.py` | `validate()`, `assert_valid()`, `parse_event()`, auth constants |
| `jigworks_contracts/bundle.py` | Deterministic bundle `.zip`, `digest()`, `read_bundle()` (verifies the digest) |
| `jigworks_contracts/graph.py` | `normalize_langgraph_json()`: LangGraph `get_graph().to_json()` → `GraphJSON` |
| `src/generated/types.ts` | TS types, generated. `import type { RunEvent } from "@jigworks/contracts"` |
| `src/validate.ts` | `validate(def, value)`, `assertValid()` (ajv, same schema) |
| `openapi.json` | Hub API: every endpoint, request/response shapes, auth. Generated from `scripts/openapi_stub.py`. |
| `fixtures/` | Runs, bundles, graph, API examples, prices, sample human deltas; see `fixtures/README.md` |

Build and test:

```bash
pnpm --filter contracts build      # generate TS, compile ESM + CJS into dist/, run the TS tests
uv run pytest packages/contracts   # Python tests (also checks openapi.json and models.py are up to date)
```

`dist/` is not committed: run the build before using the package from hub-web or the extension
(both verify scripts do it). The package ships ESM (`import`) and CommonJS (`require`, for the
VS Code extension).

Regenerate after a schema change (only with the human's approval once frozen):

```bash
uv run python packages/contracts/scripts/generate.py       # models.py + openapi.json
pnpm --filter contracts build                               # TS types
uv run python packages/contracts/scripts/make_fixtures.py   # fixtures (deterministic)
```

## Rules the code must follow

**Validation.** Pydantic and TS types cannot express the `RunEvent` rule "the payload that
matches `kind` is required". Validate with `validate()` / `parse_event()` (Python) or
`validate()` (TS) at every boundary: when the runner emits, when the hub ingests.

**RunEvent.**
- `kind` defaults to `node_status`, so the design.md §8 example validates unchanged.
- One payload object per kind: `runStarted`, `interrupt`, `reviewDecision`, `agentOutput`,
  `gateResult`, `usage`, `usageLimit`, `error`, `summary` (`run_finished`).
- `seq` is required in practice: the runner numbers every event of a run from 0 without gaps.
  The hub stores `(runId, seq)` once; re-sent events count as `duplicates`, so replaying the
  offline queue is safe.
- `progress` is % of plan (0–100) over `plannedPath`: the weight of finished planned nodes
  divided by the weight of the whole path. It never moves backwards; `fix` has no planned
  weight. `step` / `stepsPlanned` count planned nodes.
- Node `status: failed` means the node's check failed (review FAIL, gate FAIL) or the node
  errored. A fix loop follows; the run itself is not failed.
- `runStatus` is set on the events that change the run status (`waiting_human` while an
  interrupt is open, so the extension shows **Review** instead of %).

**Usage and cost** (docs/spikes/claude-stream-json.md §8).
- One `UsageRecord` per model per `claude -p` call, from the final `result` event's
  `modelUsage`, **not** from the streamed assistant events (they repeat per content block and
  their `output_tokens` is partial).
- Token fields keep the design names: `input`, `output`, `cache_write`, `cache_read`.
- Cost = tokens × `PriceEntry` valid at the call time, computed at read time. `claude -p`
  writes 1-hour cache, so the `cache_write` price is the 1-hour price (2× input).
  `fixtures/prices.json` holds prices that reproduce the CLI's own `costUSD` exactly for
  `claude-haiku-4-5-20251001` and `claude-sonnet-5` (checked by a test). Cost is labelled
  "API equivalent". `cliCostUsd` is a cross-check only.

**Identity and auth.**
- `authorEmail` / `approverEmail` come from `git config user.email`, unverified by design.
  The email pattern is deliberately loose (`x@y`).
- Every endpoint except `GET /api/health` and `POST /api/session` needs the HTTP-only cookie
  `jigworks_session` (set by `POST /api/session` with the hub password) **or** the header
  `X-Jigworks-Key: <HUB_PASSWORD>`. Constants: `HUB_KEY_HEADER`, `HUB_SESSION_COOKIE`,
  `PUBLIC_ENDPOINTS`.
- Errors use `ErrorResponse` (`{"error": {"code", "message"}}`), including 401 and 422. FastAPI's
  default 422 body is different, so the hub needs an exception handler.

**Bundles and digests.**
- `digest = "sha256:" + sha256(zip bytes)`. Build the zip with `bundle.build_bundle()` (sorted
  paths, fixed timestamp 1980-01-01, mode 0644), so the same files always give the same digest.
- `GET /api/releases/{id}/bundle` returns the bytes plus `X-Jigworks-Digest`. The client checks
  the digest it got from the channel resolution, not only the header.
- `read_bundle()` rejects a digest mismatch (`digest_mismatch`) and unsafe paths (`..`, absolute).

**Graph.** `GraphJSON` is LangGraph's `get_graph()` with stable kinds: `start`, `end`, `step`,
`interrupt`. `get_graph()` cannot see `interrupt()` inside a node, so `workflow.toml` declares
`interruptNodes`; weights come from `[weights]`.

**workflow.toml.** Parsed with `tomllib`, it must validate as `WorkflowManifest`. Keys are
camelCase like the rest of the contracts (`minRunnerVersion`, `plannedPath`,
`interruptNodes`); models are `[models] default` plus optional `[models.nodes]`.
