"""The import/compile check that runs inside the Vercel Sandbox (validation.CHECK_SCRIPT), run
here with the local Python. It must import a package the way the runner does (package.py):
relative imports (`from .steps import nodes`, the repo's feature-development) and absolute ones
(`from steps import nodes`, the T02 fixture bundles) both work."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jigworks_contracts.bundle import read_bundle
from hub_api.validation import CHECK_SCRIPT, MARK

REPO = Path(__file__).resolve().parents[3]
FIX = REPO / "packages" / "contracts" / "fixtures"


def _check(tmp_path: Path, pkg: Path, entry: str = "graph:build_graph") -> dict:
    (tmp_path / "check.py").write_text(CHECK_SCRIPT)
    run = subprocess.run([sys.executable, "check.py", str(pkg.relative_to(tmp_path)), entry],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120)
    line = next(ln for ln in run.stdout.splitlines() if ln.startswith(MARK))
    return json.loads(line[len(MARK):])


def test_relative_imports_like_the_repo_workflow(tmp_path):
    pkg = tmp_path / "pkg"
    shutil.copytree(REPO / "workflows" / "feature-development", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    out = _check(tmp_path, pkg)
    assert out.get("imports") == {"ok": True}, out
    assert out.get("compile") == {"ok": True}, out
    assert {n["id"] for n in out["graph"]["nodes"]} >= {"plan", "implement", "gate"}


@pytest.mark.parametrize("version", ["1.3.0"])
def test_absolute_imports_like_the_fixture_bundles(tmp_path, version):
    digest = next(r["digest"] for r in json.loads((FIX / "api" / "release-list.json").read_text())["releases"]
                  if r["version"] == version)
    pkg = tmp_path / "pkg"
    for path, data in read_bundle((FIX / "bundles" / f"feature-development-{version}.zip").read_bytes(), digest).items():
        (pkg / path).parent.mkdir(parents=True, exist_ok=True)
        (pkg / path).write_bytes(data)
    out = _check(tmp_path, pkg)
    assert out.get("imports") == {"ok": True} and out.get("compile") == {"ok": True}, out
