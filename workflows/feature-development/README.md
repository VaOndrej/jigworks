# feature-development

The first Jigworks workflow (design.md §9): a controlled path from a prompt to a pull request
in which the plan is agreed with the human, the tests are written by a different agent from
the spec, an independent agent reviews, a deterministic gate runs the repo's own tests, and a
human approves twice. It is project-agnostic: the repo is the one the run starts in (a bug fix
in repo A, a new feature in repo B); nothing in it is specific to `sample-repo/`.

```
START → plan ⇄ [approve_plan]           (questions / request changes → plan, same session; at most 5 rounds)
  [approve_plan] approve → write_tests → implement → review
  review FAIL → fix → review            (at most 3 fixes per run, then the run fails)
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
| `prompts/*.md` | the phase prompts (`$prompt`, `$plan`, `$scope`, … are filled in by the nodes) |
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
  invariant property tests to get through the gate; a wrong test is a human decision.
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

- **Skills ship with the release.** `plugin/` is a Claude Code plugin (`.claude-plugin/plugin.json`
  + `skills/*/SKILL.md`); the runner passes it to every agent call as
  `claude -p --plugin-dir <package>/plugin`, so the skills are versioned and covered by the
  release digest, and every developer's run uses the same ones. The prompts name the skill each
  node uses (`clarify-before-planning`, `tests-from-the-spec`, `independent-review`). The target
  repo's own `.claude/skills/` and `CLAUDE.md` apply too (`--setting-sources project`); personal
  skills and settings in `~/.claude` never do.

## Using it in another repo

1. Point the runner at it: in VS Code set `jigworks.runnerCommand` to
   `["uv", "run", "--project", "/path/to/jigworks", "jigworks"]` (the runner stays in this
   repo; `uv run --project` keeps the target repo as the working directory).
2. Optional: commit a `.jigworks/gate.toml` when the detected test command is not the right one.
3. Start a session from the target repo's workspace. Without a test setup, `write_tests` sets
   up the smallest one that fits the stack, and `implement` cannot change it afterwards.

## Commands

```bash
uv run pytest workflows/feature-development                  # every path, fake adapter, real gate
uv run python -m workflows.feature_development.export_graph  # get_graph() as GraphJSON
```
