# Build log

Time is tracked in two columns: **human** (my own time: deciding, directing, reviewing, presenting) and **agent** (time agents worked autonomously without me). The case study suggests ~4 h of human time; this log shows where it went.

## Summary

| Phase | Human | Agent |
|---|---|---|
| Brainstorming & design | 1 h 30 min | — |
| English pass, agent instructions, ticket plan | 20 min | ~85 min |
| UI review and design brainstorming (v0.7) | 30 min | ~30 min |
| Foundation T00–T02 (+ T11 Vercel setup, overnight launch) | 40 min (20 min + 10 min Vercel setup + 10 min launch) | ~35 min (+ ~8 min parallel subagent) |
| Public-repo secret audit | 2 min | ~5 min |
| Overnight two-agent build (HUB + LOCAL, in parallel) | ~2 min | ~2 h 55 min (HUB ~1 h 25 min + LOCAL ~1 h 30 min; ~1 h 30 min wall clock) |
| Morning review and merge | 10 min | ~1 h 20 min |
| Login rate limit, invariant guard, extension guide | 2 min | ~45 min |
| Extension hub connection (gear, connect flow, status line) | 2 min | ~25 min |
| Hub sample-data reset, worktree cleanup | 2 min | ~20 min |
| Hub validation: relative imports | 1 min | ~10 min |
| Extension: one entry for identical local and hub workflows | 1 min | ~15 min |
| Plan agreed with the human (T18, feature-development 1.5.0) | 3 min | ~40 min |
| Project-agnostic workflow, Opus 5.5 / Sonnet 5.5 (T19) | 5 min | ~1 h 15 min |
| Prompting and brainstorming the workflow improvements (T18, T19, A/B idea) | 1 h | — |
| Release skills as a Claude Code plugin, PR conflicts (T19) | 2 min | ~30 min |
| Brainstorming route, structured context (T20, feature-development 1.6.0) | 3 min | ~1 h |
| Extension: collapsible live view, Markdown for agent text | 2 min | ~25 min |
| Brainstorming the extension improvements (T21) | 10 min | — |
| Extension: gate input, honest gate states, session tabs, live run (T21) | — | ~1 h |
| Brainstorming the demo application | 10 min | — |
| Fix loops that ask the human, resume after the limit, release skills (T22, T23 ticket) | 5 min | ~1 h 10 min |
| Demo application review, case-study reply, time reconciliation | 28 min | — |
| Hub analytics: resumed runs, missing prices (T24) | 2 min | ~25 min |
| Blocked fixer, gate deadlocks, usage of resumed sessions (T25) | 5 min | ~1 h 10 min |
| Fix rounds that end, answers that stick, upgrading a waiting run (T26) | 8 min | ~2 h 05 min |
| **Total** | **5 h 45 min** | **~18 h 25 min** |

## Entries

### 2026-11-19 — Brainstorming & design (human 1 h 30 min)

**What I did**
- Wrote the initial design (v0.5): three-part system (web hub, VS Code extension, central hub API) built on LangGraph, executing locally via `claude -p`.
- Iterated it with Claude Code (Opus) as a sparring partner into v0.6 → [`docs/design.md`](docs/design.md).

**What I delegated**
- Critique of the design, research on LangSmith/Langfuse, Claude subscription billing for `claude -p`, Vercel Services, and licensing options.
- Drafting `docs/design.md` v0.6, this log, and the initial commit.

**What I reviewed / decided myself**
- Scope cuts: visual graph editing dropped (read-only `get_graph()` view only), own analytics (tokens × price table) instead of LangSmith, HR/legal reduced to a text tab.
- Distribution via hub API with a `.zip` import fallback.
- Name (Jigworks), license (FSL-1.1-ALv2), hosting (Vercel).
- Prototype scope and order: runner + workflow → VS Code extension → minimal hub.

**What went wrong / changed course**
- The first scope was far too big for the time box; after re-reading the brief, governance (audit trail, independent review, human approval) moved from "out of MVP" into the core, and the prototype was cut to three demo-able slices.
- "Software Factory" as a name collides with an existing AI coding company (Factory), so it was renamed.

### 2026-11-19 — English pass, agent instructions, ticket plan (human 20 min, agent ~85 min)

**What I delegated**
- Translating `docs/design.md` v0.6 from Czech to English (faithful, no content changes).
- Writing `AGENTS.md` (modeled on the structure of an agent-instructions file from another project of mine), `CLAUDE.md` and `.gitignore`.
- UI mockups of the hub, the Python editor, the graph view, the publish flow and the VS Code extension (a claude.ai artifact, not in the repo).
- A draft split for two build agents (hub vs local) with self-testing → [`docs/two-agent-build.md`](docs/two-agent-build.md).
- Breaking design.md §1 into tickets with verifiable acceptance criteria → [`docs/plan.md`](docs/plan.md).

