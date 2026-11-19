#!/usr/bin/env bash
# T12 curl transcript against a deployed hub: auth, publish → resolve stable → download bundle →
# register run → post events → read usage. Prints requests and trimmed responses, never secrets.
#   bash e2e/hub/preview-api.sh https://jigworks-xxxx.vercel.app
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=e2e/hub/env.sh
source e2e/hub/env.sh
base="${1:?usage: preview-api.sh <deployment-url>}"
: "${HUB_PASSWORD:?HUB_PASSWORD missing (.env.local)}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

bypass=()
if [[ -n "${VERCEL_AUTOMATION_BYPASS_SECRET:-}" ]]; then
  bypass=(-H "x-vercel-protection-bypass: $VERCEL_AUTOMATION_BYPASS_SECRET")
fi
key=(-H "X-Jigworks-Key: $HUB_PASSWORD")

# req <label> <auth:key|none> <METHOD> <path> [json-body]  → prints status + trimmed body, body in $tmp/body
req() {
  local auth="$1" method="$2" path="$3" body="${4:-}"
  local args=(-sS -o "$tmp/body" -D "$tmp/headers" -w '%{http_code}' -X "$method" "${bypass[@]}")
  [[ "$auth" == key ]] && args+=("${key[@]}")
  [[ -n "$body" ]] && args+=(-H 'content-type: application/json' --data-binary "$body")
  local code
  code="$(curl "${args[@]}" "$base$path")"
  printf '$ curl -X %s %s%s\n' "$method" "$path" "$([[ "$auth" == key ]] && echo '  [X-Jigworks-Key]')"
  printf '  → %s %s\n' "$code" "$(head -c 300 "$tmp/body" | tr -d '\n')"
  echo "$code" >"$tmp/code"
}
expect() { local got; got="$(cat "$tmp/code")"; [[ "$got" == "$1" ]] || { echo "FAIL: expected HTTP $1, got $got" >&2; exit 1; }; }
j() { jq -r "$1" "$tmp/body"; }

echo "# auth"
req none GET /api/health; expect 200
req none GET /api/workflows; expect 401
req none POST /api/session '{"password":"wrong"}'; expect 401
req none POST /api/session "$(jq -nc --arg p "$HUB_PASSWORD" '{password:$p}')"; expect 204
grep -i '^set-cookie' "$tmp/headers" | sed -E 's/(jigworks_session=)[^;]+/\1<redacted>/' | sed 's/^/  /'
req key GET /api/workflows; expect 200

echo; echo "# publish a smoke workflow (validated in Vercel Sandbox)"
wf="smoke-check"
version="0.1.$(date +%s)"
req key GET "/api/workflows/$wf/draft"
if [[ "$(cat "$tmp/code")" == 404 ]]; then req key PUT "/api/workflows/$wf/draft" '{"files":[]}'; expect 200; fi
jq -c --arg v "$version" '{files: [.files[] | if .path == "workflow.toml"
  then .content |= sub("version = \"[^\"]+\""; "version = \"" + $v + "\"") else . end]}' "$tmp/body" >"$tmp/draft.json"
req key PUT "/api/workflows/$wf/draft" "$(cat "$tmp/draft.json")"; expect 200
req key POST "/api/workflows/$wf/validate"; expect 200
echo "  checks: $(j '[.checks[] | "\(.name)=\(.ok)\(if .message then " (" + .message + ")" else "" end)"] | join(", ")')"
echo "  graph nodes: $(j '[.graph.nodes[]?.id] | join(" → ")')  durationMs=$(j .durationMs)"
[[ "$(j .ok)" == true ]] || { echo "FAIL: validation not ok" >&2; exit 1; }
req key POST "/api/workflows/$wf/publish" "$(jq -nc --arg v "$version" '{version:$v, channel:"stable", notes:"T12 preview transcript"}')"; expect 201
release_id="$(j .id)"; digest="$(j .digest)"
echo "  release $(j .release) id=$release_id digest=$digest bundleBytes=$(j .bundleBytes)"

