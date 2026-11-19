#!/usr/bin/env bash
# Claude Code PreToolUse hook: blocks Edit/Write outside the agent's own paths.
# Active only when JIGWORKS_AGENT is set (hub or local). Exit 2 = block, stderr goes to the agent.
set -euo pipefail
agent="${JIGWORKS_AGENT:-}"
[[ -z "$agent" ]] && exit 0

input="$(cat)"
file="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin).get("tool_input",{}); print(d.get("file_path") or d.get("notebook_path") or "")')"
[[ -z "$file" ]] && exit 0

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
abs="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$file")"
root_abs="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$root")"

case "$abs" in
  "$root_abs"/*) rel="${abs#"$root_abs"/}" ;;
  *) exit 0 ;;  # outside this worktree (scratchpad, temp files): not our concern
esac

# shellcheck source=../../scripts/ownership.sh
source "$root_abs/scripts/ownership.sh"
if is_owned "$agent" "$rel"; then
  exit 0
fi
echo "ownership-guard: agent '$agent' may not edit '$rel'. Write a proposal in build-log/agent-${agent}.md and mark the ticket blocked instead." >&2
exit 2