**What I reviewed / decided myself**
- The rules that go into `AGENTS.md`: English only, Playwright at 390 px + 1440 px for visuals, test output as proof for logic, build log per session.
- Build order: `claude -p` stream-json spike first, cut line after the VS Code extension.
- Agent may commit but not push; pushing stays with me.
- Tickets live in the repo (`tickets/prototype/`), not as GitHub issues.
- One repo for everything (hub, runner, extension, sample-repo, demo); the demo PR is opened against this repo.
- VS Code extension shape: workflows and parallel sessions on the left, the prompt in the middle, a run view with the graph position and % of the plan. Added T16 and T17.
- Human delta loop: what a human changes after approving AI code flows back to the hub as a diff, for analytics (merged as-is vs edited) and supervised workflow improvement. Architecture only (design.md v0.7), not built.
- Hub tabs: Runs & analytics merged into one; "HR department" renamed "Non-coding teams".
- Deep dives for the presentation: Q3, Q6, Q5.
- The hub computes `get_graph()` only on Vercel (Sandbox), behind a "Show graph" CTA.

**What I wrote by hand**
- The session prompt only.

**What went wrong / changed course**
- The agent could not find the brief: it was in a claude.ai chat, not in Claude Code history. I supplied the PDF by hand.
- Critical-path human time in the plan adds up to the whole remaining budget, so milestone 3 (hub) is realistically below the cut line.
- A gap check of the tickets against the brief found two misses: no secret/vulnerability scan for the security lead, and no resume-after-restart proof for the long-task engineer. Both were added to T05 and T06.

### 2026-11-19 — UI review and design brainstorming (human 30 min, agent ~30 min)

**What I did**
- Reviewed the UI mockups screen by screen and brainstormed the next round of product decisions.

**What I delegated**
- Redrawing the mockups, updating design.md (v0.7), the tickets and the two-agent draft.

**What I reviewed / decided myself**
- A session waiting for review shows a "Review" badge instead of its %; approved steps are green; the current step gets a clear "NOW" marker.
- Optional live agent output in VS Code for people who want to watch.
- Models are set by the workflow in the hub, not picked in VS Code.
- Human delta baseline = the first result of a session; follow-up prompts count as corrections just like hand edits. Added "Request changes" to the review step.
- Hub editor: Code/Graph toggle only, new file/folder, GitHub repo connection shown as planned. Hub overview toned down.
- Answers to the two-agent decisions: contracts frozen, Docker Postgres, agents commit and I merge and push.

**What went wrong / changed course**
- The first redesign of the hub overview was over-decorated (KPI tiles, sparklines, coloured step bars); I asked for it to be toned down, then for a middle ground when the second version was too bare.
- Dropped the "AI edit" box from the hub editor: workflows are edited as code.
- Agent installed pnpm and the Vercel CLI and started Docker; logins stay with me.
- Hub behind one shared password; identity from `git config user.email`; no demo in tonight's build.
- Decided the build runs overnight: two agents push to `feature/hub-and-vs-code-extension`, each only its own files; I merge the PR in the morning. Rules in AGENTS.md, procedure in docs/two-agent-build.md.

### 2026-11-19 — Foundation: T00, T01, T02 (human 40 min, agent ~35 min + ~8 min parallel)

**What I did**
- 20 min: wrote the session prompt (scope, branch rules, order, stop for review), stayed at the computer for the macOS dialogs during the T01 toolchain smoke test, and the review.
- 10 min: Vercel setup for T11 (`vercel login` + `vercel link`, Blob store, Neon via the Marketplace, `HUB_PASSWORD`).
- 10 min: overnight launch: bypass token, starting both sessions, fixing the HUB session that started outside its worktree.

**What I delegated**
- Everything that was built: branch `feature/hub-and-vs-code-extension`, T00 spike, T01 scaffolding and smoke test, T02 contracts, the agent rows of T11.
- The agent forked T00 (real `claude -p` runs) into a parallel subagent while it scaffolded T01. That subagent made ~22 small paid calls (~$2 API equivalent, mostly the plan-mode experiments), more than the ~15 planned.

**What I reviewed / decided myself**
- Reviewed [`docs/foundation-review.md`](docs/foundation-review.md) and approved all nine contract decisions; contracts frozen.
- Visual checks are Playwright at 1440 px only; mobile is out of scope (AGENTS.md updated).
- The overnight sessions run with Claude Code's default permissions; the kickoff prompts steer the agents to tools that need no approval.
- I create the Protection Bypass for Automation token myself, so HUB can run Playwright against the preview.

