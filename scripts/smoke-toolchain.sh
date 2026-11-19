#!/usr/bin/env bash
# Toolchain smoke test (T01). Run with the human present: macOS may ask for
# permissions (the VS Code test download, Docker, network) the first time.
# Usage: bash scripts/smoke-toolchain.sh [--skip-deploy]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

redact() {
  sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]+/<email>/g;
          s/"(orgId|orgName|accountUuid|organizationId|organizationName)": *"[^"]*"/"\1": "<redacted>"/g'
}

step() { printf '\n=== %s\n' "$1"; }

step "1/5 Playwright headless screenshot (390 px + 1440 px)"
pnpm exec playwright test -c e2e/smoke
ls -l e2e/screenshots/smoke-390.png e2e/screenshots/smoke-1440.png

step "2/5 hello-world extension under @vscode/test-electron"
pnpm --filter vscode test

step "3/5 docker compose up -d db + one query"
docker compose up -d --wait db
docker compose exec -T db psql -U jigworks -d jigworks -tAc "select 'postgres ok: ' || version();"

step "4/5 vercel deploy of the skeleton (preview)"
if [[ "${1:-}" == "--skip-deploy" ]]; then
  echo "skipped (--skip-deploy)"
else
  url="$(vercel deploy --yes 2>/dev/null | grep -Eo 'https://[a-z0-9-]+\.vercel\.app' | tail -1)"
  echo "preview: $url"
  printf 'GET /api/health -> '
  vercel curl /api/health --deployment "$url" -- -s 2>/dev/null | tail -1
  echo
  printf 'GET / -> HTTP '
  vercel curl / --deployment "$url" -- -s -o /dev/null -w '%{http_code}' 2>/dev/null | tail -1
  echo
fi

step "5/5 claude login check + one tiny claude -p call"
claude --version
claude auth status | redact
claude auth status | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["loggedIn"], "claude is not logged in"; print("loggedIn:", d["loggedIn"], "| authMethod:", d.get("authMethod"), "| subscription:", d.get("subscriptionType"))'
claude -p "Reply with exactly the word: ok" --model haiku --output-format json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("result:", d["result"].strip(), "| is_error:", d["is_error"], "| cost_usd:", d.get("total_cost_usd"))'

printf '\nSMOKE TEST PASSED\n'
