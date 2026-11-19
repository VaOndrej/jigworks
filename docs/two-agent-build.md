# Two-agent build — draft for discussion

- **Status:** draft. Once agreed, the rules move into `AGENTS.md` and this file is deleted or kept as the rationale.
- **Goal:** two AI agents build the prototype end to end in parallel, one for the Vercel hub and one for the local side (runner + VS Code extension), and each proves its own work without a human running tests.

## 1. Who owns what

| | Agent **HUB** | Agent **LOCAL** |
|---|---|---|
| Directories (write) | `apps/hub-api/`, `apps/hub-web/`, `vercel.json` | `runner/`, `workflows/`, `sample-repo/`, `clients/vscode/` |
| Tickets | T11 (agent part), T12, T13 | T03–T10, T16, T17, then T14, T15 |
| Branch / worktree | `agent/hub` in `../jigworks-hub` | `agent/local` in `../jigworks-local` |

**Shared, built first by one agent before the split:** T00 spike, T01 scaffolding, T02 `packages/contracts`. After T02 merges, `packages/contracts/` is **frozen**: a change needs a separate commit that the human approves, and both agents rebase onto it.

`e2e/` (cross-system tests) is written by LOCAL after both sides exist, because LOCAL owns the integration tickets T14 and T15.

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

## 5. Decisions needed

1. **Contracts frozen after T02**, changes only with your approval: OK?
2. **Integration (T14, T15, `e2e/`) owned by LOCAL**: OK, or should HUB own the hub side of T14?
3. **Live `claude -p` runs during self-testing:** allowed with a cap (proposal: $5/day, only for the T06 live proof and the demo rehearsal)?
4. **Local Postgres for HUB:** Docker, or a Neon dev branch?
5. **Preview deploys:** may HUB deploy previews itself (`vercel deploy`) and get a deployment-protection bypass for Playwright?
6. **Merging:** agents only commit on their branches and you merge and push: OK?