**What I wrote by hand**
- The session prompt only.

**What went wrong / changed course**
- The smoke test did its job: four problems surfaced while I was there, not at 3 a.m. The cached Playwright Chromium was for an older Playwright. `@vscode/test-electron` failed because a VS Code terminal exports `ELECTRON_RUN_AS_NODE=1` (now cleared in `runTest.ts`). `vercel deploy` failed on the root `prepare` script and then on the 100 MB upload limit (the 375 MB VS Code test download; `.vercelignore`).
- T00 findings changed the adapter design: usage must come from `result.modelUsage`, not from streamed messages; plan mode is unusable in the runner (non-deterministic, switched models); user-level settings leak into `claude -p` unless `--setting-sources project`.
- The extension package is named `vscode` so the documented `pnpm --filter vscode` works.
- The first `openapi.json` test required byte equality with the stub, which would have gone red as soon as HUB regenerated the file overnight. It now checks compatibility instead.
- The fixture runs are synthetic (no runner exists yet); they are labelled so.
- The ownership guard was proven inside a real `claude -p` session in the HUB worktree (write to `runner/` blocked, write to `apps/hub-web/` allowed), and the pre-commit hook rejected a commit of a LOCAL path.
- The HUB session in the VS Code panel started in the main checkout, not in its worktree, so `JIGWORKS_AGENT` was empty. The guard and the git hooks now read the agent from the target worktree's `.claude/settings.local.json`, and the HUB kickoff pins all work to `~/Development/jigworks-hub`.
- Worktrees `../jigworks-hub` and `../jigworks-local` created; kickoff prompts in `docs/kickoff-hub.md` and `docs/kickoff-local.md`.
- The recorded T00 transcripts listed the recording user's claude.ai connectors; they are blanked in the fixtures and in the scrubber.

### 2026-11-20 — Public-repo secret audit (human 2 min, agent ~5 min)

**What I delegated**
- A secret scan of the repo before it is shared: `gitleaks` 8.30.1 over all 73 commits on every local and remote branch (`no leaks found`), plus a scan of the working tree. The working-tree hits were only in ignored, never-committed files (`.env.local`, the downloaded VS Code under `clients/vscode/.vscode-test/`).
- The new "the repo is public" section in `AGENTS.md`: a gitleaks scan before every push, and what to do when it finds something.

**What I reviewed / decided myself**
- That the scan becomes a written rule for every agent.

**What went wrong / changed course**
- Nothing leaked. The commit metadata carries my author email, and `docs/kickoff-hub.md` names my local home path; both are known and accepted, not secrets.

### 2026-11-19/20 — Overnight two-agent build (human ~2 min, agent ~2 h 55 min)

Two Claude Code sessions (Opus 5.5) in their own worktrees, pushing to `feature/hub-and-vs-code-extension`, 22:05–23:36 CET. The full agent logs are in `build-log/agent-hub.md` and `build-log/agent-local.md`; this entry folds them.

| Agent | Agent time | Tickets | Blocked |
|---|---|---|---|
| HUB | ~1 h 25 min | T12 hub API, T13 hub web (done) | — |
| LOCAL | ~1 h 30 min | T03, T04, T05, T06, T07, T08, T09, T10, T14, T15 (done), T16 (review), `verify:e2e` | — (T17 deferred as planned) |

**What I delegated**
- Everything in the table, end to end: implementation, tests, ticket evidence, one live `claude -p` run with a fix loop (≈ $4.90 API equivalent on the Max subscription), Vercel preview checks.

**What I reviewed / decided myself**
- Nothing during the night beyond one architecture question from LOCAL (~2 min). The morning review is the next entry.

**What went wrong / changed course**
- Both sessions started in the main checkout, so `JIGWORKS_AGENT` was empty and the ownership hook was inactive. Both ran `check-ownership.sh` before every commit; every commit passes it.
- The disk filled up (down to ~150 MB free) and Docker Desktop stopped. HUB ran Postgres from the Homebrew binaries on port 54329; LOCAL ran its e2e on a private Postgres.
- LOCAL broke the Vercel previews for ~10 min by adding dependencies with install scripts (pnpm 12 refuses them); fixed with `esbuild-wasm` and `pnpm dlx vsce`.
- `vercel-sandbox` 1.x changed its API: two preview round trips for HUB.
- Nothing ran against the deployed hub from the local side (T14/T15/e2e use a fake hub and the real hub app locally), because loading the hub password was refused.
- The live T06 audit shows the wrong per-step models; fixed in code afterwards, not re-run.

### 2026-11-20 — Morning review and merge (human 10 min, agent ~1 h 20 min)

