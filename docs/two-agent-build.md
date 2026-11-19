# Two-agent build — draft for discussion

- **Status:** draft. Once agreed, the rules move into `AGENTS.md` and this file is deleted or kept as the rationale.
- **Goal:** two AI agents build the prototype end to end in parallel, one for the Vercel hub and one for the local side (runner + VS Code extension), and each proves its own work without a human running tests.

## 1. Who owns what

| | Agent **HUB** | Agent **LOCAL** |
|---|---|---|
| Directories (write) | `apps/hub-api/`, `apps/hub-web/`, `vercel.json` | `runner/`, `workflows/`, `sample-repo/`, `clients/vscode/` |
| Tickets | T11 (agent part), T12, T13, hub side of T14 | T03–T10, T16, T17, runner side of T14, T15 |
| Branch / worktree | `agent/hub` in `../jigworks-hub` | `agent/local` in `../jigworks-local` |

**Shared, built first by one agent before the split:** T00 spike, T01 scaffolding, T02 `packages/contracts`. After T02 merges, `packages/contracts/` is **frozen**: a change needs a separate commit that the human approves, and both agents rebase onto it.

`e2e/` (cross-system tests) is written by LOCAL after both sides exist; HUB owns the hub side of T14 (ingest endpoint), LOCAL the runner side and T15.

**Enforcement:** `scripts/check-ownership.sh <agent>` fails if the branch touches files outside that agent's directories (plus its ticket files and `BUILD_LOG.md`). Both agents run it before every commit.

## 2. The seam: contracts and recorded runs

The two sides never wait for each other because they meet in two artifacts in `packages/contracts/`:

1. **Schemas** (`RunEvent`, `UsageRecord`, `AuditRecord`, the API request/response shapes) → generated TS + Python types.
2. **Recorded runs** (`packages/contracts/fixtures/runs/*.jsonl`): real event streams captured from the runner (first from T00, then from T06).
   - HUB uses them as seed data for Runs & analytics and to test event ingest.
   - LOCAL uses them to replay a run in the extension without spending tokens.

HUB also publishes the FastAPI OpenAPI spec to `packages/contracts/openapi.json`; LOCAL's T14/T15 tests run against a mock generated from it until the preview deploy exists.

## 3. How each agent tests itself

One entry point per side; the output of that command is the ticket's evidence.

**LOCAL — `pnpm verify:local`**
- `uv run pytest runner workflows sample-repo`: fake adapter, recorded `stream-json` fixtures, no tokens spent. Includes the property tests, the planted-secret gate test and the kill-and-resume test.
- `pnpm --filter vscode test`: `@vscode/test-electron` drives the real extension headless: start two sessions with the fake adapter, receive events, approve at the interrupt, see the run finish.
- `pnpm --filter vscode test:ui`: the webview React app runs standalone with recorded runs; Playwright screenshots at 390 px and 1440 px into `e2e/screenshots/local/`.
- **Live check, opt-in:** `JIGWORKS_LIVE=1 uv run pytest -m live` runs one real `claude -p` run on `sample-repo`, with a budget cap.

**HUB — `pnpm verify:hub`**
- `uv run pytest apps/hub-api` against a local Postgres.
- `vercel dev` + Playwright on `localhost`: the three tabs at 390 px and 1440 px into `e2e/screenshots/hub/`.
- Sandbox validation is mocked locally and runs for real only on the preview deploy.
- After a preview deploy, the same Playwright suite runs against the preview URL.

**Integration — `pnpm verify:e2e`** (LOCAL, after T14/T15): publish a workflow in the hub → the extension syncs `stable` → fake-adapter run → events appear in the hub's runs list.

## 4. Human checkpoints

The agents work unattended between these points; each costs a few minutes of review.

1. After T00–T02 (contracts frozen).
2. After T06 live proof (one real run with a fix loop).
3. Before each merge of `agent/hub` or `agent/local` into `main`. Agents commit; only the human merges and pushes.
4. Before recording the demo.

## 5. Decisions (answered 19 Nov 2026)

1. **Contracts frozen after T02**; changes only with the human's approval. Agreed.
2. **Integration split:** HUB owns the hub side of T14 (event ingest endpoint, offline replay acceptance); LOCAL owns the runner side, T15 and `e2e/`. The two agents do not need equal workloads.
3. **Live `claude -p` runs:** the human has a Max subscription, so there is no per-dollar bill; the limit is the subscription's rolling usage window. Live runs stay opt-in (`JIGWORKS_LIVE=1`) and are used for the T06 live proof, the extension's login check and demo rehearsal. The extension must verify it is using the logged-in Claude Code (preflight in T08, check found in T00).
4. **Local Postgres for HUB:** Docker.
5. **Preview deploys:** the Vercel project is linked to the GitHub repo, so every pushed branch gets a preview deploy automatically. Because agents do not push (decision 6), HUB self-tests with `vercel deploy` (CLI preview) and `vercel curl` for protected URLs; the human's pushes produce the Git previews. **Open:** may HUB push its own `agent/hub` branch (never `main`) to get Git previews instead?
6. **Merging:** agents only commit on their branches; the human merges and pushes. Agreed.
