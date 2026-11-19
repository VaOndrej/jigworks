"""Regenerate packages/contracts/openapi.json from the real hub app (the one file of the
contracts package HUB may write). `uv run pytest packages/contracts` checks it stays
compatible with the frozen stub.

    uv run python apps/hub-api/scripts/export_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path

from hub_api.main import app

OUT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {OUT}")
