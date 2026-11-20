"""The gate: deterministic checks on the run's worktree, no agent involved.

The repo is the one the run starts in; the gate's root is the folder the run was started from
(`scope`, set by the runner; the whole repo when started at its root). Checks (each one fails
the gate on its own):
- scope           the diff only touches paths under the scope
- protected tests implement/fix left alone what write_tests wrote, the test configuration, the
                  test script, INVARIANTS.md and the gate config (tests are written by a
                  different agent before implementation)
- setup           installs dependencies when the repo needs it (e.g. node_modules missing)
- tests           the repo's test command(s)
- property tests  the invariant property tests, when the repo's gate config names them
- secret scan     gitleaks if installed, else the built-in rules in secrets.py, on added lines
- security scan   bandit (medium severity and up) on the changed Python files

The test commands come from `.jigworks/gate.toml` in the gate's root, read from the run's base
commit (so an agent cannot change its own gate), else they are detected: pytest, the
package.json test script (pnpm / yarn / bun / npm by lockfile), `go test`, `cargo test`.
The runner may override any setting through `runtime.options["gate"]`.

`.jigworks/gate.toml` (paths relative to the gate's root; a command is a list of arguments or
one string; `python` as the first argument means the runner's Python):

    tests = [["python", "-m", "pytest", "tests", "-q"]]
    property_tests = [["python", "-m", "pytest", "tests/test_invariants.py", "-q"]]
    setup = [["pnpm", "install", "--frozen-lockfile"]]
    pythonpath = ["."]
    protected_dirs = ["tests/"]            # existing files here are read-only for implement and fix
    protected_files = ["INVARIANTS.md"]
    timeout_s = 600
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from . import secrets

CONFIG = ".jigworks/gate.toml"
DEFAULTS: dict[str, Any] = {
    "scope": [""],  # "" = the whole repo
    "pythonpath": [],
    "timeout_s": 600,
    "protected_dirs": [],
    "protected_files": [],
    # Test configuration and the invariant spec, anywhere in the scope.
    "protected_names": ["conftest.py", "pytest.ini", "tox.ini", "INVARIANTS.md"],
}
# Files write_tests may create that implement still has to change (dependencies). Only their
# test script / test configuration is guarded, not the whole file.
DEPENDENCY_FILES = {
    "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb", "pyproject.toml", "uv.lock",
    "poetry.lock", "requirements.txt", "requirements-dev.txt", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
}
NPM_NO_TEST = "no test specified"


def gate_root(scope: list[str]) -> str:
    """The folder the gate runs in, relative to the repo root: '' or 'app/'."""
    root = scope[0] if len(scope) == 1 else ""
    root = root.strip("/")
    return "" if root in ("", ".") else root + "/"


def scope_label(scope: list[str]) -> str:
    roots = [p for p in scope if p.strip("/") not in ("", ".")]
    return ", ".join(roots) if roots else "the repository root (the whole repo)"


def _commands(value: Any) -> list[list[str]]:
    if not value:
        return []
    if isinstance(value, str):
        return [shlex.split(value)]
    if all(isinstance(v, str) for v in value):
        return [list(value)]
    return [shlex.split(v) if isinstance(v, str) else list(v) for v in value]


def read_config(cwd: Path, base: str, root: str) -> dict[str, Any]:
    try:
        text = _git(cwd, "show", f"{base}:{root}{CONFIG}")
    except subprocess.CalledProcessError:
        return {}
    raw = tomllib.loads(text)
    cfg: dict[str, Any] = dict(raw)
    for key in ("tests", "property_tests", "setup"):
        if key in raw:
            cfg[key] = _commands(raw[key])
    for key in ("protected_dirs", "protected_files"):
        if key in raw:
            cfg[key] = [root + p for p in raw[key]]
    if "pythonpath" in raw:
        cfg["pythonpath"] = [root + p if p not in ("", ".") else (root or ".") for p in raw["pythonpath"]]
    return cfg


def _package_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _node_manager(d: Path) -> str:
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun")):
        if (d / lock).exists():
            return pm
    return "npm"


def detect(d: Path) -> dict[str, list[list[str]]]:
    """Setup and test commands from the files in the gate's root."""
    setup: list[list[str]] = []
    tests: list[list[str]] = []
    pkg = _package_json(d / "package.json")
    script = (pkg.get("scripts") or {}).get("test", "")
    if script and NPM_NO_TEST not in script:
        pm = _node_manager(d)
        if (pkg.get("dependencies") or pkg.get("devDependencies")) and not (d / "node_modules").exists():
            setup.append([pm, "install"])
        tests.append([pm, "test"])
    has_py_tests = any(d.glob("test_*.py")) or any(d.glob("tests/**/test_*.py")) or any(d.glob("tests/**/*_test.py"))
    if has_py_tests or any((d / f).exists() for f in ("pytest.ini", "conftest.py")):
        if (d / "uv.lock").exists():
            tests.append(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"])
        else:
            tests.append(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    if (d / "go.mod").exists():
        tests.append(["go", "test", "./..."])
    if (d / "Cargo.toml").exists():
        tests.append(["cargo", "test"])
    return {"setup": setup, "tests": tests}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def changed_files(cwd: Path, base: str) -> list[str]:
    tracked = _git(cwd, "diff", "--name-only", base).splitlines()
    untracked = _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked) | set(untracked))


