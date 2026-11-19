#!/usr/bin/env bash
# `pnpm verify:local` — LOCAL fills this in (docs/two-agent-build.md §4).
# Foundation stub: runs the local side's current tests only.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
echo "== verify:local (foundation stub: unit tests + extension skeleton test)"
pnpm --filter contracts build   # consumers import dist/
uv run pytest runner workflows sample-repo
pnpm --filter vscode test