**What I delegated**
- The whole review (`docs/morning-review.md`): ownership per commit, frozen contracts, secret scans, every ticket against its code, all gates, Playwright at 1440 px on localhost, the preview and the extension webview against the mockups.
- Two read-only subagents checked the tickets against the code (HUB and LOCAL).
- Three small fixes: the gitleaks branch of the gate scanned every commit of a run, so a removed secret kept failing the gate (`e275bf2`); T05 back to `review`, because `gh pr create` never ran (`375c2f3`); two hub e2e assertions that depended on today's date and on preview smoke data (`6269013`).
- A helper that asks for the new hub password and writes it to `.env.local` without echoing it.

**What I reviewed / decided myself**
- I rotated `HUB_PASSWORD` (it was weak and guessable from this public repo) to a random value of type Secret for Production and Preview, before the first production deploy.
- I decided to merge after the rotation.

**What went wrong / changed course**
- The first gate run had 3 red gates (`uv run pytest`, `verify:hub`, `verify:local`); all green after the fixes.
- The disk had 226 MB free; the agent cleared the npm download cache (9.3 GB). Docker Desktop's engine still does not start, so the DB gates ran on the Postgres HUB left on port 54329.
- Open after the merge: the invariant property tests can be edited by the `implement` and `fix` agents (design decision needed, §5.2 of the review); no rate limit on the hub login; preview DB full of `smoke-check` data; `BLOB_READ_WRITE_TOKEN` should be rotated to type Secret.

### 2026-11-20 — Login rate limit, invariant guard, extension guide (human 2 min, agent ~45 min)

**What I delegated**
- A rate limit on guessing the hub password. It counts per client IP in Postgres, because Vercel
  instances share no memory. After 10 wrong passwords within 15 min, the API answers 429 with
  `Retry-After`, even for the right password. It covers both ways in: `POST /api/session` and a
  wrong `X-Jigworks-Key` on any endpoint, which the first idea (the login endpoint only) would
  have missed. 6 API tests, written red first.
- The invariant guard. A new gate check, *protected tests*, makes everything `write_tests` left
  in `sample-repo/tests/` read-only for `implement` and `fix`, as well as any `conftest.py`, the
  pytest configuration and `INVARIANTS.md`. New test files are still allowed. 3 workflow tests:
  an implementer who guts the property tests and breaks I1 is caught; `write_tests` may extend
  the invariant tests; a planted `conftest.py` that weakens Hypothesis is caught.
- `docs/guide-vscode-extension.md`.

**What I reviewed / decided myself**
- That both fixes were required, not optional follow-ups.

**What went wrong / changed course**
- The guide had to warn about something the night left implicit: `open_pr` pushes to `origin`,
  the public GitHub repo, by default. The guide sends the PR branch to a local bare repo instead.
- The hub's production `stable` channel is the contract's sample release 1.3.0, which does not
  call agents. The real 1.4.0 has to be published first; the command is in the guide, and
  nothing was published to production.

### 2026-11-20 — Extension hub connection (human 2 min, agent ~25 min)

**What I delegated**
- The human clicked **Sync** in a fresh VS Code and saw nothing: without `jigworks.hubUrl` the
  extension only showed a warning toast, and the settings had no visible entry point.
- A gear in the Jigworks view title (`jigworks.hubSettings`) with connect, sync, change
  password, bypass secret, forget, open settings. **Sync** without a URL or password now starts
  the guided setup (`jigworks.connectHub`: URL → password → optional bypass secret → sync).
- A hub status line under **WORKFLOWS** (`connected`, `sync failed` + reason, not connected).
- The extension now sends the Vercel protection bypass secret when one is stored (`HubClient`
  supported it, nobody passed it) and names a 302 to Vercel SSO as Deployment Protection
  instead of failing on the HTML login page. Red first: the new test failed on the old
  `hub.ts`, passes on the new one.

**What I reviewed / decided myself**
- The bug report and the screenshot.

**What went wrong / changed course**
- No unit test covers the input-box flow of `connectHub` itself (VS Code input boxes cannot be
  driven from the test host without a stub); it is covered by the screenshots and by hand only.

### 2026-11-20 — Hub sample-data reset, worktree cleanup (human 2 min, agent ~20 min)

**What I delegated**
- An inventory of the production hub through the API: only the fixture seed (1 workflow,
  releases 1.2.0 and 1.3.0 by `carol@example.com`, 7 runs by `alice/bob/carol@example.com`).
- `POST /api/admin/remove-sample-data` (hub-only, like `/api/analytics/overview`): deletes
  only the rows whose ids come from the seed files (releases 1.2.0/1.3.0 with their Blob
  bundles, runs `run_fd_0001`–`0007`), keeps real releases and runs under the same workflow,
  and keeps the `seeded` flag so the hub does not seed again. Idempotent. Tests written red first.
