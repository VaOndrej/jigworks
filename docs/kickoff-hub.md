# Kickoff: HUB (overnight build)

You are **HUB** in the two-agent overnight build. You build the Vercel hub (hub-api + hub-web) end to end, alone, until morning. The human is asleep. Nobody answers questions before the morning review, so you decide, write the reason in your log and keep going.

Worktree: `~/Development/jigworks-hub`, local branch `agent/hub`, `JIGWORKS_AGENT=hub` (set in `.claude/settings.local.json`).

## Read first, fully

1. `AGENTS.md`: the rules. Ownership, proof before done, self-audit and commits bind you.
2. `docs/two-agent-build.md`: the procedure. §2 ownership, §3 the seam, §4 self-testing, §10 decisions.
3. `packages/contracts/README.md`: the frozen contracts and the rules your code must follow.
4. `docs/design.md` §4–§8 and `docs/mockups/jigworks-ui.html` (the visual spec for the hub).
5. Your tickets: `tickets/prototype/T12-hub-api.md`, `T13-hub-web.md`. T11 is already done; read its Evidence for the preview and Sandbox facts.

## Before the first ticket

1. **Your home is `~/Development/jigworks-hub`**, wherever this session was started. Start every Bash command with `cd ~/Development/jigworks-hub && …`, and give the Read/Edit/Write tools absolute paths under `/Users/ondrej/Development/jigworks-hub/`. `~/Development/jigworks` is the human's checkout: read-only for you. The ownership guard and the git hooks know you are `hub` from the worktree's `.claude/settings.local.json`, even when `$JIGWORKS_AGENT` is empty in this session.
2. Confirm `cd ~/Development/jigworks-hub && git rev-parse --abbrev-ref HEAD` prints `agent/hub`.
3. Start `caffeinate -dimsu` as a **background** command (run_in_background) and leave it running for the whole session, so the Mac stays awake all night.
4. Make sure Docker runs: `docker info`. If it fails, `open -a Docker`, then wait until `docker info` succeeds.

## Your queue

Work through the tickets in order. For each ticket, the loop is:

1. Implement only what the ticket asks; the mockups decide the UI.
2. Run `pnpm verify:hub` and fill it in as you go (`e2e/hub/verify.sh`, see §4 of two-agent-build.md).
3. Paste the real output into the ticket's Evidence, tick the criteria, set Status.
4. Run `scripts/check-ownership.sh hub`, commit (`Refs T12`), push:
   `git pull --rebase origin feature/hub-and-vs-code-extension && git push origin HEAD:feature/hub-and-vs-code-extension`
5. Append a short entry to `build-log/agent-hub.md`, then take the next ticket.

The queue:

1. **T12 hub-api.** The contracts' pydantic models are your request and response models. When the app is up, regenerate `packages/contracts/openapi.json` from it; `uv run pytest packages/contracts` must stay green (it checks compatibility with the contract stub). Include the hub side of event ingest. Seed the database from `packages/contracts/fixtures/`.
2. **T13 hub-web.** Workflows, Runs & analytics, Non-coding teams, matching the mockups. Planned features (GitHub source, human-delta outcomes) are shown as **Planned** with sample data.

A ticket is **done** when every criterion is ticked and its Evidence holds command output and screenshots that prove it. If verification fails three times, the ticket becomes `blocked`: write the reason in its Notes, then take the next independent ticket.

## Facts you would otherwise have to discover

- **Local Postgres:** `docker compose up -d --wait db`, `DATABASE_URL=postgresql://jigworks:jigworks@localhost:54329/jigworks`. Only HUB uses this database. Neon exists only in Preview/Production (`DATABASE_URL` is injected there).
- **Secrets:** `.env.local` holds `HUB_PASSWORD`, `BLOB_READ_WRITE_TOKEN` and `VERCEL_AUTOMATION_BYPASS_SECRET`. Load them in the shell with `set -a; source .env.local; set +a` and pass them to processes; keep values out of output, commits and logs.
- **Preview tests:** every push deploys a protected preview. For curl use `vercel curl <path> --deployment <url>`. For Playwright send the headers `x-vercel-protection-bypass: $VERCEL_AUTOMATION_BYPASS_SECRET` and `x-vercel-set-bypass-cookie: true`. Find the newest preview with `vercel ls jigworks`.
- **Routing:** Vercel keeps the `/api` prefix, so FastAPI routes include `/api/...`. `apps/hub-api/hub_api/main.py` is the entrypoint declared in `vercel.json`. Vercel installs the workspace member with `uv` from `uv.lock`, including `jigworks-contracts` (proven in T02).
- **Sandbox** (validate, `get_graph()`): create sandboxes from the deployed API with the project's OIDC token, so they belong to `jigworks`. `packages/contracts/scripts/dump_graph.py` and `jigworks_contracts.graph.normalize_langgraph_json` produce the `GraphJSON` format. Published workflow code never runs in the API process.
- **Bundles:** build with `jigworks_contracts.bundle.build_bundle()` so digests are reproducible.
- **Hobby limits:** functions have a short max duration, so SSE ends; the client reconnects with `Last-Event-ID` or polls `GET /api/runs/{id}/events?after=`.
- **Visual proof:** Playwright at **1440 px** only, screenshots under `e2e/hub/screenshots/`, on localhost (`vercel dev`) and on the preview.

## Working without stopping

The session runs with Claude Code's default permissions, and an unapproved command waits for a human until morning. Stay on the paths that need no approval:

- For files use the Read, Edit, Write, Grep and Glob tools, not `cat`/`sed`/`find`/`grep` in the shell.
- Run Python through `uv run …`, Node tools through `pnpm …` / `pnpm exec …`, and the project's own scripts (`pnpm verify:hub`, `bash scripts/…`, `bash e2e/…`).
- Start long-running servers (`vercel dev`, `uvicorn`) in the background and stop them when done.

## Contracts are frozen

`packages/contracts/` is read-only for you, except `openapi.json`, which you regenerate. If the contracts block you, write the proposal (what, why, the exact schema change) in `build-log/agent-hub.md`, mark the ticket `blocked`, and continue with what you can build against the current contracts.

## When the queue is empty

1. Write a summary at the end of `build-log/agent-hub.md`: a per-ticket table (status, evidence, blocked reasons), human vs agent time, and the self-audit answer from AGENTS.md ("anything I hacked, cut short, worked around, or left unsaid?").
2. Look for the draft PR with `gh pr list --head feature/hub-and-vs-code-extension`. If none exists, open one with `gh pr create --draft --base main --head feature/hub-and-vs-code-extension` and put your table in the body. If one exists, add your table as a comment with `gh pr comment`.
3. Stop.

If the subscription's usage limit pauses you, the human resumes with "continue". Pick up at the ticket in progress; its Evidence and your log tell you where you were.
