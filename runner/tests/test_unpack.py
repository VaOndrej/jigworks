"""`jigworks unpack`: release bundles are verified against their digest before anything is written
(T10 import, T15 sync). Uses the T02 bundle fixtures, including the tampered one."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import jigworks_contracts as contracts
import pytest
from jigworks_contracts import bundle as cbundle

BUNDLES = Path(contracts.__file__).resolve().parent.parent / "fixtures" / "bundles"
OUR_PACKAGE = Path(__file__).resolve().parents[2] / "workflows" / "feature-development"


def unpack(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "jigworks_runner.cli", "unpack", *args], capture_output=True, text=True)


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0"])
def test_unpack_valid_bundle_with_sidecar_digest(tmp_path, version):
    zip_path = BUNDLES / f"feature-development-{version}.zip"
    digest = (BUNDLES / f"feature-development-{version}.zip.sha256").read_text().strip()
    dest = tmp_path / f"feature-development@{version}"
    proc = unpack(str(zip_path), "--dest", str(dest))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["digest"] == digest and out["release"] == f"feature-development@{version}"
    assert (dest / "package" / "workflow.toml").exists()
    meta = json.loads((dest / "jigworks-source.json").read_text())
    assert meta == {"source": "imported", "digest": digest, "release": f"feature-development@{version}",
                    "importedFrom": zip_path.name}
    # the unpacked fixture package (absolute imports) loads and draws its graph
    graph = subprocess.run([sys.executable, "-m", "jigworks_runner.cli", "graph", str(dest / "package")],
                           capture_output=True, text=True, check=True)
    assert contracts.validate("GraphJSON", json.loads(graph.stdout)) == []


def test_unpack_tampered_bundle_is_refused_and_nothing_is_written(tmp_path):
    digest = (BUNDLES / "feature-development-1.3.0.zip.sha256").read_text().strip()
    dest = tmp_path / "tampered"
    proc = unpack(str(BUNDLES / "feature-development-1.3.0.tampered.zip"), "--digest", digest, "--dest", str(dest))
    assert proc.returncode == 3
    assert "digest_mismatch" in proc.stderr
    assert not dest.exists() and not (tmp_path / "tampered.partial").exists()


def test_unpack_wrong_digest_is_refused(tmp_path):
    proc = unpack(str(BUNDLES / "feature-development-1.3.0.zip"), "--digest", "sha256:" + "0" * 64, "--dest", str(tmp_path / "x"))
    assert proc.returncode == 3 and "digest_mismatch" in proc.stderr


def test_unpack_unsafe_path_is_refused(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("workflow.toml", "name = 'x'\n")
        zf.writestr("../escape.py", "print('pwned')\n")
    data = buf.getvalue()
    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(data)
    proc = unpack(str(zip_path), "--digest", cbundle.digest(data), "--dest", str(tmp_path / "evil"))
    assert proc.returncode == 3 and "unsafe path" in proc.stderr
    assert not (tmp_path / "escape.py").exists()


def test_unpack_our_package_bundle_roundtrip(tmp_path):
    from jigworks_runner.package import build_package_bundle

    data, digest = build_package_bundle(OUR_PACKAGE)
    zip_path = tmp_path / "feature-development-1.5.0.zip"
    zip_path.write_bytes(data)
    proc = unpack(str(zip_path), "--digest", digest, "--dest", str(tmp_path / "fd"), "--source", "hub", "--channel", "stable")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["release"] == "feature-development@1.5.0" and out["channel"] == "stable"
    assert not (tmp_path / "fd" / "package" / "tests").exists(), "tests are not part of a release bundle"
