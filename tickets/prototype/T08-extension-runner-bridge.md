# T08 · VS Code extension: scaffold and runner bridge

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-2` |
| Size | M |
| Demo critical path | yes |
| Depends on | T02, T06 |
| Human time | 5 min |

## Goal

The extension spawns the local runner and consumes its JSONL events.

## Acceptance criteria

- [x] `clients/vscode` builds; `pnpm --filter vscode package` produces a `.vsix` installable via `code --install-extension`.
- [x] Preflight on activation and before each session: `claude` is installed and logged in (check from T00); if not, the extension says what to run instead of starting a run that fails.
- [x] The bridge manages several runner processes at once, keyed by `runId`, and survives a webview reload without losing a running session.
- [x] Integration test (`@vscode/test-electron`) starts two runs with a fake-adapter workflow and receives events; `pnpm --filter vscode test` output pasted.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Code: `clients/vscode/src/runner/bridge.ts` (one `jigworks` process per command, keyed by runId,
JSONL stdout → events, `load()` rebuilds sessions from the runner's logs), `runner/preflight.ts`
(`claude auth status --json`; only authMethod / subscriptionType kept), `extension.ts` (host,
webviews, commands, status bar), `workflows.ts` (registry via `jigworks inspect`), `build.mjs`
(esbuild bundles). Test workflow: `clients/vscode/test-fixtures/tiny-workflow` (work → review → finish).

`pnpm --filter vscode test` (real VS Code 1.146 headless, the real runner, fake adapter, a
throwaway git workspace):

```
  Jigworks extension
    ✔ activates, finds the workspace workflow and contributes its views and commands (1087ms)
    ✔ login preflight: logged in, logged out, not installed (319ms)
    ✔ two sessions run in parallel; request changes and approve go through the runner (3185ms)
    ✔ sessions survive a webview reload and a window reload (996ms)
  4 passing (6s)
Exit code:   0
```

- Two sessions: started together, both reach `waiting_human` with their own events and
  worktrees; A approved → succeeded; B request changes → `work` attempt 2 → review → approved,
  `followUpPrompts: 1`, `firstResultCommit != finalCommit`.
- Reload: closing all panels keeps every event in the host; a fresh bridge (window reload)
  rebuilds identical event lists from `jigworks events`.
- Preflight: a fake `claude` that is logged in / logged out / missing gives ok / "run `claude`
  … /login" / "not installed"; the email from `auth status` never leaves the function. Starting a
  session runs the preflight first and shows the message instead of starting.

Package and install:

```
$ pnpm --filter vscode package
 DONE  Packaged: jigworks.vsix (9 files, 88.65 KB)
$ code --install-extension clients/vscode/jigworks.vsix --force
$ code --list-extensions | grep -i jigworks
jigworks.vscode
```

## Notes

- `code --install-extension` installed the extension into the human's own VS Code profile (that
  was the check). Remove it with `code --uninstall-extension jigworks.vscode` if unwanted.
- The default runner command is `uv run jigworks` in the workspace folder, so the extension
  works inside this repo. Another repo needs `jigworks.runnerCommand` pointing at a runner install.
  Packaging the runner itself for other repos is not done.
- Stop sends SIGTERM to the runner process; the run then shows as `interrupted` and `Resume`
  continues it (T06 resume). Not covered by the extension test.
