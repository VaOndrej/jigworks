# Spike: `claude -p --output-format stream-json`

- **Ticket:** T00 (design.md §8 "spike B", §11.4)
- **Date:** 19 Nov 2026, Claude Code **2.1.197**, macOS, Max subscription (OAuth, `authMethod: claude.ai`)
- **Reproduce:** `bash scripts/spike-claude.sh` (5 small paid calls; `--record` also rewrites the fixtures)
- **Fixtures:** `runner/tests/fixtures/stream-json/` (scrubbed: home → `/home/user`, temp dir → `/work`, email/org id replaced, thinking `signature` → `REDACTED`)

| Fixture | What it shows |
|---|---|
| `plain.jsonl` | one-turn run: init, thinking_tokens, assistant, rate_limit_event, result |
| `resume-1.jsonl`, `resume-2.jsonl` | `--resume <session_id>`; run 2 recalls the codeword from run 1 |
| `denied-tool.jsonl` | `--allowedTools Read`, agent tries Bash → denial |
| `denied-plan.jsonl` | `--permission-mode plan`, agent tries Write → denial (curated run, see §6) |
| `plan-mode.jsonl` | `--permission-mode plan` where the agent did not attempt the write |
| `not-logged-in.jsonl` | empty `CLAUDE_CONFIG_DIR`, no API key |

"Observed" = seen in the transcripts and asserted by the script. "Inferred" = not reproducible on demand.

## 1. Required flags

- `-p --output-format stream-json` **requires `--verbose`** (observed; without it the CLI refuses stream-json in print mode).
- `--allowedTools`, `--disallowedTools` and `--tools` are **variadic**: a prompt placed after them is swallowed (`Error: Input must be provided either through stdin or as a prompt argument`, exit 1). Put the prompt first, or pass it on stdin. (observed)
- Without stdin, claude waits 3 s and prints `Warning: no stdin data received in 3s`. Always run with `stdin=DEVNULL`. (observed)
- Every line on stdout is one JSON object; stderr carries only warnings. (observed)

## 2. Event types seen

| `type` / `subtype` | Notes |
|---|---|
| `system/hook_started`, `system/hook_response` | user-level hooks from `~/.claude/settings.json` run inside `claude -p`; gone with `--setting-sources project` (observed) |
| `system/init` | `session_id`, `model`, `cwd`, `tools[]`, `permissionMode`, `apiKeySource`, `claude_code_version`, `mcp_servers`, `skills`, `plugins` |
| `system/thinking_tokens` | `estimated_tokens`, `estimated_tokens_delta`; many per turn, ignore for cost |
| `assistant` | `message` = Anthropic Messages API message (`id`, `model`, `content[]`, `usage`); optional top-level `error` |
| `user` | tool results: `message.content[]` items of `type: tool_result` (`tool_use_id`, `content`, `is_error`), plus top-level `tool_use_result` |
| `rate_limit_event` | `rate_limit_info` (§5) |
| `result` | final summary, always the last line (§3) |

## 3. Usage, cost, session, model (observed)

**Final `result` event** (one per `claude -p` invocation):

| Fact | Path |
|---|---|
| input tokens | `result.usage.input_tokens` |
| output tokens | `result.usage.output_tokens` |
| cache write | `result.usage.cache_creation_input_tokens` (split in `usage.cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`) |
| cache read | `result.usage.cache_read_input_tokens` |
| cost | `result.total_cost_usd` (USD, "API equivalent" on a subscription) |
| per model | `result.modelUsage.<model>.{inputTokens, outputTokens, cacheCreationInputTokens, cacheReadInputTokens, costUSD, contextWindow, maxOutputTokens}` |
| session | `result.session_id` (same value as `system/init.session_id`) |
| outcome | `result.subtype` (`success`, `error_max_turns`), `result.is_error`, `result.terminal_reason` (`completed`, `max_turns`), `result.errors[]`, `result.num_turns`, `result.result` (final text) |
| denials | `result.permission_denials[]` (§6) |

