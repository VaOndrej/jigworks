# shellcheck shell=bash
# Source me: loads this worktree's .env.local (HUB_PASSWORD, BLOB_READ_WRITE_TOKEN,
# VERCEL_AUTOMATION_BYPASS_SECRET) into the environment of the verify scripts. Never prints values.
_jw_env="$(git rev-parse --show-toplevel)/.env.local"
if [[ -f "$_jw_env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$_jw_env"
  set +a
else
  echo "env.sh: no .env.local in this worktree (vercel env pull .env.local)" >&2
fi
unset _jw_env
