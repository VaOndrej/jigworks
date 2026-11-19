#!/usr/bin/env bash
# Usage: scripts/check-ownership.sh <hub|local> [--range <rev-range>]
# Without --range it checks the staged files (run it before every commit).
# With --range it checks every file touched by the commits in the range.
set -euo pipefail

agent="${1:-}"
if [[ "$agent" != "hub" && "$agent" != "local" ]]; then
  echo "usage: $0 <hub|local> [--range <rev-range>]" >&2
  exit 2
fi
shift

root="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/ownership.sh
source "$root/scripts/ownership.sh"

if [[ "${1:-}" == "--range" ]]; then
  files="$(git diff --name-only "${2:?missing rev-range}")"
  what="commits in ${2}"
else
  files="$(git diff --cached --name-only)"
  what="staged files"
fi

violations=()
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if ! is_owned "$agent" "$f"; then
    violations+=("$f")
  fi
done <<< "$files"

if (( ${#violations[@]} > 0 )); then
  echo "check-ownership: agent '$agent' may not change these paths (${what}):" >&2
  printf '  %s\n' "${violations[@]}" >&2
  echo "If you need a change there, write a proposal in build-log/agent-${agent}.md and mark the ticket blocked." >&2
  exit 1
fi
echo "check-ownership: OK for agent '$agent' (${what}: $(grep -c . <<< "$files" || true) files)"