**Model name:** `system/init.model` (e.g. `claude-haiku-4-5-20251001`), `assistant.message.model`, and the keys of `result.modelUsage`. **They can disagree**: with `--model haiku --permission-mode plan`, init said `claude-haiku-4-5-20251001` but every assistant message was `claude-sonnet-5` and `modelUsage` listed both (observed, all four plan-mode runs). Only `modelUsage` keys are trustworthy for billing.

**Per message vs final:**

- Usage is reported **both** per assistant message and in the final `result`. (observed)
- One API message is emitted as **several `assistant` events, one per content block** (thinking, text, tool_use), all with the **same `message.id` and the same `usage` object**. Summing assistant events double-counts. (observed)
- The `output_tokens` on streamed assistant events is **partial** (plain run: 8 on the assistant events, 201 in `result`). (observed)
- `result.usage` covers the main conversation model only. `result.modelUsage` additionally includes background calls (e.g. a haiku call of ~530 input tokens on the Bash run: `result.usage.input_tokens` 18 vs `modelUsage[haiku].inputTokens` 550). (observed)
- `total_cost_usd == Σ modelUsage[*].costUSD` exactly. (observed, asserted)
- `total_cost_usd` covers **this invocation only**, not the whole resumed session (resume-1 $0.0145, resume-2 $0.0015). (observed)
- Cache writes are 1-hour cache (`ephemeral_1h_input_tokens`), which Anthropic prices at 2× base input, not 1.25× like the 5-minute cache. (observed type; price is documented pricing, not verified here)
- Even "reply ok" costs ~$0.014–0.024 on haiku: the Claude Code system prompt is ~18 k cached + 7–10 k cache-write tokens. Cache tokens dominate, as design.md §8 assumed. (observed)

## 4. `--resume` (observed)

`claude -p "<prompt>" --resume <session_id>` continues the session: `resume-2` answered `PLUM-42`, a codeword only present in `resume-1`, with tools disabled (`--tools ""`) so it could not have read it from a file. The `session_id` stays the same. Sessions are stored under `~/.claude/projects/<cwd with non-alphanumerics → "-">/<session_id>.jsonl`, so **resume only works from the same cwd** (inferred from the storage layout; the runner must resume from the same worktree path).

## 5. Login check and usage limits

**Preflight (observed):** `claude auth status --json` (JSON is the default) starts no task and costs nothing.

```json
{"loggedIn": true, "authMethod": "claude.ai", "apiProvider": "firstParty",
 "email": "...", "orgId": "...", "orgName": "...", "subscriptionType": "max"}
```

Not logged in (empty `CLAUDE_CONFIG_DIR`, no `ANTHROPIC_API_KEY`): exit code **1**, `{"loggedIn": false, "authMethod": "none", "apiProvider": "firstParty"}`. Extension preflight: run it, require exit 0 and `loggedIn: true`; show `authMethod` / `subscriptionType`; never display or send email/org.

**A run when not logged in (observed):** exit code 1 after ~40 ms, no API call:
- `system/init.apiKeySource: "none"` (**not a login signal**: the logged-in OAuth runs, e.g. `plain.jsonl`, also report `"none"`);
- an `assistant` event with `message.model: "<synthetic>"`, text `"Not logged in · Please run /login"` and top-level **`error: "authentication_failed"`**;
- `result.subtype: "success"` but **`is_error: true`**, `total_cost_usd: 0`.

So `result.subtype` alone is not a success signal; use `is_error`, the exit code, and `assistant.error`.

**Usage limits:** every run emits one `rate_limit_event` (observed):

```json
{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1795128000,
 "rateLimitType": "five_hour", "overageStatus": "rejected",
 "overageDisabledReason": "org_level_disabled", "isUsingOverage": false}}
```

- Observed: `status: "allowed"`, `rateLimitType: "five_hour"`, `resetsAt` as Unix seconds.
- Inferred (cannot trigger the real limit tonight): near the limit `status` becomes `allowed_warning`, at the limit `rejected` (other `rateLimitType` values such as weekly limits are likely); a limit-reached run then ends like the auth failure: an `assistant` event with a top-level `error` (rate limit) and a `result` with `is_error: true`, non-zero exit, probably `api_error_status: 429`.
- Runner rule: map `rate_limit_info.status != "allowed"` to a `usage_limit` event with `resetsAt`, and treat an `is_error` result whose last `rate_limit_event` is `rejected` as "paused by usage limit", not as a node failure.

