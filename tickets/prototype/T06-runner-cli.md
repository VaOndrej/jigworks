# T06 · Runner CLI: execution, checkpoints, worktree, audit log

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-1` |
| Size | L |
| Demo critical path | yes |
| Depends on | T05 |
| Human time | 15 min (watch the first live run) |

## Goal

Run a pinned workflow against a repo, isolated and auditable.

## Acceptance criteria

- [x] `uv run jigworks run --workflow workflows/feature-development --repo sample-repo --prompt "<task>"` runs in a fresh git worktree and emits JSONL events on stdout.
- [x] LangGraph checkpoint + git commit per node; the commit hash is stored in the graph state.
- [x] Resume after a restart (design.md §11.1): kill the runner mid-node, then `uv run jigworks resume <runId>` continues from the last checkpoint; a node whose git commit already exists is not executed twice. Test output pasted.
- [x] `uv run jigworks approve <runId>`, `request-changes <runId> --comment "…"` and `reject <runId>` resume the interrupt; request changes counts as a follow-up prompt.
- [x] Parallel sessions: two runs started at the same time (same or different workflow) each get their own worktree, checkpoint store and event stream, and do not touch each other's files. `uv run jigworks ls` lists them with status. Test output pasted.
- [x] Progress estimate: every event carries `progress` (0–100) = weight of finished nodes / weight of the planned path. Weights come from durations in past local audit logs of the same release digest; with no history they fall back to `weight` per node in `workflow.toml`. A fix loop never moves progress backwards. Unit test with a recorded run.
- [x] `uv run jigworks graph <workflow>` prints the `get_graph()` JSON locally (the runner executes the workflow code anyway), so the extension can draw the graph without the hub.
- [x] Audit log `.jigworks/runs/<runId>/audit.jsonl`: who started (`git config user.email`), workflow digest, model, steps, changed files, gate results, who approved and when, tokens, cost.
- [x] Live proof: one real run on `sample-repo` that goes through at least one fix loop (design.md §9 acceptance) and opens a PR against a local bare remote (no push to GitHub during the build); audit log excerpt pasted.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Code: `runner/jigworks_runner/cli.py` (`jigworks run|approve|request-changes|reject|resume|ls|show|audit|events|graph|inspect|preflight`),
`store.py` (per-run dir: `events.jsonl`, `nodes.jsonl` journal, `checkpoints.sqlite`, `audit.jsonl`,
pinned `package/`, lock), `progress.py` (weights from history of the same digest), `engine.py`
(resume: a journaled node is applied instead of re-run; a cut-off node is cancelled, the worktree
reset and the node re-run; a crashed node of a failed run can be retried).

### Tests: `uv run pytest runner/tests/test_cli.py -v`

Real `jigworks` processes, real git worktrees, SQLite checkpoints, the real gate, fake adapter:

```
test_cli_run_approve_in_a_fresh_worktree PASSED
test_cli_request_changes_and_reject PASSED
test_cli_kill_mid_node_then_resume PASSED
test_cli_crash_after_commit_does_not_run_the_node_twice PASSED
test_cli_relative_pr_remote_and_retry_of_a_failed_push PASSED
test_cli_parallel_runs_are_isolated PASSED
test_cli_second_command_on_a_busy_run_is_refused PASSED
test_progress_matches_recorded_run_and_never_moves_back PASSED
test_progress_weights_from_history_of_the_same_digest PASSED
test_cli_graph_prints_graph_json PASSED
============================= 10 passed in 44.70s ==============================
```

- **Kill mid-node** (`test_cli_kill_mid_node_then_resume`): SIGKILL while `implement` sleeps; `ls`
  shows the run `interrupted` at `implement`; after `resume`, `implement` reads running 1,
  cancelled 1, running 2, succeeded 2; `write_tests` ran once; the killed attempt's partial edit is gone.
- **Commit exists, checkpoint does not** (`test_cli_crash_after_commit_…`): the runner dies with
  exit 137 right after `implement`'s git commit (`JIGWORKS_TEST_CRASH_AFTER_COMMIT`); `resume`
  applies the journaled update; `implement` is not executed again (one agent call, one commit).
- **Parallel** (`test_cli_parallel_runs_are_isolated`): two `run` and then two `approve` processes
  at the same time; separate worktrees, event logs and checkpoint stores; each worktree holds only
  its own files; `ls` lists both as `waiting_human` at `approve_pr`.
- **Progress**: replaying `run_fd_0002` (fix loops + request changes) through the ledger
  reproduces every recorded `progress` value and never moves back; history weights come only from
  audits of the same digest, otherwise `[weights]` from workflow.toml.
- The commit hash of every node is in the graph state (`commits` in the SQLite checkpoint equals
  the snapshots in the events).

### Live proof (Max subscription, release models, 19 Nov 2026 21:40–22:00 UTC)

```
uv run jigworks run --workflow workflows/feature-development --repo sample-repo --run-id run_live_t06 \
  --pr-remote .jigworks/live-remote.git --pr-base base \
  --prompt "Add OrderService.cancel_all(account) to sample-repo: … Keep every invariant in INVARIANTS.md."
