# Build log

Time is tracked in two columns: **human** (my own time: deciding, directing, reviewing, presenting) and **agent** (time agents worked autonomously without me). The case study suggests ~4 h of human time; this log shows where it went.

## Summary

| Phase | Human | Agent |
|---|---|---|
| Brainstorming & design | 1 h 30 min | — |
| English pass, agent instructions, ticket plan | 20 min | ~85 min |
| UI review and design brainstorming (v0.7) | 30 min | ~30 min |
| Foundation T00–T02 (+ T11 Vercel setup) | 30 min (20 min + 10 min Vercel setup) | ~35 min (+ ~8 min parallel subagent) |
| **Total** | **2 h 50 min** | **~2 h 30 min** |

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

### 2026-11-19 — Foundation: T00, T01, T02 (human 30 min, agent ~35 min + ~8 min parallel)

**What I did**
- 20 min: wrote the session prompt (scope, branch rules, order, stop for review), stayed at the computer for the macOS dialogs during the T01 toolchain smoke test, and the review.
- 10 min: Vercel setup for T11 (`vercel login` + `vercel link`, Blob store, Neon via the Marketplace, `HUB_PASSWORD`).

**What I delegated**
- Everything that was built: branch `feature/hub-and-vs-code-extension`, T00 spike, T01 scaffolding and smoke test, T02 contracts, the agent rows of T11.
- The agent forked T00 (real `claude -p` runs) into a parallel subagent while it scaffolded T01. That subagent made ~22 small paid calls (~$2 API equivalent, mostly the plan-mode experiments), more than the ~15 planned.

**What I reviewed / decided myself**
- Pending: the foundation review ([`docs/foundation-review.md`](docs/foundation-review.md)) before the contracts are frozen and the overnight agents start.

**What I wrote by hand**
- The session prompt only.

**What went wrong / changed course**
- The smoke test did its job: four problems surfaced while I was there, not at 3 a.m. The cached Playwright Chromium was for an older Playwright. `@vscode/test-electron` failed because a VS Code terminal exports `ELECTRON_RUN_AS_NODE=1` (now cleared in `runTest.ts`). `vercel deploy` failed on the root `prepare` script and then on the 100 MB upload limit (the 375 MB VS Code test download; `.vercelignore`).
- T00 findings changed the adapter design: usage must come from `result.modelUsage`, not from streamed messages; plan mode is unusable in the runner (non-deterministic, switched models); user-level settings leak into `claude -p` unless `--setting-sources project`.
- The extension package is named `vscode` so the documented `pnpm --filter vscode` works.
- The first `openapi.json` test required byte equality with the stub, which would have gone red as soon as HUB regenerated the file overnight. It now checks compatibility instead.
- The fixture runs are synthetic (no runner exists yet); they are labelled so.
- The recorded T00 transcripts listed the recording user's claude.ai connectors; they are blanked in the fixtures and in the scrubber.