def diff_text(cwd: Path, base: str) -> str:
    # Include untracked files: mark them intent-to-add on a throwaway index copy would be
    # cleaner; the runner commits after every node, so the gate normally sees committed work.
    return _git(cwd, "diff", "--no-color", "--unified=0", base)


def _tail(text: str, n: int = 12) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def _command(name: str, kind: str, cmd: list[str], cwd: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    env = dict(os.environ)
    paths = [str((cwd / p).resolve()) for p in cfg.get("pythonpath", [])]
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    argv = [sys.executable, *cmd[1:]] if cmd and cmd[0] == "python" else list(cmd)
    run_in = cwd / gate_root(cfg["scope"])
    label = f"{name}: {shlex.join(cmd)}"
    try:
        proc = subprocess.run(argv, cwd=run_in, env=env, capture_output=True, text=True, timeout=cfg["timeout_s"])
    except subprocess.TimeoutExpired:
        return {"name": label, "kind": kind, "passed": False, "summary": f"timed out after {cfg['timeout_s']} s"}
    except OSError as exc:
        return {"name": label, "kind": kind, "passed": False, "findings": 1, "summary": f"could not run: {exc}"}
    out = proc.stdout + proc.stderr
    failed = [ln for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))]
    check = {"name": label, "kind": kind, "passed": proc.returncode == 0, "summary": _tail(out, 1) or f"exit {proc.returncode}"}
    if proc.returncode != 0:
        check["findings"] = max(len(failed), 1)
        check["summary"] = _tail(out, 3) + ("\n" + "\n".join(failed[:10]) if failed else "")
    return check


def _scope(files: list[str], allowed: list[str]) -> dict[str, Any]:
    prefixes = [gate_root([p]) for p in allowed]
    outside = [f for f in files if not any(f.startswith(p) for p in prefixes)]
    check = {"name": "scope", "kind": "other", "passed": not outside}
    check["summary"] = "ok" if not outside else "changes outside " + scope_label(allowed) + ": " + ", ".join(outside[:10])
    if outside:
        check["findings"] = len(outside)
    return check


