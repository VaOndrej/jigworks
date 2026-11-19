#!/usr/bin/env bash
# List the release bundles in the Vercel Blob store (proof that publish writes to Blob).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=e2e/hub/env.sh
source e2e/hub/env.sh
uv run python - <<'EOF'
from vercel.blob.sync import query_blobs
for b in query_blobs(prefix="bundles/"):
    print(f"{b.uploaded_at:%Y-%m-%d %H:%M}  {b.size:>6} B  {b.pathname}")
EOF