## 6. `--allowedTools` and `--permission-mode` (observed)

- `--allowedTools Read`: the agent still sees all tools in `system/init.tools` (27); the call is denied at run time. A denied Bash call shows up as:
  - a `user` event with `tool_result` `{"tool_use_id": "toolu_…", "is_error": true, "content": "<reason>"}`;
  - `result.permission_denials[]`: `{"tool_name": "Bash", "tool_use_id": "toolu_…", "tool_input": {"command": "echo hi > x.txt", …}}`;
  - the run itself still succeeds (`is_error: false`); the agent reports back. The file was not created.
  - The `content` text names the reason that applied (here: output redirection outside the allowed working directories). Key on `permission_denials`, not on the text.
- `--permission-mode plan` (`system/init.permissionMode: "plan"`): no file was written in any run, but behaviour is **non-deterministic and expensive**: in one run the agent tried Write and got `"Cannot write to … while in plan mode."` plus a `permission_denials` entry (`denied-plan.jsonl`); in others it wrote its own plan to `~/.claude/plans/<slug>.md` (allowed in plan mode) or spent all turns on `ToolSearch` for `ExitPlanMode`, ending `error_max_turns` with exit 1. It also switched the model to `claude-sonnet-5` (~$0.43 per tiny run). **Do not use plan mode in the runner**; restrict with `--allowedTools` / `--disallowedTools` / `--tools`.
- `result.subtype: "error_max_turns"` → exit code 1, `is_error: true`, `errors: ["Reached maximum number of turns (N)"]`.

## 7. Other surprises

- **User config leaks into runs:** without `--setting-sources project`, the user's global hooks (SessionStart), plugins, skills and CLAUDE.md load into every `claude -p` run (more tokens, non-reproducible behaviour). `--bare` would isolate fully but accepts only `ANTHROPIC_API_KEY`, not the subscription OAuth.
- **Auto-memory:** with tools enabled, a prompt saying "remember X" made the agent write `~/.claude/projects/<cwd>/memory/*.md` (outside the repo). The runner should disable or isolate it (e.g. a dedicated `CLAUDE_CONFIG_DIR` is not an option because it drops the login; use `--setting-sources project` plus a project setting that turns auto-memory off, to be verified in T04).

## 8. Implications for T02 contracts / T04 adapter

**UsageRecord:** one record **per model** per `claude -p` invocation, from the final `result` event, not from assistant events:

| UsageRecord | Source |
|---|---|
| `model` | key of `result.modelUsage` |
| `input` | `modelUsage[m].inputTokens` |
| `output` | `modelUsage[m].outputTokens` |
| `cache_write` | `modelUsage[m].cacheCreationInputTokens` |
| `cache_read` | `modelUsage[m].cacheReadInputTokens` |
| `cliCostUsd` (cross-check only) | `modelUsage[m].costUSD` (Σ = `total_cost_usd`) |
| `sessionId` | `result.session_id` |
| `adapter` | `"claude"` |

The 5m/1h split of cache writes is only in `result.usage.cache_creation` (main model). Recommendation: keep `cache_write` as the total and price it as 1-hour cache, or add optional `cache_write_1h` to the contract; decide in T02.

**agent_output passthrough:** for each `assistant` content block emit `{kind: "agent_output", messageId, block: "text" | "tool_use" | "thinking", text?, tool?: {id, name, input}}`, and for each `tool_result` emit `{block: "tool_result", toolUseId, isError, text}`. Skip `thinking` text by default (the signature is opaque), skip `system/thinking_tokens` and hook events.

**Adapter invocation:** `claude -p "<prompt>" --output-format stream-json --verbose --model <from release> --setting-sources project --max-turns N [--resume <sid>] --allowedTools …`, prompt first, stdin closed. Success = exit 0 and `result.is_error == false`. Map `rate_limit_event` → `usage_limit`, `assistant.error` → `error` (`authentication_failed`, …), `permission_denials` → `agent_output` with a denial flag.