- The extension's sync now drops hub workflows the hub no longer offers on `stable`; before,
  the emptied hub's 1.3.0 would have stayed in the sidebar from the cache. Red first, via a new
  `/_test/reset` control in the fake hub.
- Removed the `jigworks-hub` and `jigworks-local` worktrees of the parallel build (nothing
  unpushed, both branches merged into `main`) and deleted `agent/hub` and `agent/local`.

**What I reviewed / decided myself**
- That the test data goes and the worktrees go.

**What went wrong / changed course**
- First version was a script on the raw `DATABASE_URL`. The human rejected it: they have the
  hub URL and password, a database URL should not be needed. Replaced by the endpoint, which
  works with the hub password only; the script was deleted before it was committed.

### 2026-11-20 — Hub validation: relative imports (human 1 min, agent ~10 min)

**What I delegated**
- Publishing `feature-development 1.4.0` to production failed with 409 `imports: ImportError:
  attempted relative import with no known parent package`. The hub's sandbox check put the
  package root on `sys.path` and imported `graph` as a top-level module; the runner wraps the
  root in a package of its own, so it supported `from .steps import nodes` and the hub did not.
  It never showed because the only published releases were the fixture bundles, which use
  absolute imports. The check script now imports like the runner and keeps both styles working.
- A regression test runs the real check script locally against the repo's workflow (red with
  the exact production message, green after) and against the 1.3.0 fixture bundle.

**What I reviewed / decided myself**
- Ran the publish and reported the error.

**What went wrong / changed course**
- The hub's validation and the runner's loader are two copies of the same import rule. Nothing
  tied them together; the new test is the tie for now.

### 2026-11-20 — Extension: one entry for identical local and hub workflows (human 1 min, agent ~15 min)

**What I delegated**
- The sidebar listed `feature-development 1.4.0` twice: the hub's release and the workspace's
  `workflows/feature-development`, with the same digest. A workspace package identical to a
  published one is now hidden; one that differs from a published package of the same name is
  tagged `local (changed)`.
- A file watcher on `workflows/**` rescans the workspace, so the tag follows edits without a
  reload. Tests written red first (hidden at v1, changed at v2, edit → changed → undo → hidden).

**What I reviewed / decided myself**
- Hide identical copies, tag the others `local (changed)`.

**What went wrong / changed course**
- The first watcher broke three existing tests: the runner's `inspect` writes `__pycache__`
  into the package, the filter missed the directory event, and the rescan dropped the
  workspace entries before re-inspecting them. The filter now checks every path segment and
  the scan replaces entries in place, dropping stale ones only at the end.

### 2026-11-20 — Plan agreed with the human, feature-development 1.5.0 (human 3 min, agent ~40 min)

**What I delegated**
- T18: Request changes at the plan now re-plans in the planner's own session instead of
  appending the comment and building on; the planner may answer `QUESTIONS:`; the planning
  conversation goes to `write_tests`, `implement` and `review`; at most 5 planning rounds.
  Four tests written red first through `WorkflowRun` + the fake adapter.
- The runner ledger counts only PR-stage Request changes as follow-up prompts, so agreeing on
  the plan does not show up as a correction in the human delta.
- Three runner tests had the workflow version hard-coded; bumped to 1.5.0.

**What I reviewed / decided myself**
- That every workflow must agree its plan with the human, with memory, before implementation.

**What I wrote by hand**
- Nothing.

**What went wrong / changed course**
- The first run of the round-limit test hung (no limit yet, so the loop never ended) and was
  stopped by hand; the limit made it pass.
- Only the fake adapter is verified; a real `claude -p` questions round has not been run.

### 2026-11-20 — Project-agnostic feature-development, latest models (human 5 min, agent ~1 h 15 min)

**What I delegated**
- T19: the gate no longer assumes `sample-repo/`. The repo is where the run starts; the gate
  reads `.jigworks/gate.toml` from the base commit or detects the test command (pytest,
  package.json `test`, go, cargo), protects what write_tests wrote plus the test script and the
  gate config, and fails with a hint when a repo has no tests. `sample-repo/` got its own gate
  config with the old settings. Prompts lost their sample-repo and Python wording and now get
  the gate's real test commands.
- Models Opus 5.5 (plan, write_tests, review at effort `medium`) and Sonnet 5.5 (implement,
  fix, summary). Reasoning effort is a new per-node release setting (`[effort]`), which needed
  a contract change (`WorkflowManifest.effort`), regenerated types and `openapi.json`.
- The extension's `repoPath` defaults to the workspace root; the runner's `.jigworks/.gitignore`
  no longer hides a committed `gate.toml`; prices for the new models.
