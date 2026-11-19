# T15 · Extension syncs from the hub `stable` channel

| Field | Value |
|---|---|
| Status | todo |
| Owner | local |
| Label | `milestone-3` |
| Size | S |
| Demo critical path | no (below the cut line) |
| Depends on | T09, T12 |
| Human time | — |

## Goal

The extension resolves `stable`, downloads the bundle, verifies the digest and runs the pinned version.

## Acceptance criteria

- [ ] Settings: hub URL in VS Code settings; the hub password in VS Code SecretStorage (never in settings.json), sent as `X-Jigworks-Key`. A wrong password shows a clear error.
- [ ] Test or recording: publish v1 → run → publish v2 → roll the channel back to v1 → the extension picks up v1.

## Evidence

_Paste command output, screenshots or links here when the ticket is done._
