# feature-development

The first Jigworks workflow (design.md §9): a controlled path from a prompt to a pull request
in which the tests are written by a different agent from the spec, an independent agent
reviews, a deterministic gate checks the invariants, and a human approves twice.

```
START → plan → [approve_plan] → write_tests → implement → review
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
| `workflow.toml` | manifest: version, `plannedPath`, `interruptNodes`, `[models]` (default + per node), `[weights]`, `[permissions]` |
| `graph.py` | the `StateGraph` (`build_graph`, entrypoint) and the routing functions |
| `steps/nodes.py` | node functions; per-node tool sets (read-only for plan and review) |
| `steps/gate.py` | the gate: scope, protected tests, pytest, Hypothesis property tests, secret scan, bandit |
| `steps/secrets.py` | built-in secret rules (used when `gitleaks` is not installed) |
| `steps/runtime.py` | the interface the runner injects; the package never imports the runner |
| `prompts/*.md` | the phase prompts (`$prompt`, `$plan`, `$scope`, … are filled in by the nodes) |
| `requirements.lock` | pinned runtime dependencies (one venv per release digest) |
| `tests/` | fake-adapter tests of every path (not part of the release bundle) |

## Rules the package enforces

- **Models come from the release.** `[models] default` plus `[models.nodes]`; the runner passes
  them to the adapter. VS Code never picks a model.
- **Separate sessions.** `write_tests` and `review` start new agent sessions; `write_tests`
  sees only the prompt and the approved plan. `fix` resumes the implementer's session.
- **The agent only changes `sample-repo/`.** The gate's scope check fails on any other path,
  and `open_pr` only runs after a green gate.
- **Tests written before implementation are read-only.** After `write_tests`, the gate's
  *protected tests* check fails if `implement` or `fix` changed or deleted a file under
  `sample-repo/tests/` that existed then, added or changed any `conftest.py`, the pytest
  configuration or `INVARIANTS.md`. New test files are allowed. So an agent cannot weaken the
  invariant property tests to get through the gate; a wrong test is a human decision.
- **The gate is deterministic** (no agent): plain tests, property tests, secret scan on the
  added lines, bandit (medium and up) on the changed Python files. Any failing check fails
  the gate and routes to `fix`.
- **Request changes** at the PR review sends the comment back to the agent; the runner counts
  it as a follow-up prompt and records the first reviewed commit (`firstResultCommit`), the
  baseline of the human delta (design.md §8).
- **Request changes at the plan** does not re-plan: the comment is appended to the plan that
  the later agents see.

## Commands

```bash
uv run pytest workflows/feature-development                  # every path, fake adapter, real gate
uv run python -m workflows.feature_development.export_graph  # get_graph() as GraphJSON
```
