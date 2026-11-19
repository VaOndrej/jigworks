#!/usr/bin/env bash
# Print the URL of the Ready preview deploy of a commit (default: HEAD), waiting up to 10 min.
# Falls back to the newest Ready preview of the branch when the commit itself was skipped
# (two agents push to the same branch; Vercel may cancel a superseded build).
set -euo pipefail
sha="${1:-$(git rev-parse HEAD)}"
branch="feature/hub-and-vs-code-extension"
for _ in $(seq 1 60); do
  json="$(vercel ls jigworks --json --meta "githubCommitSha=$sha" 2>/dev/null || echo '{}')"
  state="$(jq -r '.deployments[0].state // empty' <<<"$json")"
  url="$(jq -r '.deployments[0].url // empty' <<<"$json")"
  case "$state" in
    READY) echo "https://$url"; exit 0 ;;
    ERROR) echo "preview-url: deploy of $sha failed: https://$url" >&2; exit 1 ;;
    CANCELED) break ;;
  esac
  sleep 10
done
url="$(vercel ls jigworks --json --meta "githubCommitRef=$branch" 2>/dev/null \
  | jq -r '[.deployments[] | select(.state == "READY")][0].url // empty')"
[[ -n "$url" ]] || { echo "preview-url: no Ready preview for $sha or $branch" >&2; exit 1; }
echo "preview-url: $sha has no Ready deploy; using the newest Ready preview of $branch" >&2
echo "https://$url"
