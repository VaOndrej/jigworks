#!/usr/bin/env bash
# Playwright at 1440 px on localhost: hub-api under uvicorn (fresh seeded database `jigworks_e2e`,
# Sandbox mocked with the contract fixture) behind the Vite dev server's /api proxy, the same
# routing as vercel.json. Screenshots: e2e/hub/screenshots/local-*.png
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
api_port=8765
web_port=5174
export HUB_PASSWORD="local-e2e-password"   # local only; never the deployed secret
db="postgresql://jigworks:jigworks@localhost:54329/jigworks_e2e"

uv run python - <<'EOF'
import psycopg
with psycopg.connect("postgresql://jigworks:jigworks@localhost:54329/jigworks", autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS jigworks_e2e WITH (FORCE)")
    c.execute("CREATE DATABASE jigworks_e2e")
print("fresh database jigworks_e2e")
EOF

logs="$(mktemp -d)"
DATABASE_URL="$db" JIGWORKS_SANDBOX=fixture JIGWORKS_BUNDLE_STORE=db BLOB_READ_WRITE_TOKEN= VERCEL_OIDC_TOKEN= \
  uv run --with uvicorn uvicorn hub_api.main:app --port "$api_port" >"$logs/api.log" 2>&1 &
api_pid=$!
HUB_API_URL="http://127.0.0.1:$api_port" pnpm --filter @jigworks/hub-web exec vite --port "$web_port" --strictPort >"$logs/web.log" 2>&1 &
web_pid=$!
cleanup() { kill "$api_pid" "$web_pid" 2>/dev/null || true; pkill -P "$web_pid" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 60); do
  curl -sf "http://localhost:$web_port/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://localhost:$web_port/api/health" >/dev/null || { echo "local stack did not start"; tail -20 "$logs"/*.log; exit 1; }
mkdir -p e2e/hub/screenshots
HUB_URL="http://localhost:$web_port" HUB_TARGET=local VERCEL_AUTOMATION_BYPASS_SECRET= \
  pnpm exec playwright test -c e2e/hub/playwright.config.ts
