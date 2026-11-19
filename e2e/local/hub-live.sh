#!/usr/bin/env bash
# Runner → real hub (T14 live check): a fake-adapter run against a hub deployment, synced while it
# runs, then read back from the hub API. Secrets come from this worktree's .env.local and are
# never printed.
#   bash e2e/local/hub-live.sh https://jigworks-xxxx.vercel.app
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi
: "${HUB_PASSWORD:?HUB_PASSWORD missing (.env.local)}"
export JIGWORKS_HUB_URL="${1:?usage: hub-live.sh <hub url>}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo"
cp -R sample-repo "$repo/sample-repo"
rm -rf "$repo/sample-repo/scripts" "$repo/sample-repo/.hypothesis"
printf '__pycache__/\n.hypothesis/\n.pytest_cache/\n' > "$repo/.gitignore"
git -C "$repo" init -q -b main
git -C "$repo" -c user.email=hub-live@example.com -c user.name="Hub live check" add -A
git -C "$repo" -c user.email=hub-live@example.com -c user.name="Hub live check" commit -q -m base
git -C "$repo" config user.email hub-live@example.com
git init -q --bare "$tmp/remote.git"
cat > "$tmp/script.json" <<'JSON'
{"plan": [{"text": "1. Add describe(order) to sample_repo/notes.py.\n2. Test it."}],
 "write_tests": [{"text": "added test_notes.py", "files": {"sample-repo/tests/test_notes.py": "from sample_repo.notes import describe\n\n\ndef test_describe():\n    assert describe\n"}}],
 "implement": [{"text": "implemented describe", "files": {"sample-repo/sample_repo/notes.py": "def describe(order):\n    return f\"{order.side.value} {order.quantity} {order.instrument}\"\n"}}],
 "review": [{"text": "describe() has no docstring\nVERDICT: FAIL"}, {"text": "VERDICT: PASS"}],
 "fix": [{"text": "added a docstring", "files": {"sample-repo/sample_repo/notes.py": "def describe(order):\n    \"\"\"One-line description of an order.\"\"\"\n    return f\"{order.side.value} {order.quantity} {order.instrument}\"\n"}}],
 "summary": [{"text": "describe(order) added; one review fix loop."}]}
JSON

run_id="run_hublive_$(date -u +%Y%m%d%H%M%S)"
jw() { uv run --quiet jigworks "$@"; }
echo "# $run_id against $JIGWORKS_HUB_URL (fake adapter)"
jw run --workflow workflows/feature-development --repo "$repo/sample-repo" --prompt "Add describe(order) (hub live check)" \
  --adapter fake --fake-script "$tmp/script.json" --run-id "$run_id" --home "$tmp/home" --pr-remote "$tmp/remote.git" >/dev/null
jw approve "$run_id" --home "$tmp/home" >/dev/null
jw approve "$run_id" --home "$tmp/home" >/dev/null
local_n="$(wc -l < "$tmp/home/runs/$run_id/events.jsonl" | tr -d ' ')"

hdr=(-H "X-Jigworks-Key: $HUB_PASSWORD")
[[ -n "${VERCEL_AUTOMATION_BYPASS_SECRET:-}" ]] && hdr+=(-H "x-vercel-protection-bypass: $VERCEL_AUTOMATION_BYPASS_SECRET")
curl -sS "${hdr[@]}" "$JIGWORKS_HUB_URL/api/runs/$run_id/events?limit=500" > "$tmp/events.json"
curl -sS "${hdr[@]}" "$JIGWORKS_HUB_URL/api/runs/$run_id" > "$tmp/run.json"
hub_n="$(jq '.events | length' "$tmp/events.json")"
echo "local events: $local_n, on the hub: $hub_n"
jq -c '{status: .summary.status // .status, release: (.summary.release // .release), followUpPrompts: (.summary.followUpPrompts // .followUpPrompts), fixLoops: (.summary.fixLoops // .fixLoops), progress: (.summary.progress // .progress), costUsd: (.summary.costUsd // .costUsd)}' "$tmp/run.json"
[[ "$local_n" == "$hub_n" ]] || { echo "FAIL: event counts differ" >&2; exit 1; }
echo "hub-live: OK ($run_id)"
