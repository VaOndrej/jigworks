"""Copy the contract fixtures the hub seeds from into hub_api/seed_data/.

The Vercel service root is apps/hub-api, so files under packages/contracts/fixtures are not
in the deployed function. The copy is byte-identical; tests/test_seed_data.py fails when it
drifts from the frozen fixtures.

    uv run python apps/hub-api/scripts/sync_seed.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
FIX = HUB.parent.parent / "packages" / "contracts" / "fixtures"
DEST = HUB / "hub_api" / "seed_data"

FILES = [
    "api/release-list.json",
    "api/workflow-list.json",
    "bundles/feature-development-1.2.0.zip",
    "bundles/feature-development-1.3.0.zip",
    "graph/feature-development-1.3.0.graph.json",
    "graph/feature-development.langgraph.json",
    "prices.json",
    "human-deltas.json",
    *sorted(str(p.relative_to(FIX)) for p in (FIX / "runs").glob("*.jsonl")),
]


def main() -> None:
    if DEST.exists():
        shutil.rmtree(DEST)
    for rel in FILES:
        target = DEST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIX / rel, target)
    print(f"copied {len(FILES)} fixtures to {DEST.relative_to(HUB.parent.parent)}")


if __name__ == "__main__":
    main()
