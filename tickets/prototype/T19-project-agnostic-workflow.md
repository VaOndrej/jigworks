# T19 · Project-agnostic `feature-development`, latest models

| Field | Value |
|---|---|
| Status | review |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no |
| Depends on | T18 |
| Human time | 5 min |

## Goal

The same workflow release works in any repo (a bug fix in repo A, a feature in repo B): the
repo is where the run starts, the gate runs that repo's own tests, and the models are the
latest ones (design.md §9, v0.9).

## Acceptance criteria

- [x] Models: Opus 5.5 for plan, write_tests, review; Sonnet 5.5 for implement, fix, summary.
- [x] Reasoning effort per node from the release (`[effort]`, contract `WorkflowManifest.effort`, `claude -p --effort`); review at `medium`.
- [x] Gate without `sample-repo` defaults: scope = the folder the run starts from; tests from `.jigworks/gate.toml` (read from the base commit) or detected (pytest, package.json `test` with pnpm/yarn/bun/npm, go, cargo); a repo without tests fails with a hint.
- [x] Protected tests in any repo: what write_tests wrote, test configuration, the test script, INVARIANTS.md and the gate config; dependencies may still change.
- [x] `sample-repo/.jigworks/gate.toml` keeps the old sample-repo gate (tests, property tests, protected tests dir).
- [x] Prompts carry no sample-repo or Python assumptions; they get the gate's real test commands.
- [x] Agents may run the repo's test and install commands (pnpm/npm/yarn/uv/go/cargo).
- [x] Extension `jigworks.repoPath` defaults to the workspace root; this repo's `.vscode/settings.json` keeps the demo on `sample-repo`.
- [x] The runner's `.jigworks/.gitignore` lets `gate.toml` through.
- [x] Skills ship with the release: `plugin/` (Claude Code plugin) loaded by every agent call via `--plugin-dir`; three skills (`clarify-before-planning`, `tests-from-the-spec`, `independent-review`), named in the prompts.
- [x] Prices for `claude-opus-5-5` and `claude-sonnet-5-5` in the price table.
- [ ] Production hub: redeploy (schema change) and add the new prices before publishing 1.5.0 (human).
- [x] Claude Code updated to 2.1.329 (`claude update`); Opus 5.5 at effort `medium` verified live.
- [ ] A/B eval against a plain Opus 5.5 session (design.md §11, question 7).

## Evidence

```
$ pnpm verify:local
== python: runner, workflows, sample-repo (fake adapter, recorded fixtures, property tests)
103 passed, 1 skipped, 17 warnings in 229.69s (0:03:49)
4/4 bugs caught by the property tests
== vscode: @vscode/test-electron (real extension, real runner, fake adapter)
 8 passing (10s)
== vscode: standalone webview + Playwright screenshots at 1440 px (e2e/local/screenshots/)
  5 passed (1.5s)
== live: skipped (set JIGWORKS_LIVE=1)
== verify:local OK

$ uv run pytest packages/contracts apps/hub-api -q
136 passed, 17 warnings in 11.31s
```

A separate Node repo (not in this repo), runner from here via `uv run --project`, fake adapter:

```
run_b1: waiting for a human (plan review)            # planner asked QUESTIONS
run_b1: waiting for a human (plan review)            # after request-changes: re-planned
run_b1: waiting for a human (pr review)
PASS scope | ok
PASS protected tests | ok
PASS tests: npm test | > node greet.test.js
PASS gitleaks | ok
PASS bandit | no changed Python files
```

Real `claude -p` (Claude Code 2.1.197):
- `--plugin-dir workflows/feature-development/plugin`: the init event lists
  `feature-development:clarify-before-planning`, `…:independent-review`, `…:tests-from-the-spec`,
  and the agent names all three.
- `--model claude-sonnet-5-5`: succeeds; a project skill in `.claude/skills/` is used with
  `--setting-sources project` and only `Read Glob Grep` allowed (no `Skill` permission needed).
- `--model claude-opus-5-5 --effort medium`: `is_error: true`, "Claude Code 2.1.197 does not
  support this model; version 2.1.280 or newer is required".

After `claude update` (2.1.329): `--model claude-opus-5-5 --effort medium --plugin-dir …/plugin`
succeeds, init reports `model: claude-opus-5-5` and the three release skills.
