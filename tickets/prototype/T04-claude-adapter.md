# T04 · Runner: Claude CLI adapter

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | yes |
| Depends on | T00, T02 |
| Human time | 5 min |

## Goal

`run(prompt, cwd, options) → result + events` (design.md §7) over `claude -p --output-format stream-json`.

## Acceptance criteria

- [ ] The adapter streams normalized `RunEvent`s and returns a `UsageRecord` per call; it supports `--resume`, `--allowedTools`, `--permission-mode` and the model, which always comes from the workflow release (never from the user).
- [ ] Passes the agent's text and tool calls through as `agent_output` events (for the extension's "Agent output" tab), and turns a subscription usage limit into a `usage_limit` event instead of a crash.
- [ ] `uv run pytest runner -k adapter` passes against the T00 fixtures (no live call in tests).
- [ ] Cost is computed from a price table with validity (`model, token_type, price_per_mtok, valid_from`), cache tokens priced separately; `total_cost_usd` is only compared as a cross-check.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
