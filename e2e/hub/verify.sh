#!/usr/bin/env bash
# `pnpm verify:hub` — HUB fills this in (docs/two-agent-build.md §4).
# Foundation stub: runs the hub's current tests only.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
echo "== verify:hub (foundation stub: unit tests only, no Postgres, no Playwright yet)"
uv run pytest apps/hub-api
pnpm --filter @jigworks/hub-web test
