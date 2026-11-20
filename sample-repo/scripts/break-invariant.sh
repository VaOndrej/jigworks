#!/usr/bin/env bash
# Apply a plausible-looking bug to sample-repo (in a temp copy) and show the property tests
# catch it. Exit 0 = caught. See INVARIANTS.md and break_invariant.py for the options:
#   bash sample-repo/scripts/break-invariant.sh            # default bug (overfill, I1)
#   bash sample-repo/scripts/break-invariant.sh all        # every bug
#   bash sample-repo/scripts/break-invariant.sh --list
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here/../.."
exec uv run --quiet python "$here/break_invariant.py" "$@"
