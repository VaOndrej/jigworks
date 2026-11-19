# T08 · VS Code extension: scaffold and runner bridge

| Field | Value |
|---|---|
| Status | todo |
| Label | `milestone-2` |
| Size | M |
| Demo critical path | yes |
| Depends on | T02, T06 |
| Human time | 5 min |

## Goal

The extension spawns the local runner and consumes its JSONL events.

## Acceptance criteria

- [ ] `clients/vscode` builds; `pnpm --filter vscode package` produces a `.vsix` installable via `code --install-extension`.
- [ ] Integration test (`@vscode/test-electron`) starts a run with a fake-adapter workflow and receives events; `pnpm --filter vscode test` output pasted.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