uv run jigworks approve run_live_t06                      # plan
uv run jigworks request-changes run_live_t06 --comment "Add a short docstring to cancel_all …"
uv run jigworks approve run_live_t06                      # PR review → open_pr failed (bug, see Notes)
uv run jigworks resume run_live_t06                       # after the fix: open_pr retried, succeeded
```

**A real fix loop happened on its own:** the test writer produced three property tests that
inspected state *after* `cancel_all` instead of before; the independent reviewer ran the suite
(`3 failed, 30 passed`) and answered `VERDICT: FAIL`; `fix` corrected the tests; review #2 PASS;
gate PASS (scope, pytest, hypothesis invariants, secret scan, bandit). The request-changes comment
then went through fix → gate → approve_pr as a follow-up prompt.

Audit (`uv run jigworks audit run_live_t06`; the email is redacted here):

```
release feature-development@1.4.0  digest sha256:06917e8e3d9e226ffad476d7625471516bb9b845c1f5a65f13e1e1f2f2844338
status succeeded  author = approver = <git config user.email>  approvedAt 2026-11-19T21:56:11Z
firstResultCommit 5f95941b5c46  finalCommit bd5ccb03cf7d  followUpPrompts 1  fixLoops 2
prUrl .jigworks/live-remote.git#demo/run_live_t06   (bare remote: refs/heads/demo/run_live_t06 = ab4be25cc328)
changedFiles sample-repo/tests/test_examples.py, sample-repo/tests/test_invariants.py, sample-repo/sample_repo/service.py
apiEquivalentCostUsd 4.896873 (price table) = cliCostUsd 4.896873 (cross-check)
usage: claude-sonnet-5            6 calls  in 22871  out 31146  cache_write 476949  cache_read 4095928
       claude-haiku-4-5-20251001  6 calls  in 7032   out 7927   cache_write 90739   cache_read 424524

steps (node #attempt status model commit gate):
plan #1 succeeded claude-haiku-4-5-20251001 00c86d01bd
approve_plan #1 succeeded - 78ac23d566
write_tests #1 succeeded claude-haiku-4-5-20251001 0025198e2d
implement #1 succeeded claude-haiku-4-5-20251001 231692a866
review #1 failed claude-haiku-4-5-20251001 87d13df3d2
fix #1 succeeded claude-sonnet-5 51afd507f3
review #2 succeeded claude-haiku-4-5-20251001 6839ae299b
gate #1 succeeded - 5f95941b5c gate PASS
approve_pr #1 cancelled - 3376d2284f
fix #2 succeeded claude-sonnet-5 448ba04c0f
gate #2 succeeded - ec15988af3 gate PASS
approve_pr #2 succeeded - ab4be25cc3
open_pr #1 failed -
open_pr #2 succeeded - d3bf929ae0
summary #1 succeeded claude-haiku-4-5-20251001 bd5ccb03cf

decisions:
{"stage":"plan","decision":"approve","at":"2026-11-19T21:46:37Z"}
{"stage":"pr","decision":"request_changes","comment":"Add a short docstring to cancel_all that says terminal orders and other accounts are skipped and ids come back in placement order.","at":"2026-11-19T21:55:38Z"}
{"stage":"pr","decision":"approve","at":"2026-11-19T21:56:11Z"}
```

## Notes

- **The per-step model in the live audit above is wrong for the sonnet nodes** (plan, implement and
  review ran on `claude-sonnet-5`, shown as haiku): the ledger took the first `modelUsage` key,
  and the CLI lists a background haiku call first. Fixed after the run: the node's finish event now
  carries the release model the runner passed (`test_cli_run_approve_…` asserts `plan` →
  `claude-sonnet-5`, `gate` → no model). The live run was not repeated.
- **Bug found by the live run:** a relative `--pr-remote` was resolved against the worktree, so the
  push failed and the run ended `failed` at `open_pr`. Fixed (`cli.pr_remote`), regression test
  added, and the live run was finished with `resume`, which now retries a crashed node of a failed run.
- The bare remote's base branch is `base`, not `main`: the repo's pre-push hook refuses any push
  to a ref named `main`, even to a local bare repo.
- The live run cost $4.90 API-equivalent, more than the mockup's "$1.10 typical"; sonnet `fix` and
  `review` with ~0.5 M cache writes dominate.
- The fix agent edited test files (it fixed the buggy tests the reviewer named). The `fix` prompt
  allows that as long as tests are not weakened, but "tests by a different agent" then holds only
  for the first version.
- Runs execute in the runner's own venv, not in a venv per release digest (design.md §3); T06 does
  not require it, and it is still open.
