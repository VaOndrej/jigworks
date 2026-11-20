# T10 · "Import workflow from file" (.zip fallback)

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-2` |
| Size | S |
| Demo critical path | no |
| Depends on | T09 |
| Human time | — |

## Goal

The distribution fallback from design.md §6, so the demo story works without the hub.

## Acceptance criteria

- [x] The command imports a `.zip`, verifies the digest and unpacks it to the extension cache.
- [x] Tests with a valid and a tampered zip pass; output pasted.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Flow: **Jigworks: Import workflow from file** (sidebar "Import") → pick a `.zip` → expected digest
from the `<zip>.sha256` next to it, otherwise asked for (as shown in the hub) → the extension hashes
the file (`src/bundles.ts`) → `jigworks unpack` verifies again with the frozen contract's
`read_bundle` (digest + unsafe paths) and writes nothing unless both pass → the package lands in
`<globalStorage>/workflows/<digest prefix>/package/` with `jigworks-source.json` → it appears in
the sidebar as the active workflow, identified by the bundle digest.

Runner side, `uv run pytest runner/tests/test_unpack.py -v`:

```
test_unpack_valid_bundle_with_sidecar_digest[1.2.0] PASSED
test_unpack_valid_bundle_with_sidecar_digest[1.3.0] PASSED
test_unpack_tampered_bundle_is_refused_and_nothing_is_written PASSED
test_unpack_wrong_digest_is_refused PASSED
test_unpack_unsafe_path_is_refused PASSED
test_unpack_our_package_bundle_roundtrip PASSED
============================== 6 passed in 2.94s ===============================
```

Extension side, `pnpm --filter vscode test` (real VS Code):

```
    ✔ activates, finds the workspace workflow and contributes its views and commands (1280ms)
    ✔ login preflight: logged in, logged out, not installed (214ms)
    ✔ two sessions run in parallel; request changes and approve go through the runner (3069ms)
    ✔ import a workflow .zip: valid bundle accepted, tampered bundle refused (846ms)
    ✔ sessions survive a webview reload and a window reload (1012ms)
  5 passing (6s)
```

The import test uses `packages/contracts/fixtures/bundles/feature-development-1.3.0.zip` (accepted,
digest = the `.sha256`, graph drawn, becomes the active workflow) and
`feature-development-1.3.0.tampered.zip` with the 1.3.0 digest (rejected with `digest_mismatch`,
the cache directory unchanged).

## Notes

- The T02 fixture bundles use absolute imports (`from steps import nodes`); the runner's package
  loader now supports both relative and absolute imports, and drops a package's top-level modules
  after import so two packages never share `steps`.
- The fixture bundles are contract fixtures: their nodes do not call the runtime, so an imported
  1.2.0/1.3.0 can be inspected and drawn but not meaningfully run. The runnable package is
  `workflows/feature-development` 1.4.0.
