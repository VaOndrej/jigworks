"""Deterministic release bundles and their digest (design.md §6).

The digest is sha256 over the exact .zip bytes. To make publishing reproducible, the
zip is built with sorted paths, a fixed timestamp and fixed permissions, so the same
files always give the same digest. Both the hub (publish) and the runner/extension
(verify, T10) use these rules.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Mapping
from pathlib import Path

FIXED_DATE = (1980, 1, 1, 0, 0, 0)
_SKIP_PARTS = {"__pycache__", ".venv", ".git", "node_modules", ".DS_Store"}


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_bundle(files: Mapping[str, bytes | str]) -> bytes:
    """Build the .zip for {relative path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in sorted(files):
            if path.startswith("/") or ".." in Path(path).parts:
                raise ValueError(f"unsafe path in bundle: {path}")
            content = files[path]
            info = zipfile.ZipInfo(path, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3  # unix, so external_attr is honoured everywhere
            zf.writestr(info, content.encode() if isinstance(content, str) else content, compresslevel=9)
    return buf.getvalue()


def files_from_dir(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not (_SKIP_PARTS & set(rel.parts)):
            out[rel.as_posix()] = p.read_bytes()
    return out


def read_bundle(data: bytes, expected_digest: str) -> dict[str, bytes]:
    """Verify the digest, then return the files. Raises ValueError on mismatch or unsafe paths."""
    actual = digest(data)
    if actual != expected_digest:
        raise ValueError(f"digest_mismatch: expected {expected_digest}, got {actual}")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        out = {}
        for name in zf.namelist():
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"unsafe path in bundle: {name}")
            out[name] = zf.read(name)
        return out