- Ten new tests on Python and Node repos that are not sample-repo, red first; a CLI run of the
  release on a separate Node repo through `uv run --project`.

**What I reviewed / decided myself**
- The workflow must be project-agnostic and later support skills; how the gate finds tests
  (detection + optional config), effort as a release field, which nodes get Opus.

**What I wrote by hand**
- Nothing.

**What went wrong / changed course**
- The installed Claude Code (2.1.197) rejects Opus 5.5 ("2.1.280 or newer is required"). It
  still reports `subtype: success` with `is_error: true`; the adapter already treats that as a
  failure, so a run fails with the CLI's message instead of planning on an error text.
- Found two more sample-repo couplings outside the workflow while testing another repo: the
  extension's `repoPath` default and the runner's ignore-all `.jigworks/.gitignore`.
- The production hub seeds prices once, so it will price Opus 5.5 / Sonnet 5.5 at 0 until the
  prices are added there.

### 2026-11-20 — Prompting and brainstorming the workflow improvements (human 1 h)

**What I reviewed / decided myself**
- Prompting the agent through T18 and T19 and brainstorming what the workflow still needs:
  the plan agreed before any code, a project-agnostic gate, the latest models, skills that ship
  with the release, and an A/B comparison against a plain Opus 5.5 session.

### 2026-11-20 — Release skills, PR conflicts (human 2 min, agent ~30 min)

**What I delegated**
- Skills ship with the workflow release: `plugin/` in the package is a Claude Code plugin, and
  the runner passes it to every agent call (`claude -p --plugin-dir`). Three skills
  (`clarify-before-planning`, `tests-from-the-spec`, `independent-review`), named in the
  prompts. Red-first tests for the adapter flag and for every call getting the plugin; a real
  `claude -p` check that the plugin's skills load.
- Merged `main` into the T18 branch and the T18 branch into the T19 branch; the only conflicts
  were the build-log table and entries.

**What I reviewed / decided myself**
- That the workflow has to bring its own skills.

**What went wrong / changed course**
- The first idea, copying skills into the worktree's `.claude/skills/`, would have shown up in
  the diff and the gate's scope check; `--plugin-dir` loads them for the session only.


### 2026-11-20 — Brainstorming route, structured context, feature-development 1.6.0 (human 3 min, agent ~1 h)

**What I delegated**
- `triage` at START (keyword "brainstorm…" or a low-effort Sonnet call), a
  `brainstorm ⇄ approve_brainstorm` loop in one resumed Opus session with no cap on questions
  per round, the approved design fed to `plan` (`plan_from_design.md`), and a new skill
  `brainstorm-before-planning`.
- One prompt structure for every agent and a context builder (`spec()`, `earlier()`) that hands
  the implementer the test list and the reviewer the test list plus the implementer's report.
- A checkpoint test: a brainstorming run continued from SQLite in a new `WorkflowRun`.
- `jigworks run --max-turns`, an extension label for brainstorming and a taller plan box,
  `demo/` as the target folder for demo projects.

**What I reviewed / decided myself**
- That larger changes are brainstormed in as many rounds as the design needs, inside 1.6.0,
  and that every agent must get the right context in a well-structured prompt.

**What went wrong / changed course**
- First idea was to reuse `approve_plan` for brainstorming rounds; dropped because `plan` is on
  the planned path and the brainstorming route would never earn its % weight. Brainstorming is
  now off the planned path (like `fix`) and ends in the normal plan.
- Found that a larger build would hit the runner's fixed 40-turn limit per agent call, and that
  the gate only detects a test setup in the scope root; added `--max-turns` and told the agents.

### 2026-11-20 — Extension: collapsible live view, Markdown for agent text (human 2 min, agent ~25 min)

**What I delegated**
- A "Hide live view" toggle in the run view: progress, graph and agent output collapse into a
  one-line strip (% · node · step), the decision card takes the full width, and the choice is
  remembered (webview `localStorage`).
- Markdown rendering (`react-markdown` + `remark-gfm`) for the interrupt message, the plan or
  brainstorming questions, and the agent's text blocks: headings, bold, lists, code, tables,
  task lists. Raw HTML is not rendered and links are not followed.
- A synthetic fixture `clients/vscode/test-fixtures/runs/run_md_0001-markdown-questions.jsonl`
  and two Playwright tests with 1440 px screenshots.

**What I reviewed / decided myself**
- That the workflow prompts stay as they are: the agents already write Markdown (`###`, `**`,
  numbered lists); only the extension rendered it as plain text.

**What went wrong / changed course**
- Nothing notable. The live view stays open by default; it does not collapse on its own when
  a decision is waiting.

### 2026-11-20 — Brainstorming: extension improvements and the demo application (human 20 min)

