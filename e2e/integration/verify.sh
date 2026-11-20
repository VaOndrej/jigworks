#!/usr/bin/env bash
# `pnpm verify:e2e` (docs/two-agent-build.md §4): publish in the hub → the extension syncs `stable`
# → fake-adapter run → the run's events appear in Runs & analytics.
#
# The hub is HUB's real FastAPI app (apps/hub-api) under uvicorn, on a private Postgres from the
# Homebrew binaries (Docker is optional), with the local Sandbox fixture and bundles in the
# database, so the check needs no cloud secrets. The extension part runs in a real VS Code
# (@vscode/test-electron, suite "e2e").
#   pnpm verify:e2e
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
root="$(pwd)"
pgbin="${JIGWORKS_PG_BIN:-/opt/homebrew/opt/postgresql@16/bin}"
pgport=54339             # not HUB's 54329
api_port=8766
key="local-e2e-key"      # local only; never the deployed secret
work="$(mktemp -d "${TMPDIR:-/tmp}/jigworks-e2e.XXXXXX")"
pgdata="$work/pg"
db="postgresql://jigworks@127.0.0.1:$pgport/jigworks_e2e_local"
api_pid=""

cleanup() {
  [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true
  "$pgbin/pg_ctl" -D "$pgdata" -m fast stop >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

step() { printf '\n== %s\n' "$*"; }

step "contracts build"
pnpm --filter contracts build >/dev/null && echo ok

step "private Postgres on $pgport ($pgdata)"
# C locale (the host locale may lack a text-search config); TCP only: a Unix socket under $TMPDIR
# would exceed the 103-character socket path limit on macOS.
LC_ALL=C "$pgbin/initdb" -D "$pgdata" -U jigworks --auth=trust --locale=C -E UTF8 >/dev/null
LC_ALL=C "$pgbin/pg_ctl" -D "$pgdata" -o "-p $pgport -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" \
  -l "$work/pg.log" -w start >/dev/null || { tail -20 "$work/pg.log"; exit 1; }
"$pgbin/createdb" -h 127.0.0.1 -p "$pgport" -U jigworks jigworks_e2e_local
echo ok

step "hub-api (real app) on :$api_port"
DATABASE_URL="$db" HUB_PASSWORD="$key" JIGWORKS_SANDBOX=fixture JIGWORKS_BUNDLE_STORE=db BLOB_READ_WRITE_TOKEN= VERCEL_OIDC_TOKEN= \
  uv run --quiet --with uvicorn uvicorn hub_api.main:app --port "$api_port" >"$work/api.log" 2>&1 &
api_pid=$!
hub="http://127.0.0.1:$api_port"
for _ in $(seq 1 60); do curl -sf "$hub/api/health" >/dev/null 2>&1 && break; sleep 0.5; done
curl -sf "$hub/api/health" || { echo "hub did not start"; tail -30 "$work/api.log"; exit 1; }
echo

step "publish workflows/feature-development to stable (PUT draft, POST publish)"
release="$(HUB_PASSWORD="$key" uv run --quiet python e2e/integration/publish.py "$hub" workflows/feature-development)"
echo "$release" | jq -c '{id, workflowId, version, digest, channels}'

step "VS Code: sync stable → fake-adapter run → approve (suite e2e)"
out="$work/e2e-run.json"
if ! JIGWORKS_E2E_HUB_URL="$hub" JIGWORKS_E2E_HUB_KEY="$key" JIGWORKS_E2E_OUT="$out" JIGWORKS_TEST_GREP="e2e" \
  pnpm --filter vscode test >"$work/vscode.log" 2>&1; then
  grep -v -E "AgentHost|ChatModel|node-compile-cache" "$work/vscode.log" | grep -A 25 "failing"
  echo "--- hub log"; tail -15 "$work/api.log"
  exit 1
fi
grep -E "  ✔|passing" "$work/vscode.log"
run_id="$(jq -r .runId "$out")"
echo "run: $run_id ($(jq -r .release "$out"), digest $(jq -r .digest "$out" | cut -c1-19)…)"

step "Runs & analytics in the hub"
h=(-sS -H "X-Jigworks-Key: $key")
curl "${h[@]}" "$hub/api/runs/$run_id" | jq -c '.summary | {runId, status, release, digest: (.digest[0:19] + "…"), progress, fixLoops, followUpPrompts, costUsd, approverEmail}'
hub_events="$(curl "${h[@]}" "$hub/api/runs/$run_id/events?limit=500" | jq '.events | length')"
local_events="$(jq -r .events "$out")"
echo "events: $hub_events in the hub, $local_events in the runner"
curl "${h[@]}" "$hub/api/runs?limit=5" | jq -r '.runs[] | "  \(.runId)  \(.release)  \(.status)  $\(.costUsd)"'
echo "analytics (usage by release):"
curl "${h[@]}" "$hub/api/analytics/usage?groupBy=release&workflowId=feature-development" | jq -c '.rows[] | {key, runs, input, output, costUsd}'
[[ "$hub_events" == "$local_events" ]] || { echo "FAIL: event counts differ" >&2; exit 1; }
[[ "$(curl "${h[@]}" "$hub/api/runs/$run_id" | jq -r .summary.status)" == "succeeded" ]] || { echo "FAIL: run not succeeded in the hub" >&2; exit 1; }
echo; echo "verify:e2e OK"
