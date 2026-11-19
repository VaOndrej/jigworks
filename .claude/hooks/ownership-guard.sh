#!/usr/bin/env bash
# Claude Code PreToolUse hook: blocks Edit/Write outside the agent's own paths.
# The agent is taken from the worktree that contains the file (its
# .claude/settings.local.json), so the guard also holds for a session that was
# started in another folder. Exit 2 = block; stderr goes to the agent.
set -euo pipefail

input="$(cat)"
file="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin).get("tool_input",{}); print(d.get("file_path") or d.get("notebook_path") or "")')"
[[ -z "$file" ]] && exit 0

abs="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$file")"
dir="$(dirname "$abs")"
while [[ ! -d "$dir" ]]; do dir="$(dirname "$dir")"; done
root="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -z "$root" ]] && exit 0  # not in a git checkout (scratchpad, temp files)
root="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$root")"

lib="$root/scripts/ownership.sh"
[[ -f "$lib" ]] || lib="$(cd "$(dirname "$0")/../.." && pwd)/scripts/ownership.sh"
# shellcheck source=../../scripts/ownership.sh
source "$lib"

session="${JIGWORKS_AGENT:-}"
target="$(worktree_agent "$root")"
rel="${abs#"$root"/}"

if [[ -z "$target" ]]; then
  [[ -z "$session" ]] && exit 0  # human / foundation work in a normal checkout
  echo "ownership-guard: agent '$session' writes only inside its own worktree; '$abs' is outside it." >&2
  exit 2
fi
if [[ -n "$session" && "$session" != "$target" ]]; then
  echo "ownership-guard: agent '$session' may not write into the '$target' worktree ($abs)." >&2
  exit 2
fi
if is_owned "$target" "$rel"; then
  exit 0
fi
echo "ownership-guard: agent '$target' may not edit '$rel'. Write a proposal in build-log/agent-${target}.md and mark the ticket blocked instead." >&2
exit 2