**What I did**
- 10 min brainstorming the extension improvements that became T21: what I saw while using the
  extension on a real run (lost answers at the gate, a gate that looked approved, tabs that say
  nothing, a step that looks frozen), written up as the T21 brief.
- 10 min brainstorming the demo application built with the workflow in `demo/`.

### 2026-11-20 — T21: gate input, honest gate states, session tabs, a run that looks alive (human: in the brainstorming above, agent ~1 h)

**What I delegated**
- Gate input: Enter sends the typed text as Request changes, Shift+Enter is a newline, Approve is
  disabled while there is text, one decision per gate (buttons locked until the state changes),
  and every new gate (keyed on node + interrupt seq) starts with an empty field.
- Graph fold: a gate the runner finishes as `succeeded` after a `request_changes` is shown as
  "↺ changes", not ✓; a new attempt of the gate clears the old decision; the progress card's
  "your approval ≈ %" marker uses the same `nodeDone()`.
- Session tabs: `tabChrome()` (word-boundary title, gate name / current action / done / failed)
  and five state icons under `clients/vscode/media/`; the status bar opens the session that waits.
- Live run: Now card (latest action in plain words, last 5 actions, files / tool calls / output
  tokens for the step), elapsed timer and a calm pulse on the running node, shimmer on the
  running segment, and a 10 s PID check of `.jigworks/runs/<runId>/lock` in the extension host.
- 22 unit tests (`pnpm --filter vscode test:unit`), 5 new Playwright tests, 3 synthetic fixtures.

**What I reviewed / decided myself**
- The rules: text typed at a gate never approves; silence is normal, so no alarms, only
  "Agent stopped" when the runner PID is definitely gone.

**What went wrong / changed course**
- Found that the runner records a `request_changes` gate as `succeeded`; fixed in the extension's
  fold only (contracts are frozen), so the hub's own views may still need the same rule.
- Tab tooltips are not possible: `WebviewPanel` has only `title` and `iconPath`.
- **Proposal (runner, not done):** pass `--include-partial-messages` to `claude -p` in
  `runner/jigworks_runner/adapters/claude.py` so text streams while the model writes. A real
  `write_tests` call emitted nothing for 5.5 min because `stream-json` sends a `tool_use` only
  when the whole block is generated. It needs a new delta event kind (or a throttled
  `agent_output` text block), so it is a contract change.

### 2026-11-20 — T22: fix loops that ask the human instead of failing (human 5 min, agent ~1 h 10 min)

**What I delegated**
- The whole change to one Claude Code session: the `approve_fix` interrupt with the round-by-round report and stall detection in `feature-development` 1.7.0, re-review by finding ID, `jigworks resume --more-fixes` for runs that already failed at the limit, the extension cards and Activity trend, tests, fixtures and screenshots.
- A subagent adapted generic engineering skills from the MIT-licensed Matt Pocock skills and Superpowers into the release plugin (with attribution); no Shopify or client material.

**What I reviewed / decided myself**
- Answered one grilling round: the run must never just fail at the limit; Continue with a round-by-round view of what changed; fixes go on while they make progress; every finding must be fixed, and a finding that needs the human must be shown clearly; large projects are split into tickets with their own criteria and a review every few tickets (T23, not built yet).

**What I wrote by hand**
- Nothing.

**What went wrong / changed course**
- The trigger was a real run: 1.6.0 stopped at "fix loop limit reached (3 fixes)" after ~$28 of tokens with no way on. Its pinned release cannot learn the new behaviour, so the runner continues it by forking the LangGraph checkpoint before the last fix and raising `max_fix_loops`; a dry run on a copy of that run with the fake adapter proved the fork and showed that the real gate would fail next (2 failing tests, edits to INVARIANTS.md/README, bandit B108).
- The workflow test suite hung: the `approve_all` test helper approved every interrupt, and approving `approve_fix` grants more fixes, so a test whose fixer never fixes looped forever. The helper now stops at `approve_fix`; it cost ~30 min of waiting before I looked at the process tree instead of the progress dots.
- The first round table had five columns and wrapped letter by letter in the side panel; cut to four columns and no word breaks in table cells.

### 2026-11-20 — Demo review, case-study reply, time reconciliation (human 28 min)

**What I did**
- Reviewed the demo application (`demo/btc-paper-trader`) and the run that built it, drafted the
  reply e-mail to the case-study brief with Claude Code, and reconciled the time totals so the
  e-mail and this log state the same numbers: 5 h 30 min human, ~14 h 45 min agent.

**What I delegated**
- Reading the repo and the brief and drafting the e-mail (not committed: it is not part of the repo).

**What went wrong / changed course**
- The e-mail draft first stated 6 h human / 13 h agent, which did not match this log; the log is
  the source of truth. This entry is booked at 28 min (my estimate was ~30 min) so the total is
  exactly 5 h 30 min.

