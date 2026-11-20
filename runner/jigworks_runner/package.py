"""Loading a workflow package (design.md §5) from a directory or an unpacked bundle.

The package is imported under a synthetic module name derived from its digest, so two
releases (or two packages that both have `graph.py` and `steps/`) never collide in
`sys.modules`. Package code uses relative imports (`from .steps import nodes`).
"""

from __future__ import annotations

import hashlib
import importlib
import sys
import tomllib
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import jigworks_contracts as contracts
from jigworks_contracts import bundle
from jigworks_contracts.graph import normalize_langgraph_json

# Development-only files that are not part of a release bundle.
DEV_ONLY = ("tests/", "evals/", "pyproject.toml", ".pytest_cache/", ".hypothesis/")


def bundle_files(root: Path) -> dict[str, bytes]:
    files = bundle.files_from_dir(root)
    return {p: b for p, b in files.items() if not any(p == d or p.startswith(d) for d in DEV_ONLY)}


def build_package_bundle(root: Path) -> tuple[bytes, str]:
    data = bundle.build_bundle(bundle_files(root))
    return data, bundle.digest(data)


@dataclass
class WorkflowPackage:
    root: Path
    manifest: dict[str, Any]
    digest: str
    module_name: str
    build_graph: Callable[[], Any]

    @property
    def name(self) -> str:
        return self.manifest["name"]

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @property
    def release(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def planned_path(self) -> list[str]:
        return list(self.manifest.get("plannedPath", []))

    @property
    def weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.manifest.get("weights", {}).items()}

    def model_for(self, node: str) -> str:
        models = self.manifest["models"]
        return models.get("nodes", {}).get(node) or models["default"]

    def effort_for(self, node: str) -> str | None:
        effort = self.manifest.get("effort") or {}
        return effort.get("nodes", {}).get(node) or effort.get("default")

    def allowed_tools(self) -> list[str] | None:
        perms = self.manifest.get("permissions") or {}
        return list(perms["allowedTools"]) if "allowedTools" in perms else None

    def graph_json(self) -> dict[str, Any]:
        raw = self.build_graph().compile().get_graph().to_json()
        out = normalize_langgraph_json(
            raw,
            weights=self.weights,
            interrupt_nodes=self.manifest.get("interruptNodes", []),
            workflow_id=self.name,
            release=self.release,
        )
        contracts.assert_valid("GraphJSON", out)
        return out


def read_manifest(root: Path) -> dict[str, Any]:
    with (root / "workflow.toml").open("rb") as fh:
        manifest = tomllib.load(fh)
    contracts.assert_valid("WorkflowManifest", manifest)
    return manifest


def load_package(root: str | Path, digest: str | None = None) -> WorkflowPackage:
    root = Path(root).resolve()
    manifest = read_manifest(root)
    if digest is None:
        _, digest = build_package_bundle(root)
    # Digest and location both name the module: the same release unpacked in two places must not
    # share a cached module (its files, e.g. prompts/, are read relative to the module).
    where = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    module_name = f"jigworks_pkg_{digest.split(':', 1)[-1][:16]}_{where}"
    if module_name not in sys.modules:
        pkg = types.ModuleType(module_name)
        pkg.__path__ = [str(root)]  # type: ignore[attr-defined]
        pkg.__package__ = module_name
        sys.modules[module_name] = pkg
    mod_name, _, attr = manifest["entrypoint"].partition(":")
    module = _import_entry(root, f"{module_name}.{mod_name}")
    return WorkflowPackage(root, manifest, digest, module_name, getattr(module, attr or "build_graph"))


def _import_entry(root: Path, qualified: str) -> types.ModuleType:
    """Import the entry module. Packages may use relative imports (`from .steps import nodes`,
    preferred) or absolute ones (`from steps import nodes`, like the T02 fixture bundles). For the
    latter the root is on sys.path only during the import, and the top-level modules it loaded are
    dropped from sys.modules afterwards, so another package's `steps` never resolves to this one."""
    before = set(sys.modules)
    sys.path.insert(0, str(root))
    try:
        return importlib.import_module(qualified)
    finally:
        sys.path.remove(str(root))
        for name in set(sys.modules) - before:
            mod = sys.modules.get(name)
            file = getattr(mod, "__file__", None) or ""
            if not name.startswith("jigworks_pkg_") and file.startswith(str(root)):
                del sys.modules[name]
