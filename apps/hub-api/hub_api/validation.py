"""Validate a draft: manifest, syntax, imports, compile, get_graph().

The API process only *parses* (tomllib, ast.parse); it never imports or runs workflow code
(design.md §5). Imports, compile() and get_graph() run in Vercel Sandbox. Without Sandbox
credentials (local development, tests) the last three checks are mocked with the contract's
recorded get_graph() output, and the result says so.
"""

from __future__ import annotations

import ast
import json
import time
import tomllib
from importlib import resources
from typing import Any

import jigworks_contracts as c
from jigworks_contracts.graph import normalize_langgraph_json

from .config import settings

MARK = "JIGWORKS_RESULT "
SANDBOX_ROOT = "/vercel/sandbox"

# Runs inside the sandbox only. Imports the package, builds the graph, prints get_graph().
CHECK_SCRIPT = r'''
import importlib, json, os, sys, traceback
pkg, entry = os.path.abspath(sys.argv[1]), sys.argv[2]
sys.path.insert(0, pkg)
MARK = "JIGWORKS_RESULT "

def where(exc):
    for fr in reversed(traceback.extract_tb(exc.__traceback__)):
        if fr.filename.startswith(pkg + os.sep):
            return {"file": os.path.relpath(fr.filename, pkg), "line": fr.lineno}
    return {}

def fail(name, exc):
    out[name] = {"ok": False, "message": f"{type(exc).__name__}: {exc}", **where(exc)}
    print(MARK + json.dumps(out))
    sys.exit(0)

out = {}
module_name, _, attr = entry.partition(":")
try:
    target = getattr(importlib.import_module(module_name), attr)
    out["imports"] = {"ok": True}
except Exception as exc:
    fail("imports", exc)
try:
    g = target
    if callable(g) and not hasattr(g, "compile") and not hasattr(g, "get_graph"):
        g = g()
    if not hasattr(g, "get_graph"):
        g = g.compile()
    raw = json.loads(json.dumps(g.get_graph().to_json(), default=str))
    out["compile"] = {"ok": True}
    out["graph"] = raw
except Exception as exc:
    fail("compile", exc)
print(MARK + json.dumps(out))
'''


def _check(name: str, ok: bool, message: str | None = None, file: str | None = None, line: int | None = None) -> dict:
    out: dict[str, Any] = {"name": name, "ok": ok}
    for key, value in (("message", message), ("file", file), ("line", line)):
        if value is not None:
            out[key] = value
    return out


def static_checks(workflow_id: str, files: dict[str, str]) -> tuple[list[dict], dict | None]:
    """Manifest + syntax, parsed in the API process (no code is executed)."""
    checks: list[dict] = []
    text = files.get("workflow.toml")
    if text is None:
        return [_check("manifest", False, "workflow.toml is missing", "workflow.toml")], None
    try:
        manifest = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [_check("manifest", False, f"TOML: {exc}", "workflow.toml")], None
    errors = c.validate("WorkflowManifest", manifest)
    module = manifest.get("entrypoint", "").partition(":")[0]
    if not errors and manifest["name"] != workflow_id:
        errors = [f"name {manifest['name']!r} must equal the workflow id {workflow_id!r}"]
    if not errors and f"{module.replace('.', '/')}.py" not in files:
        errors = [f"entrypoint module {module!r} has no file {module.replace('.', '/')}.py"]
    if errors:
        return [_check("manifest", False, "; ".join(errors), "workflow.toml")], None
    checks.append(_check("manifest", True))

    for path in sorted(p for p in files if p.endswith(".py")):
        try:
            ast.parse(files[path], filename=path)
        except SyntaxError as exc:
            checks.append(_check("syntax", False, f"SyntaxError: {exc.msg}", path, exc.lineno or None))
            return checks, manifest
    checks.append(_check("syntax", True))
    return checks, manifest


def _graph_check(graph: dict, manifest: dict) -> dict:
    ids = {n["id"] for n in graph["nodes"]}
    missing = [n for n in [*(manifest.get("plannedPath") or []), *(manifest.get("interruptNodes") or [])] if n not in ids]
    if missing:
        return _check("graph", False, f"nodes named in workflow.toml are not in the graph: {', '.join(missing)}")
    steps = sum(1 for n in graph["nodes"] if n["kind"] in ("step", "interrupt"))
    return _check("graph", True, f"{steps} nodes")


