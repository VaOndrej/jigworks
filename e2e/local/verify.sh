#!/usr/bin/env bash
# `pnpm verify:local` (docs/two-agent-build.md §4). LOCAL fills it in ticket by ticket.
#   JIGWORKS_LIVE=1 pnpm verify:local   # also runs the opt-in live `claude -p` tests (Max subscription)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
echo "== verify:local"
pnpm --filter contracts build   # consumers import dist/

echo "== python: runner, workflows, sample-repo (fake adapter, recorded fixtures, property tests)"
# Keep temp dirs only for failing tests (each workflow test copies a git repo).
uv run pytest runner workflows sample-repo -q -o tmp_path_retention_policy=failed

echo "== sample-repo: planted bugs must be caught by the property tests"
bash sample-repo/scripts/break-invariant.sh all

echo "== vscode: @vscode/test-electron (real extension, real runner, fake adapter)"
pnpm --filter vscode test

echo "== vscode: standalone webview + Playwright screenshots at 1440 px (e2e/local/screenshots/)"
pnpm --filter vscode exec tsc -p tsconfig.webview.json
pnpm --filter vscode test:ui

if [[ "${JIGWORKS_LIVE:-}" == "1" ]]; then
  echo "== live: real claude -p calls"
  uv run pytest runner workflows -m live -q
else
  echo "== live: skipped (set JIGWORKS_LIVE=1)"
fi
echo "== verify:local OK"
