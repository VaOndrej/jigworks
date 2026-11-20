# T00 · Spike: `claude -p --output-format stream-json`

| Field | Value |
|---|---|
| Status | done |
| Owner | foundation (before the split) |
| Label | `milestone-0` |
| Size | S |
| Demo critical path | yes |
| Depends on | none |
| Human time | 5 min to read the findings |

## Goal

Confirm the facts the runner and analytics depend on, before any code is written. This is "spike B" in design.md §8 and §11.4.

## Acceptance criteria

- [x] `scripts/spike-claude.sh` reproduces every observation below; `bash scripts/spike-claude.sh` exits 0.
- [x] Recorded, scrubbed transcripts in `runner/tests/fixtures/stream-json/`: one plain run, one `--resume` run, one denied tool.
- [x] `docs/spikes/claude-stream-json.md` documents the exact path and names of the usage fields (input, output, cache write, cache read), `total_cost_usd`, `session_id` and the model name, and whether usage is reported per message or only in the final `result` event.
- [x] Confirms `--resume <session_id>` continues the session (the second run sees context from the first).
- [x] Documents how to check that `claude` is installed and logged in (subscription or API key) without starting a real task, and what a run reports when it is not logged in; this becomes the extension's preflight check.
- [x] Notes how a Max subscription's usage limits show up in `stream-json` (rate-limit or limit-reached events), so the runner can report them instead of failing silently.
- [x] Confirms `--allowedTools` blocks a non-listed tool and shows what the denial event looks like; same for `--permission-mode`.

## Evidence

Findings: [`docs/spikes/claude-stream-json.md`](../../docs/spikes/claude-stream-json.md). Fixtures: `runner/tests/fixtures/stream-json/` (`plain`, `resume-1`, `resume-2`, `denied-tool`, `denied-plan`, `plan-mode`, `not-logged-in`).

`bash scripts/spike-claude.sh --record` (19 Nov 2026, exit code 0):

```
raw transcripts: /var/folders/ws/ccn4_pv94p37xwsmv2_jtr1m0000gn/T//jigworks-spike.IDkylB/raw
claude version: 2.1.197 (Claude Code)
PASS  auth status: loggedIn=true, exit 0, authMethod=claude.ai, subscriptionType=max
PASS  auth status with empty CLAUDE_CONFIG_DIR: loggedIn=false, authMethod=none, exit 1
PASS  not-logged-in run exits 1
PASS  not-logged-in run: init.apiKeySource=none, assistant.error=authentication_failed, result.is_error=true, cost 0
PASS  plain: system/init has session_id, model, apiKeySource, claude_code_version
PASS  plain: every assistant event has message.usage.{input_tokens,output_tokens,cache_creation_input_tokens,cache_read_input_tokens}
PASS  plain: one API message is split into several assistant events with the same message.id (dedupe needed)
PASS  plain: result has total_cost_usd, session_id, usage.* and modelUsage.<model>.{inputTokens,outputTokens,cacheReadInputTokens,cacheCreationInputTokens,costUSD}
PASS  plain: total_cost_usd == sum(modelUsage[].costUSD)
PASS  plain: final output_tokens >= streamed assistant output_tokens (streamed values are partial)
PASS  plain: rate_limit_event with rate_limit_info.{status,resetsAt,rateLimitType}
      models: init=claude-haiku-4-5-20251001, modelUsage=["claude-haiku-4-5-20251001"], rate_limit={"status":"allowed","rateLimitType":"five_hour"}
PASS  resume: second run reports the same session_id
PASS  resume: second run recalls PLUM-42 from the first
      cost per invocation: resume-1=0.014495 resume-2=0.0015018
PASS  allowedTools=Read: x.txt was not created
PASS  allowedTools=Read: result.permission_denials[] has tool_name=Bash with tool_use_id and tool_input
PASS  allowedTools=Read: the denied tool_use gets a user tool_result with is_error=true
PASS  allowedTools=Read: denial is not a run error (result.is_error=false, subtype=success)
      plan-mode exit=0 result={"subtype":"success","is_error":false,"terminal_reason":"completed"}
PASS  permission-mode=plan: y.txt was not created
PASS  permission-mode=plan: init.permissionMode=plan
      plan-mode denials (non-deterministic): []
      plan-mode models: init=claude-haiku-4-5-20251001, assistant=claude-sonnet-5, modelUsage=["claude-haiku-4-5-20251001","claude-sonnet-5"]
PASS  fixtures written to runner/tests/fixtures/stream-json/ and contain no user name, email or org id

ALL CHECKS PASSED
```

Leak check on the fixtures (no hits, grep exit 1):

```
$ grep -rliE "<user>|<email local part>|@gmail|<org id>" runner/tests/fixtures/stream-json; echo $?
1
```

## Notes

- Fixture paths were post-processed once after the run above: the temp dir appeared as `/var/folders/.../T//jigworks-spike.*` (double slash from `$TMPDIR`) and slipped past the scrubber; the scrubber now normalizes the path.
- `denied-plan.jsonl` is a curated run from exploration (plan mode is non-deterministic; it does not always attempt the write). Re-recording writes plan mode to `plan-mode.jsonl` and leaves `denied-plan.jsonl` alone.
- Usage-limit behaviour at the limit is inferred, not observed (see the doc, §5).
- Spend: ~22 paid haiku/plan-mode calls during the spike and four script runs (~$2 API equivalent, mostly plan mode switching to `claude-sonnet-5`); more than the ~15 planned because two script runs failed on findings (auto-memory, plan-mode max turns).