echo; echo "# resolve stable → download bundle → check digest"
req key GET "/api/workflows/$wf/channels/stable"; expect 200
[[ "$(j .releaseId)" == "$release_id" && "$(j .digest)" == "$digest" ]] || { echo "FAIL: stable does not point to the new release" >&2; exit 1; }
bundle_url="$(j .bundleUrl)"
curl -sS -o "$tmp/bundle.zip" -D "$tmp/headers" "${bypass[@]}" "${key[@]}" "$base$bundle_url"
header_digest="$(grep -i '^x-jigworks-digest' "$tmp/headers" | tr -d '\r' | awk '{print $2}')"
actual="sha256:$(shasum -a 256 "$tmp/bundle.zip" | awk '{print $1}')"
echo "\$ curl $bundle_url  [X-Jigworks-Key]"
echo "  → $(wc -c <"$tmp/bundle.zip" | tr -d ' ') bytes, X-Jigworks-Digest=$header_digest, sha256(bytes)=$actual"
[[ "$actual" == "$digest" && "$header_digest" == "$digest" ]] || { echo "FAIL: digest mismatch" >&2; exit 1; }
unzip -l "$tmp/bundle.zip" | tail -n +4 | head -n -2 | awk '{print "    " $4}'

echo; echo "# register a run → post events (twice) → read usage"
run_id="run_smoke_$(date +%s)"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
create="$(jq -nc --arg r "$run_id" --arg wf "$wf" --arg rel "$wf@$version" --arg id "$release_id" --arg d "$digest" --arg t "$now" \
  '{runId:$r, workflowId:$wf, releaseId:$id, release:$rel, digest:$d, authorEmail:"hub-agent@example.com",
    models:{default:"claude-sonnet-5"}, adapter:"fake", title:"T12 preview transcript", stepsPlanned:3, startedAt:$t}')"
req key POST /api/runs "$create"; expect 201
events="$(jq -nc --arg r "$run_id" --arg wf "$wf" --arg rel "$wf@$version" --arg id "$release_id" --arg d "$digest" --arg t "$now" '
  {events: [
    {runId:$r, seq:0, kind:"run_started", at:$t, release:$rel, digest:$d, runStatus:"running", progress:0, step:0, stepsPlanned:3,
     runStarted:{workflowId:$wf, release:$rel, releaseId:$id, digest:$d, authorEmail:"hub-agent@example.com",
                 models:{default:"claude-sonnet-5"}, adapter:"fake", title:"T12 preview transcript",
                 plannedPath:["plan","approve_plan","implement"]}},
    {runId:$r, seq:1, kind:"node_status", at:$t, release:$rel, node:"plan", attempt:1, status:"running", model:"claude-sonnet-5", progress:0, step:0, stepsPlanned:3},
    {runId:$r, seq:2, kind:"usage", at:$t, release:$rel, node:"plan", attempt:1,
     usage:{runId:$r, node:"plan", attempt:1, model:"claude-sonnet-5", adapter:"fake", input:40, output:2100, cache_write:18400, cache_read:96000, at:$t}},
    {runId:$r, seq:3, kind:"node_status", at:$t, release:$rel, node:"plan", attempt:1, status:"succeeded", progress:20, step:1, stepsPlanned:3}
  ]}')"
req key POST "/api/runs/$run_id/events" "$events"; expect 200
req key POST "/api/runs/$run_id/events" "$events"; expect 200
[[ "$(j .duplicates)" == 4 ]] || { echo "FAIL: replay was not deduplicated" >&2; exit 1; }
req key GET "/api/runs/$run_id/events?after=1"; expect 200
req key GET "/api/runs/$run_id"; expect 200
echo "  status=$(j .summary.status) progress=$(j .summary.progress) currentNode=$(j '.summary.currentNode // "-"') costUsd=$(j .summary.costUsd)"
req key GET "/api/analytics/usage?groupBy=release&workflowId=$wf"; expect 200
row="$(jq -r --arg rel "$wf@$version" '.costLabel as $l | .rows[] | select(.key == $rel)
  | "\(.key): runs=\(.runs) input=\(.input) output=\(.output) cache_write=\(.cache_write) cache_read=\(.cache_read) costUsd=\(.costUsd) (\($l))"' "$tmp/body")"
echo "  $row"
[[ -n "$row" ]] || { echo "FAIL: no usage row for the new release" >&2; exit 1; }

echo; echo "# SSE stream (ends after the function's stream window; clients reconnect)"
curl -sS -N --max-time 40 "${bypass[@]}" "${key[@]}" "$base/api/runs/$run_id/events/stream?after=-1" >"$tmp/sse" || true
echo "\$ curl -N /api/runs/$run_id/events/stream?after=-1  [X-Jigworks-Key]"
echo "  → $(grep -c '^id: ' "$tmp/sse") messages: $(grep '^event: ' "$tmp/sse" | awk '{print $2}' | paste -sd, -)"
[[ "$(grep -c '^id: ' "$tmp/sse")" == 4 ]] || { echo "FAIL: SSE did not replay the 4 events" >&2; exit 1; }

echo; echo "preview-api: OK ($base)"
