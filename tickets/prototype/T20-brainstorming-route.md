# T20 · Brainstorming route, structured context (`feature-development` 1.6.0)

| Field | Value |
|---|---|
| Status | review |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no |
| Depends on | T18, T19 |
| Human time | 3 min |

## Goal

A larger change (a new feature, product or module) is brainstormed with the human, in as many
rounds of questions as it takes, before anyone plans it; a bug fix keeps the quick path. Every
agent gets the context it needs in the same prompt structure, rebuilt from the checkpointed
state.

## Acceptance criteria

- [x] `triage` at START: "brainstorm…" in the prompt goes to brainstorming without an agent call; otherwise a read-only Sonnet call (low effort) answers `ROUTE: QUICK|BRAINSTORM`; no route line → quick.
- [x] `brainstorm ⇄ approve_brainstorm`: one resumed session, no cap on questions per round, rounds until the agent replies `DESIGN:`; Approve on open questions makes it decide them itself; `max_brainstorm_rounds` (15).
- [x] The approved design goes to `plan` (`plan_from_design.md`, up to 40 lines by milestone), then the usual `approve_plan`.
- [x] Prompts share one structure (Role, Task, context sections, Your job, Rules, Reply format); the implementer gets the test list, the reviewer the test list and the implementer's report, a fixer without a session the whole spec, the test writer never the implementation.
- [x] A brainstorming run continues in a new process from the SQLite checkpoint with the same session and answers.
- [x] `--max-turns` for `jigworks run` (per agent call; default 40) for larger builds.
- [x] Extension: BRAINSTORMING label, taller plan box; packaged and installed locally.
- [ ] One real `claude -p` run through the brainstorming route (unverified: fake adapter only).
- [ ] Published to the hub as 1.6.0 (human).

## Evidence

```
$ uv run pytest workflows/feature-development/tests/test_workflow.py -q -p no:cacheprovider
37 passed, 17 warnings in 157.81s (0:02:37)

$ uv run pytest runner -q -p no:cacheprovider
49 passed, 1 skipped, 17 warnings in 63.25s (0:01:03)

$ pnpm --filter vscode test        # 8 passing, 1 pending
$ pnpm --filter vscode test:ui     # 6 passed (existing screenshots; no brainstorming fixture yet)
$ pnpm --filter vscode package && code --install-extension clients/vscode/jigworks.vsix --force
Extension 'jigworks.vsix' was successfully installed.
```
