# T00 · Spike: `claude -p --output-format stream-json`

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-0` |
| Size | S |
| Demo critical path | yes |
| Depends on | none |
| Human time | 5 min to read the findings |

## Goal

Confirm the facts the runner and analytics depend on, before any code is written. This is "spike B" in design.md §8 and §11.4.

## Acceptance criteria

- [ ] `scripts/spike-claude.sh` reproduces every observation below; `bash scripts/spike-claude.sh` exits 0.
- [ ] Recorded, scrubbed transcripts in `runner/tests/fixtures/stream-json/`: one plain run, one `--resume` run, one denied tool.
- [ ] `docs/spikes/claude-stream-json.md` documents the exact path and names of the usage fields (input, output, cache write, cache read), `total_cost_usd`, `session_id` and the model name, and whether usage is reported per message or only in the final `result` event.
- [ ] Confirms `--resume <session_id>` continues the session (the second run sees context from the first).
- [ ] Confirms `--allowedTools` blocks a non-listed tool and shows what the denial event looks like; same for `--permission-mode`.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
