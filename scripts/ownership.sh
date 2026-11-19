# shellcheck shell=bash
# Path ownership for the two-agent build (AGENTS.md "Parallel build").
# Source this file, then call: is_owned <hub|local> <repo-relative-path>
# Shared lockfiles are writable by both agents (rebase rule in AGENTS.md).

is_owned() {
  local agent="$1" path="$2"
  case "$path" in
    pnpm-lock.yaml|uv.lock) return 0 ;;
  esac
  case "$agent" in
    hub)
      case "$path" in
        apps/hub-api/*|apps/hub-web/*|vercel.json|e2e/hub/*) return 0 ;;
        packages/contracts/openapi.json) return 0 ;;
        tickets/prototype/T11-*|tickets/prototype/T12-*|tickets/prototype/T13-*) return 0 ;;
        build-log/agent-hub.md) return 0 ;;
      esac
      ;;
    local)
      case "$path" in
        runner/*|workflows/*|sample-repo/*|clients/vscode/*) return 0 ;;
        e2e/local/*|e2e/integration/*) return 0 ;;
        tickets/prototype/T0[3-9]-*|tickets/prototype/T10-*) return 0 ;;
        tickets/prototype/T1[4-7]-*) return 0 ;;
        build-log/agent-local.md) return 0 ;;
      esac
      ;;
    *)
      echo "ownership: unknown agent '$agent' (expected hub or local)" >&2
      return 2
      ;;
  esac
  return 1
}
