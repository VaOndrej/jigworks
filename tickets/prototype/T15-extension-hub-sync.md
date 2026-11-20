# T15 · Extension syncs from the hub `stable` channel

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-3` |
| Size | S |
| Demo critical path | no (below the cut line) |
| Depends on | T09, T12 |
| Human time | — |

## Goal

The extension resolves `stable`, downloads the bundle, verifies the digest and runs the pinned version.

## Acceptance criteria

- [x] Settings: hub URL in VS Code settings; the hub password in VS Code SecretStorage (never in settings.json), sent as `X-Jigworks-Key`. A wrong password shows a clear error.
- [x] Test or recording: publish v1 → run → publish v2 → roll the channel back to v1 → the extension picks up v1.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Code: `clients/vscode/src/hub.ts` (client: `X-Jigworks-Key`, a clear 401 message, optional
bypass header), `extension.ts` (`Jigworks: Set hub password` → `context.secrets`;
`Jigworks: Sync workflows from the hub`: `GET /api/workflows` → `GET …/channels/stable` →
download unless the digest is already cached → digest checked against the **channel
resolution**, then `jigworks unpack` → the sidebar shows the current `stable`; syncs on activation
when `jigworks.hubUrl` is set). Runs started from VS Code get the hub URL and key in their
environment, so their events sync to the same hub (T14).

`pnpm --filter vscode test` (real VS Code, the runner's contract-validating fake hub as a process,
releases built with the new `jigworks bundle`):

```
  Jigworks extension
    ✔ activates, finds the workspace workflow and contributes its views and commands (1275ms)
    ✔ login preflight: logged in, logged out, not installed (365ms)
    ✔ two sessions run in parallel; request changes and approve go through the runner (3044ms)
    ✔ import a workflow .zip: valid bundle accepted, tampered bundle refused (860ms)
    ✔ sessions survive a webview reload and a window reload (985ms)
  Jigworks hub sync (T15)
    ✔ the password lives in secret storage; a wrong one is a clear error
    ✔ publish v1 → run → publish v2 → roll stable back to v1 → the extension picks up v1 (4611ms)
  7 passing (11s)
```

The T15 test: wrong password → "The hub refused the password. Run “Jigworks: Set hub password” …",
and the password is not in `.vscode/settings.json`. Publish tiny 0.1.0 to `stable` → sync → the
sidebar has `tiny@0.1.0` (digest = bundle digest) → a session runs on it (`run_started.release =
tiny@0.1.0`) and its events reach the hub → publish 0.2.0 → sync → `tiny@0.2.0` → `PUT
/api/workflows/tiny/channels/stable {releaseId: v1}` → sync → `tiny@0.1.0` with the v1 digest
again; the running session stayed on 0.1.0.

## Notes

- **Not run against the real hub preview** (same reason as T14: the session may not load the hub
  password). The client follows `openapi.json`; HUB's preview transcript (T12) shows the same
  endpoints answering.
- After a window reload the hub workflows reappear on the next sync (on activation), not from the
  cache, so the sidebar never shows a `stable` that has since moved. Offline, hub workflows are
  missing until the hub is reachable again.
- Only `stable` is synced; `beta` and an "offer the new version" prompt (design.md §6) are not built.
