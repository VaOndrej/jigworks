# feature-development

The first Jigworks workflow (design.md §9): a controlled path from a prompt to a pull request
in which the plan is agreed with the human, the tests are written by a different agent from
the spec, an independent agent reviews, a deterministic gate runs the repo's own tests, and a
human approves twice. It is project-agnostic: the repo is the one the run starts in (a bug fix
in repo A, a new feature in repo B); nothing in it is specific to `sample-repo/`.

```
START → triage                          ("brainstorm…" in the prompt, else a short read-only agent call)
  quick      → plan
  brainstorm → brainstorm ⇄ [approve_brainstorm]   (rounds of questions in one session until the
               agent writes the design; at most 15 rounds) → plan (from the approved design)
plan ⇄ [approve_plan]                   (questions / request changes → plan, same session; at most 5 rounds)
  [approve_plan] approve → write_tests → implement → review
  review FAIL → fix → review            (while the open findings shrink; else [approve_fix])
  review PASS → gate
  gate FAIL   → fix → gate
  gate PASS   → [approve_pr]
     approve          → open_pr → summary → END
     request changes  → fix → gate → [approve_pr]      (the comment is the follow-up prompt)
     reject           → END
  [approve_plan] reject → END
```

## Package

| Path | What |
|---|---|
| `workflow.toml` | manifest: version, `plannedPath`, `interruptNodes`, `[models]` and `[effort]` (default + per node), `[weights]`, `[permissions]` |
| `graph.py` | the `StateGraph` (`build_graph`, entrypoint) and the routing functions |
| `steps/nodes.py` | node functions; per-node tool sets (read-only for plan and review) |
| `steps/gate.py` | the gate: scope, protected tests, setup, the repo's tests, property tests (when configured), secret scan, bandit |
| `steps/secrets.py` | built-in secret rules (used when `gitleaks` is not installed) |
| `steps/runtime.py` | the interface the runner injects; the package never imports the runner |
| `plugin/` | the release's skills, loaded by every agent call (`--plugin-dir`) |
| `prompts/*.md` | the phase prompts (`$prompt`, `$spec`, `$earlier`, `$scope`, … are filled in by the nodes) |
| `requirements.lock` | pinned runtime dependencies (one venv per release digest) |
| `tests/` | fake-adapter tests of every path (not part of the release bundle) |

## Rules the package enforces

- **Models and effort come from the release.** `[models]` and `[effort]` (default plus per
  node); the runner passes them to `claude -p --model … --effort …`. Opus 5.5 plans, writes
  the tests and reviews (review at effort `medium`); Sonnet 5.5 implements, fixes and
  summarises. VS Code never picks a model. Needs Claude Code 2.1.280 or newer.
- **Separate sessions.** `write_tests` and `review` start new agent sessions; `write_tests`
  sees only the prompt and the approved plan. `fix` resumes the implementer's session.
- **The repo is where the run starts.** `jigworks run --repo <path>` (the extension: setting
  `jigworks.repoPath`, default the workspace root) sets the scope: the agents may change only
  files under it, the gate's scope check fails on any other path, and `open_pr` only runs after
  a green gate. The prompt can narrow the work further; the plan the human approves names the
  files.
- **The gate runs the repo's own tests.** It reads `.jigworks/gate.toml` in the scope's root
  from the run's base commit (an agent cannot change its own gate), or detects the commands:
  pytest, the package.json `test` script (pnpm / yarn / bun / npm by lockfile, with an install
  first when `node_modules` is missing), `go test ./...`, `cargo test`. Property tests run only
  when the config names them. No test command at all fails the gate with a hint. See the
  docstring of `steps/gate.py` for the config format and `sample-repo/.jigworks/gate.toml` for
  an example.
- **Tests written before implementation are read-only.** After `write_tests`, the gate's
  *protected tests* check fails if `implement` or `fix` changed a file `write_tests` wrote, a
  file under the config's `protected_dirs` that existed then, any `conftest.py`, `pytest.ini`,
  `tox.ini`, `INVARIANTS.md`, the gate config, or the test script / pytest settings in
  `package.json` / `pyproject.toml` (the rest of those files may change: dependencies). New
  test files are allowed. So an agent cannot weaken the
  invariant property tests to get through the gate; a wrong test is a human decision (1.8.0):
  when the fixer keeps a change the human ruled (`NEEDS HUMAN:`), `[approve_fix]` shows the diff
  of the protected files and Approve accepts exactly that content (pinned by git blob hash; any
  later edit fails the gate again). The run goes on; nothing is built again.
- **The gate is deterministic** (no agent): plain tests, property tests, secret scan on the
  added lines, bandit (medium and up) on the changed Python files. Any failing check fails
  the gate and routes to `fix`.
- **Request changes** at the PR review sends the comment back to the agent; the runner counts
  it as a follow-up prompt and records the first reviewed commit (`firstResultCommit`), the
  baseline of the human delta (design.md §8).
