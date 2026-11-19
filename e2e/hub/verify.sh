#!/usr/bin/env bash
# `pnpm verify:hub` (docs/two-agent-build.md §4).
#   1. contracts build, local Postgres, hub-api + contract tests
#   2. hub-web unit tests
#   3. preview: the API transcript (and, from T13, Playwright) against the newest branch preview
# Usage: pnpm verify:hub [--local-only] [--preview <url>]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=e2e/hub/env.sh
source e2e/hub/env.sh

local_only=0
preview="${HUB_PREVIEW_URL:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --local-only) local_only=1 ;;
    --preview) preview="$2"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n== %s\n' "$*"; }

step "contracts build (consumers import dist/)"
pnpm --filter contracts build >/dev/null && echo "ok"

step "local Postgres (docker compose project 'jigworks', port 54329)"
docker compose -p jigworks up -d --wait db 2>&1 | tail -1

step "uv run pytest apps/hub-api packages/contracts"
uv run pytest apps/hub-api packages/contracts -q -p no:cacheprovider 2>&1 | grep -v '^warning: `VIRTUAL_ENV'

step "hub-web unit tests"
pnpm --filter @jigworks/hub-web test 2>&1 | tail -4

if [[ $local_only == 1 ]]; then
  echo; echo "verify:hub local stages passed (preview skipped: --local-only)"
  exit 0
fi

if [[ -z "$preview" ]]; then
  step "find the newest preview of this commit"
  preview="$(bash e2e/hub/preview-url.sh)"
fi
echo "preview: ${preview}"

step "API transcript against the preview"
bash e2e/hub/preview-api.sh "$preview"

echo; echo "verify:hub passed"
