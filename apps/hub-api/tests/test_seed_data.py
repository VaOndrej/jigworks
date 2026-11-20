"""hub_api/seed_data is a byte-identical copy of the frozen contract fixtures it seeds from."""

from __future__ import annotations

import importlib.util
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
SCRIPT = HUB / "scripts" / "sync_seed.py"


def test_seed_data_matches_the_contract_fixtures():
    spec = importlib.util.spec_from_file_location("sync_seed", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    copied = {str(p.relative_to(mod.DEST)) for p in mod.DEST.rglob("*") if p.is_file()}
    assert copied == set(mod.FILES), "run: uv run python apps/hub-api/scripts/sync_seed.py"
    for rel in mod.FILES:
        assert (mod.DEST / rel).read_bytes() == (mod.FIX / rel).read_bytes(), rel