- **The plan is agreed before anything is built** (design.md §5). The planner may reply with
  `QUESTIONS:` instead of a plan; Request changes at the plan (the answers, or a comment) goes
  back to the planner, which resumes its own session and remembers the conversation. Approving
  open questions sends the planner back to state its assumptions. After 5 planning rounds the
  run fails. `write_tests`, `implement` and `review` get the approved plan plus the planning
  conversation. Plan discussion is not counted as a follow-up prompt.

- **Fix rounds ask the human only when it helps (1.7.0, 1.8.0).** Fixes run on their own while
  the open findings shrink. `[approve_fix]` asks the human, with a round-by-round report, when two
  fixes made no progress, at the fix cap (8), when the reviewer has a `QUESTION:`, when the fixer
  is blocked (`NEEDS HUMAN:`), or when a fix changed nothing. Every answer there is kept in the
  run's agreements, so the next reviewer and fixer see it as a final decision (a waived finding
  is reported `ACCEPTED`); answered questions are not shown again. A fix right after an answer
  always goes on to review / gate, even when it changed nothing, and Approve after a no-change
  fix re-runs the check, so `approve_fix ⇄ fix` cannot loop.
- **Larger changes are brainstormed first (1.6.0).** `triage` routes the run: the word
  *brainstorm* (or *brainstorming*) in the prompt goes straight to brainstorming; otherwise a
  Sonnet call at low effort answers `ROUTE: QUICK` or `ROUTE: BRAINSTORM` (an answer without a
  route goes the quick way, which still plans with the human). The brainstormer (Opus, high
  effort, read-only) asks as many questions per round and as many rounds as the design needs
  (`QUESTIONS:`), each with its recommended option, and ends with `DESIGN:` and a design in fixed
  sections (goal, scenarios, scope, where it lives, architecture, data model, invariants,
  analytics, milestones, test strategy, decisions). The human answers with Request changes;
  Approve on open questions makes the agent decide them itself. After the design is approved,
  `plan` turns it into an implementation plan of up to 40 lines (`prompts/plan_from_design.md`),
  approved as usual. The brainstorming nodes are off the planned path, like `fix`: % of plan
  is the same on both routes. Limit: `max_brainstorm_rounds` (15).
- **Every agent gets the context it needs, in the same structure.** Prompts read Role → Task
  (from the human) → context sections → Your job → Rules → Reply format. The context is built
  from the checkpointed state (`spec()`, `earlier()` in `steps/nodes.py`): the approved plan,
  the approved design, the planning conversation; the implementer also gets the test writer's
  list, the reviewer gets that list and the implementer's report (and is told not to trust it),
  a fixer without a session to resume gets everything, and the test writer never sees the
  implementation. Each reply format says who reads it next.
- **Checkpoints.** Every node is its own LangGraph step: the runner keeps a SQLite checkpoint
  per run, one git commit per node and a journal of node results, so a run resumes after a
  crash, a usage limit or a new process (the extension calls the CLI once per decision) with
  the same sessions, answers and design. Everything an agent needs later is in the graph state,
  never only in an agent's memory.
- **Skills ship with the release.** `plugin/` is a Claude Code plugin (`.claude-plugin/plugin.json`
  + `skills/*/SKILL.md`); the runner passes it to every agent call as
  `claude -p --plugin-dir <package>/plugin`, so the skills are versioned and covered by the
  release digest, and every developer's run uses the same ones. The prompts name the skill each
  node uses (`brainstorm-before-planning`, `clarify-before-planning`, `tests-from-the-spec`,
  `independent-review`). The target
  repo's own `.claude/skills/` and `CLAUDE.md` apply too (`--setting-sources project`); personal
  skills and settings in `~/.claude` never do.

## Using it in another repo

1. Point the runner at it: in VS Code set `jigworks.runnerCommand` to
   `["uv", "run", "--project", "/path/to/jigworks", "jigworks"]` (the runner stays in this
   repo; `uv run --project` keeps the target repo as the working directory).
2. Optional: commit a `.jigworks/gate.toml` when the detected test command is not the right one.
3. Start a session from the target repo's workspace. Without a test setup, `write_tests` sets
   up the smallest one that fits the stack, and `implement` cannot change it afterwards.

- **Long builds:** every agent call has a 40-turn limit by default. For a larger build pass
  `--max-turns` (VS Code: `"jigworks.runArgs": ["--max-turns", "150"]`).
- **Where the gate looks:** test setups are detected only in the root of the scope; a project in
  a subfolder needs a root `pytest.ini` / package.json test script that runs it.

## Commands

```bash
uv run pytest workflows/feature-development                  # every path, fake adapter, real gate
uv run python -m workflows.feature_development.export_graph  # get_graph() as GraphJSON
uv run python scripts/publish-workflow.py workflows/feature-development                  # dry run against the hub
uv run python scripts/publish-workflow.py workflows/feature-development --channel stable --yes
```

Publishing needs `JIGWORKS_HUB_URL` and `HUB_PASSWORD` in the environment. Deploying the hub
does not publish a workflow: a release exists only after this script (or Publish in the hub's
editor) has run.
