# T08 · VS Code extension: scaffold and runner bridge

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-2` |
| Size | M |
| Demo critical path | yes |
| Depends on | T02, T06 |
| Human time | 5 min |

## Goal

The extension spawns the local runner and consumes its JSONL events.

## Acceptance criteria

- [ ] `clients/vscode` builds; `pnpm --filter vscode package` produces a `.vsix` installable via `code --install-extension`.
- [ ] Preflight on activation and before each session: `claude` is installed and logged in (check from T00); if not, the extension says what to run instead of starting a run that fails.
- [ ] The bridge manages several runner processes at once, keyed by `runId`, and survives a webview reload without losing a running session.
- [ ] Integration test (`@vscode/test-electron`) starts two runs with a fake-adapter workflow and receives events; `pnpm --filter vscode test` output pasted.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