def _finish(checks: list[dict], raw_graph: dict | None, manifest: dict, workflow_id: str, started: float) -> dict:
    result: dict[str, Any] = {"ok": False, "checks": checks}
    if raw_graph is not None:
        graph = normalize_langgraph_json(
            raw_graph, weights=manifest.get("weights"), interrupt_nodes=manifest.get("interruptNodes") or [],
            workflow_id=workflow_id, release=f"{workflow_id}@{manifest['version']}",
        )
        checks.append(_graph_check(graph, manifest))
        result["graph"] = graph
    result["ok"] = all(ch["ok"] for ch in checks) and raw_graph is not None
    result["durationMs"] = int((time.monotonic() - started) * 1000)
    return result


def validate_draft(workflow_id: str, files: dict[str, str], request_headers: dict[str, str] | None = None) -> dict:
    started = time.monotonic()
    checks, manifest = static_checks(workflow_id, files)
    if manifest is None or not all(ch["ok"] for ch in checks):
        return {"ok": False, "checks": checks, "durationMs": int((time.monotonic() - started) * 1000)}
    if settings().sandbox == "vercel":
        sandbox_checks, raw = run_in_sandbox(files, manifest["entrypoint"], request_headers or {})
    else:
        sandbox_checks, raw = fixture_checks()
    checks += sandbox_checks
    return _finish(checks, raw, manifest, workflow_id, started)


def fixture_checks() -> tuple[list[dict], dict]:
    raw = json.loads((resources.files(__package__) / "seed_data" / "graph" / "feature-development.langgraph.json").read_text())
    note = "mocked locally: no Vercel Sandbox credentials, recorded get_graph() fixture"
    return [_check("imports", True, note), _check("compile", True, note)], raw


def run_in_sandbox(files: dict[str, str], entrypoint: str, request_headers: dict[str, str]) -> tuple[list[dict], dict | None]:
    """Write the package into a fresh Vercel Sandbox, install its lock, import, compile, get_graph()."""
    from vercel.headers import set_headers  # noqa: PLC0415
    from vercel.sandbox.sync import create_sandbox  # noqa: PLC0415

    # The deployed function receives the project's OIDC token in x-vercel-oidc-token; the SDK
    # reads it from this context, so the sandbox belongs to (and is billed to) the project.
    set_headers({k.lower(): v for k, v in request_headers.items()})
    checks: list[dict] = []
    with create_sandbox(runtime="python3.13", execution_time_limit=240, tags={"app": "jigworks-hub", "purpose": "validate"}) as sb:
        dirs = sorted({f"pkg/{p.rsplit('/', 1)[0]}" for p in files if "/" in p} | {"pkg"})
        sb.run_command("mkdir", ["-p", *dirs], cwd=SANDBOX_ROOT, check=True)
        for path, content in files.items():
            sb.fs.write_bytes(f"pkg/{path}", content.encode(), cwd=SANDBOX_ROOT)
        sb.fs.write_bytes("jigworks_check.py", CHECK_SCRIPT.encode(), cwd=SANDBOX_ROOT)
        reqs = ["-r", "pkg/requirements.lock"] if "requirements.lock" in files else ["langgraph"]
        pip = sb.run_command("python3", ["-m", "pip", "install", "-q", "--disable-pip-version-check", *reqs],
                             cwd=SANDBOX_ROOT, capture_output=True)
        if pip.returncode != 0:
            tail = (pip.stderr or b"").decode(errors="replace").strip().splitlines()[-3:]
            checks.append(_check("imports", False, "pip install failed: " + " | ".join(tail), "requirements.lock"))
            return checks, None
        run = sb.run_command("python3", ["jigworks_check.py", "pkg", entrypoint], cwd=SANDBOX_ROOT, capture_output=True)
    stdout = (run.stdout or b"").decode(errors="replace")
    line = next((ln for ln in stdout.splitlines() if ln.startswith(MARK)), None)
    if line is None:
        err = (run.stderr or b"").decode(errors="replace").strip().splitlines()[-3:]
        return [_check("imports", False, "sandbox check produced no result: " + " | ".join(err))], None
    out = json.loads(line[len(MARK):])
    for name in ("imports", "compile"):
        if name in out:
            r = out[name]
            checks.append(_check(name, r["ok"], r.get("message"), r.get("file"), r.get("line")))
    return checks, out.get("graph")