def _show(cwd: Path, rev: str, path: str) -> str | None:
    try:
        return _git(cwd, "show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None


def _test_settings(name: str, text: str | None) -> Any:
    """The part of a dependency file that decides what the tests run."""
    if text is None:
        return None
    if name == "package.json":
        try:
            return (json.loads(text).get("scripts") or {}).get("test")
        except ValueError:
            return text
    if name == "pyproject.toml":
        try:
            return (tomllib.loads(text).get("tool") or {}).get("pytest")
        except tomllib.TOMLDecodeError:
            return text
    return None


INVARIANTS = "INVARIANTS.md"


def written_by_tests(cwd: Path, base: str, tests_base: str) -> set[str]:
    """Files write_tests changed: read-only for implement and fix."""
    return set(_git(cwd, "diff", "--name-only", "--no-renames", base, tests_base).splitlines()) if tests_base != base else set()


def content_id(cwd: Path, path: str) -> str:
    """What the human accepts for a protected file: the git blob hash of its current content."""
    return _git(cwd, "hash-object", "--", path).strip() if (cwd / path).is_file() else "deleted"


def protected_changes(cwd: Path, base: str, tests_base: str, cfg: dict[str, Any],
                      accepted: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(path, label) of every file implement/fix changed since write_tests that they may not
    touch, except changes the human accepted at approve_fix (pinned to the exact content: any
    later edit counts again)."""
    accepted = accepted or {}
    root = gate_root(cfg["scope"])
    by_tests = written_by_tests(cwd, base, tests_base)
    out = _git(cwd, "diff", "--name-status", "--no-renames", tests_base).splitlines()
    out += [f"A\t{f}" for f in _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()]
    touched = []
    for line in out:
        status, path = line.split("\t", 1)
        name = path.rsplit("/", 1)[-1]
        if name in DEPENDENCY_FILES:
            if name in ("package.json", "pyproject.toml"):
                before = _test_settings(name, _show(cwd, tests_base, path))
                now = _test_settings(name, (cwd / path).read_text() if (cwd / path).is_file() else None)
                if before is not None and before != now:
                    touched.append((path, f"{path} (test script)"))
            continue
        in_dirs = any(path.startswith(d) for d in cfg["protected_dirs"])
        if name == INVARIANTS and status == "A" and path not in by_tests:
            continue  # a new INVARIANTS.md is the implementer's (the plan can give it one); an existing one is not
        if (
            path in by_tests
            or (in_dirs and status != "A")
            or path in cfg["protected_files"]
            or name in cfg["protected_names"]
            or path == root + CONFIG
        ):
            touched.append((path, path))
    return [(p, label) for p, label in dict.fromkeys(touched) if accepted.get(p) != content_id(cwd, p)]


def _protected(cwd: Path, base: str, tests_base: str, cfg: dict[str, Any],
               accepted: dict[str, str] | None = None) -> dict[str, Any]:
    touched = [label for _, label in protected_changes(cwd, base, tests_base, cfg, accepted)]
    check = {"name": "protected tests", "kind": "other", "passed": not touched}
    if touched:
        check["findings"] = len(touched)
        check["summary"] = (
            "changed after write_tests: " + ", ".join(sorted(set(touched))[:10])
            + ". The tests from write_tests, the test configuration and test script, INVARIANTS.md and"
            f" {CONFIG} are read-only for implement and fix: restore them and fix the code. If the human"
            " ruled that a test is wrong (or it is), keep the change and write `NEEDS HUMAN: accept the"
            " change to <path>`: the human sees the diff and can accept exactly that content."
        )
    else:
        check["summary"] = "ok"
    return check


def _secret_scan(cwd: Path, base: str) -> dict[str, Any]:
    gitleaks = shutil.which("gitleaks")
    if gitleaks:
        # Scan the added lines of the net diff, like the built-in rules. `gitleaks git` over
        # base..HEAD would scan every commit of the run, so a secret that `fix` removed again
        # would keep failing the gate until the fix loop limit.
        added = "\n".join(
            ln for ln in diff_text(cwd, base).splitlines() if ln.startswith("+") and not ln.startswith("+++")
        )
        proc = subprocess.run(
            [gitleaks, "stdin", "--no-banner", "--no-color", "--redact", "--verbose", "--exit-code", "1"],
            cwd=cwd, input=added, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return {"name": "gitleaks", "kind": "secret_scan", "passed": True, "summary": "ok"}
        rules = [ln.split(":", 1)[1].strip() for ln in proc.stdout.splitlines() if ln.startswith("RuleID:")]
        return {"name": "gitleaks", "kind": "secret_scan", "passed": False, "findings": max(len(rules), 1),
                "summary": "; ".join(rules[:10]) or _tail(proc.stdout + proc.stderr, 5)}
    findings = secrets.scan_diff(diff_text(cwd, base))
    check = {"name": "secret-scan (built-in rules)", "kind": "secret_scan", "passed": not findings}
    if findings:
        check["findings"] = len(findings)
        check["summary"] = "; ".join(f"{f.rule} in {f.file}:{f.line}" for f in findings[:10])
    else:
        check["summary"] = "ok"
    return check


def _security_scan(cwd: Path, files: list[str], read_only: set[str] | None = None) -> dict[str, Any]:
    """bandit on the changed Python files. Findings in the tests from write_tests are reported but
    not counted: implement and fix may not edit those files, so the fixer could never clear them
    (the reviewer and the human see them in the summary)."""
    read_only = read_only or set()
    py = [f for f in files if f.endswith(".py") and (cwd / f).is_file()]
    if not py:
        return {"name": "bandit", "kind": "security_scan", "passed": True, "summary": "no changed Python files"}
    proc = subprocess.run(
        [sys.executable, "-m", "bandit", "-q", "-f", "json", "-ll", "-s", "B101", *py],
        cwd=cwd, capture_output=True, text=True,
    )
    try:
        results = json.loads(proc.stdout or "{}").get("results", [])
    except json.JSONDecodeError:
        return {"name": "bandit", "kind": "security_scan", "passed": False,
                "summary": "bandit did not run: " + _tail(proc.stderr, 3), "findings": 1}
    def where(r: dict) -> str:
        return f"{r['test_id']} {r['issue_severity'].lower()} in {r['filename']}:{r['line_number']}"

    def path_of(r: dict) -> str:
        name = r["filename"]
        return name[2:] if name.startswith("./") else name

    counted = [r for r in results if path_of(r) not in read_only]
    ignored = [r for r in results if path_of(r) in read_only]
    check = {"name": "bandit", "kind": "security_scan", "passed": not counted}
    parts = []
    if counted:
        check["findings"] = len(counted)
        parts.append("; ".join(where(r) for r in counted[:10]))
    if ignored:
        parts.append("not counted, in the read-only tests from write_tests: " + "; ".join(where(r) for r in ignored[:10]))
    check["summary"] = " · ".join(parts) or "ok"
    return check


def settings(cwd: Path, base: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """DEFAULTS < detected commands < the repo's .jigworks/gate.toml (base commit) < runner overrides."""
    scope = (overrides or {}).get("scope") or DEFAULTS["scope"]
    root = gate_root(scope)
    cfg = {**DEFAULTS, **detect(cwd / root), **read_config(cwd, base, root), **(overrides or {})}
    cfg["scope"] = scope
    return cfg


def run_gate(cwd: Path, base: str, overrides: dict[str, Any] | None = None,
             tests_base: str | None = None, accepted: dict[str, str] | None = None) -> dict[str, Any]:
    """`tests_base` is the commit of write_tests; without one, the run's base commit.
    `accepted`: protected files the human accepted at approve_fix, path → content_id()."""
    cfg = settings(cwd, base, overrides)
    files = changed_files(cwd, base)
    checks = [_scope(files, cfg["scope"]), _protected(cwd, base, tests_base or base, cfg, accepted)]
    for cmd in _commands(cfg.get("setup")):
        checks.append(_command("setup", "other", cmd, cwd, cfg))
    tests = _commands(cfg.get("tests"))
    if not tests:
        checks.append({
            "name": "tests", "kind": "tests", "passed": False, "findings": 1,
            "summary": f"no test command found in {scope_label(cfg['scope'])}: add a test script (pytest, package.json"
                       f" \"test\", go test, cargo test) or name the commands in {gate_root(cfg['scope'])}{CONFIG}",
        })
    for cmd in tests:
        checks.append(_command("tests", "tests", cmd, cwd, cfg))
    for cmd in _commands(cfg.get("property_tests")):
        checks.append(_command("property tests", "property_tests", cmd, cwd, cfg))
    checks += [_secret_scan(cwd, base), _security_scan(cwd, files, written_by_tests(cwd, base, tests_base or base))]
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def report(gate: dict[str, Any]) -> str:
    lines = []
    for c in gate["checks"]:
        lines.append(f"- {c['name']} ({c['kind']}): {'PASS' if c['passed'] else 'FAIL'}")
        if not c["passed"] and c.get("summary"):
            lines.extend("    " + ln for ln in c["summary"].splitlines())
    return "\n".join(lines)
