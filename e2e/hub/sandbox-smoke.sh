#!/usr/bin/env bash
# Validate the contract's feature-development package in a real Vercel Sandbox from this machine
# (uses VERCEL_OIDC_TOKEN from `vercel env pull`, valid for 12 h). Prints the checks and the graph.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=e2e/hub/env.sh
source e2e/hub/env.sh
JIGWORKS_SANDBOX=vercel uv run python - <<'EOF'
import json
from pathlib import Path
from hub_api.validation import validate_draft

src = Path("packages/contracts/fixtures/bundles/src/feature-development")
files = {str(p.relative_to(src)): p.read_text() for p in sorted(src.rglob("*")) if p.is_file()}
result = validate_draft("feature-development", files)
print(json.dumps({k: v for k, v in result.items() if k != "graph"}, indent=2))
if "graph" in result:
    print("graph nodes:", " ".join(n["id"] for n in result["graph"]["nodes"]))
    expected = json.loads(Path("packages/contracts/fixtures/graph/feature-development-1.3.0.graph.json").read_text())
    print("graph equals the contract fixture:", result["graph"] == expected)
EOF
