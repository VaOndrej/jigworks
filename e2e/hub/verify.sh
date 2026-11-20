#!/usr/bin/env bash
# `pnpm verify:hub` (docs/two-agent-build.md §4).
#   1. contracts build, local Postgres, hub-api + contract tests
#   2. hub-web typecheck + unit tests
#   3. Playwright at 1440 px on localhost (uvicorn + vite, see local-e2e.sh)
#   4. preview: the API transcript and the same Playwright suite against the branch preview
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

step "local Postgres on port 54329"
if (exec 3<>/dev/tcp/127.0.0.1/54329) 2>/dev/null; then
  echo "already listening on 54329 (docker compose project 'jigworks', or the fallback instance in the build log)"
else
  docker compose -p jigworks up -d --wait db 2>&1 | tail -1
fi

step "uv run pytest apps/hub-api packages/contracts"
uv run pytest apps/hub-api packages/contracts -q -p no:cacheprovider 2>&1 | grep -v '^warning: `VIRTUAL_ENV'

step "hub-web typecheck + unit tests"
pnpm --filter @jigworks/hub-web test 2>&1 | tail -4

step "Playwright on localhost (1440 px)"
bash e2e/hub/local-e2e.sh 2>&1 | grep -E '✓|✘|passed|failed|Error' 

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

step "Playwright on the preview (1440 px)"
HUB_URL="$preview" HUB_TARGET=preview pnpm exec playwright test -c e2e/hub/playwright.config.ts 2>&1 | grep -E '✓|✘|passed|failed|Error'

echo; echo "verify:hub passed"