### 2026-11-20 — Hub analytics: resumed runs, missing prices (T24) (human 2 min, agent ~25 min)

**What I did**
- Noticed that Runs & analytics showed my live run as "0 running" and "$0.00" and asked why.

**What I delegated**
- Diagnosis and fix to one Claude Code session: replaying the real run's `events.jsonl` through the hub projection, a failing test per bug, the fix, ticket T24, PR.

**What I reviewed / decided myself**
- Approved the contract fixture change (`prices.json`) and the fix for both bugs.

**What I wrote by hand**
- Nothing.

**What went wrong / changed course**
- Two independent bugs looked like one "analytics is empty" symptom: a resumed run (T22's `resume --more-fixes`) was projected as `failed` because the old `run_finished` summary was applied last, and the production database never got the 5.5 prices because the seed runs only into an empty database (Haiku 5.5 had no price at all). The hub now adds missing price rows on every start.
- `pnpm verify:hub` tests the Vercel preview, not the working tree; its Workflows test fails on a stale `stable 1.3.0` assertion (pre-existing, left for later).
- The time totals were reconciled to exactly 5 h 30 min human for the case-study reply; this entry moves them to 5 h 32 min.

### 2026-11-20 — Blocked fixer, gate deadlocks, usage of resumed sessions (T25) (human 5 min, agent ~1 h 10 min)

**What I did**
- Watched the real demo run loop through fix rounds that changed nothing at a reported $168, then fail the gate on files the fixer may not touch; asked whether it is a workflow bug and to fix everything for 1.7.0, including the cost in the extension.
- Ran the vendoring command the fixer asked for by hand.

**What I delegated**
- Diagnosis from the run's `events.jsonl`, a 4-call measurement of `claude -p --resume` usage, the fixes in runner, workflow, gate, hub and extension with a failing test each, ticket T25.

**What I reviewed / decided myself**
- Fix all of it at once and ship it as 1.7.0 (not published yet).

**What I wrote by hand**
- Nothing.

**What went wrong / changed course**
- The cost bug came from a CLI change: the T00 spike observed per-call usage on `--resume`; CLI 2.1.329 reports the session's running total. The fixer session was counted 22 times ($195 shown, ~$25 real), and T24's "$117 = CLI" evidence was inflated the same way.
- The first runner fix subtracted the sum of earlier records; a run with old running totals followed by new per-call records would then subtract the wrong base. Replaced by one rule shared by runner, hub and extension (leading running totals, then per call). It is a heuristic because the frozen UsageRecord has no field for it.
- The rule first treated two equal records as a running total that did not grow, which zeroed a contract fixture's repeated calls; a running total must grow in output.
- New 1.7.0 behaviour broke the existing fake fixers that changed nothing; they now touch a file each round.

### 2026-11-20 — Fix rounds that end, answers that stick, upgrading a waiting run (T26) (human 8 min, agent ~2 h 05 min)

**What I did**
- Noticed the demo run (1.7.0) cycling through review fixes and asking questions I had already answered; asked for a diagnosis, then to fix everything and give me a way to continue the same run without building the app again.

**What I delegated**
- Diagnosis from the run's `nodes.jsonl` (review ran once, then approve_fix ⇄ fix three times), failing tests first, the fixes in the workflow (1.8.0) and the gate, the runner's `upgrade` command, two rehearsals on a copy of the real run, ticket T26.

**What I reviewed / decided myself**
- Fix all of it in one release and continue the stuck run on it.

**What I wrote by hand**
- Nothing.

**What went wrong / changed course**
- T25's "a fix that changed nothing goes to the human" had no way back to the check: after the human's answer, changing nothing is the correct fix, so the run looped until Reject.
- The first rehearsal on the real run's state got out of the loop and straight into the next dead end: the gate rejected the test change the human had approved (option b) and only offered "reject the run and start again". Added acceptance of protected files at approve_fix, pinned to their content.
- Answers given to the fixer were consumed by one fix and never reached the reviewer; every answer is now part of the run's agreements.
- After I upgraded the live run, the agent read its new events and found five more gaps (a `# nosec` the gate let through, no `git rm`, no scanners for the agents, protected scratch files, repo rules outside the scope); I asked to add all five to 1.8.0.
- At the new protected-files screen I typed "I agree" instead of pressing Approve; the fixer then claimed the files were accepted and the run stopped again. The screen and the fixer prompt now say that only Approve accepts.
- The real cause of that stop was the extension: the Approve button at approve_fix said "Continue fixing", so I did not see that it was the one that accepts. The button is now named after what it does ("Accept these changes", "Re-run the check").

