# T04 · Runner: Claude CLI adapter

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | yes |
| Depends on | T00, T02 |
| Human time | 5 min |

## Goal

`run(prompt, cwd, options) → result + events` (design.md §7) over `claude -p --output-format stream-json`.

## Acceptance criteria

- [x] The adapter streams normalized `RunEvent`s and returns a `UsageRecord` per call; it supports `--resume`, `--allowedTools`, `--permission-mode` and the model, which always comes from the workflow release (never from the user).
- [x] Passes the agent's text and tool calls through as `agent_output` events (for the extension's "Agent output" tab), and turns a subscription usage limit into a `usage_limit` event instead of a crash.
- [x] `uv run pytest runner -k adapter` passes against the T00 fixtures (no live call in tests).
- [x] Cost is computed from a price table with validity (`model, token_type, price_per_mtok, valid_from`), cache tokens priced separately; `total_cost_usd` is only compared as a cross-check.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Code: `runner/jigworks_runner/adapters/claude.py` (command, stream parser, preflight),
`adapters/base.py` (`AgentOptions`: `model` is required and comes from the release; plan mode is
refused), `events.py` (`EventSink`: seq from 0, every event validated against the contract),
`pricing.py` (price table with validity, cross-check).

`uv run pytest runner -k adapter -v`:

```
test_adapter_command_puts_prompt_before_variadic_flags PASSED
test_adapter_model_is_required_and_plan_mode_is_refused PASSED
test_adapter_plain_run_succeeds_with_usage_per_model PASSED
test_adapter_usage_comes_from_model_usage_not_assistant_events PASSED
test_adapter_passes_text_and_tool_calls_through_as_agent_output PASSED
test_adapter_marks_permission_denials PASSED
test_adapter_thinking_can_be_included PASSED
test_adapter_resume_keeps_the_session PASSED
test_adapter_not_logged_in_is_an_error_not_a_success PASSED
test_adapter_usage_limit_pauses_instead_of_crashing PASSED
test_adapter_usage_limit_warning_is_reported_without_pausing PASSED
test_adapter_max_turns_is_a_failure PASSED
test_adapter_crash_without_result_is_a_failure PASSED
test_adapter_cost_from_price_table_matches_cli_cross_check[plain.jsonl] PASSED
test_adapter_cost_from_price_table_matches_cli_cross_check[resume-1.jsonl] PASSED
test_adapter_cost_from_price_table_matches_cli_cross_check[resume-2.jsonl] PASSED
test_adapter_cost_from_price_table_matches_cli_cross_check[denied-tool.jsonl] PASSED
test_adapter_cost_from_price_table_matches_cli_cross_check[denied-plan.jsonl] PASSED
test_adapter_cost_from_price_table_matches_cli_cross_check[plan-mode.jsonl] PASSED
test_adapter_cost_prices_cache_tokens_separately PASSED
test_adapter_price_validity_picks_the_entry_valid_at_call_time PASSED
test_adapter_runs_the_cli_with_closed_stdin PASSED
test_adapter_cli_not_logged_in_exit_code PASSED
test_adapter_missing_cli_is_an_error_event PASSED
test_adapter_auth_status_keeps_only_method_and_subscription PASSED
test_adapter_live_smoke SKIPPED (set JIGWORKS_LIVE=1)
```

Live smoke, run once (one haiku call on the Max subscription):

```
$ JIGWORKS_LIVE=1 uv run pytest runner -k live_smoke -m live -q
.                                                                        [100%]
1 passed, 26 deselected in 3.30s
```

`pnpm verify:local`: `46 passed, 1 skipped` (python), `4/4 bugs caught`, extension `1 passing`,
`== verify:local OK`.

## Notes

- The usage-limit test uses a **synthetic** stream built from `plain.jsonl` (rate limit
  `rejected`, `is_error: true`), because the real limit cannot be triggered on demand (spike §5,
  "inferred"). The real shape of a limit-reached run is unverified.
- Spike §7 asked T04 to verify how to turn auto-memory off inside `claude -p`. Not done: I found
  no documented setting I could verify without a paid exploratory run. The adapter passes
  `--setting-sources project`, which keeps user hooks/plugins/CLAUDE.md out; auto-memory isolation
  stays open.
- A denied tool call appears twice in agent output: once as the streamed `tool_use`, once at the
  end with `denied: true` (from `result.permission_denials`). The UI keys on `denied`.
