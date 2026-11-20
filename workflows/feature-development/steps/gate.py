"""The gate: deterministic checks on the run's worktree, no agent involved.

Checks (each one fails the gate on its own):
- scope           the diff only touches the allowed paths (default `sample-repo/`)
- protected tests implement/fix left the tests from write_tests and the pytest configuration
                  alone (design.md: tests are written by a different agent before implementation)
- tests           the plain test suite
- property tests  the invariant property tests (sample-repo/INVARIANTS.md)
- secret scan     gitleaks if installed, else the built-in rules in secrets.py, on added lines
- security scan   bandit (medium severity and up) on the changed Python files

The defaults target `sample-repo/`; the runner may override any of them through
`runtime.options["gate"]` (used by the tests to point at a tiny repo).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import secrets

DEFAULTS: dict[str, Any] = {
    "scope": ["sample-repo/"],
    "pythonpath": ["sample-repo"],
    "tests": [sys.executable, "-m", "pytest", "sample-repo/tests", "-q", "-p", "no:cacheprovider",
              "--ignore=sample-repo/tests/test_invariants.py"],
    "property_tests": [sys.executable, "-m", "pytest", "sample-repo/tests/test_invariants.py", "-q",
                       "-p", "no:cacheprovider"],
    "timeout_s": 600,
    # Read-only for implement and fix: what write_tests left under these paths, pytest
    # configuration anywhere, and the invariant spec. New test files may be added.
    "protected_dirs": ["sample-repo/tests/"],
    "protected_files": ["sample-repo/INVARIANTS.md", "sample-repo/pyproject.toml", "sample-repo/pytest.ini",
                        "sample-repo/setup.cfg", "sample-repo/tox.ini"],
    "protected_names": ["conftest.py"],
}


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


def _pytest(name: str, kind: str, cmd: list[str], cwd: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    env = dict(os.environ)
    paths = [str((cwd / p).resolve()) for p in cfg.get("pythonpath", [])]
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=cfg["timeout_s"])
    except subprocess.TimeoutExpired:
        return {"name": name, "kind": kind, "passed": False, "summary": f"timed out after {cfg['timeout_s']} s"}
    out = proc.stdout + proc.stderr
    failed = [ln for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))]
    check = {"name": name, "kind": kind, "passed": proc.returncode == 0, "summary": _tail(out, 1) or f"exit {proc.returncode}"}
    if proc.returncode != 0:
        check["findings"] = max(len(failed), 1)
        check["summary"] = _tail(out, 1) + ("\n" + "\n".join(failed[:10]) if failed else "")
    return check


def _scope(files: list[str], allowed: list[str]) -> dict[str, Any]:
    outside = [f for f in files if not any(f.startswith(p) for p in allowed)]
    check = {"name": "scope", "kind": "other", "passed": not outside}
    check["summary"] = "ok" if not outside else "changes outside " + ", ".join(allowed) + ": " + ", ".join(outside[:10])
    if outside:
        check["findings"] = len(outside)
    return check


def _protected(cwd: Path, tests_base: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Files implement/fix changed since write_tests that they may not touch."""
    out = _git(cwd, "diff", "--name-status", "--no-renames", tests_base).splitlines()
    out += [f"A\t{f}" for f in _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()]
    touched = []
    for line in out:
        status, path = line.split("\t", 1)
        name = path.rsplit("/", 1)[-1]
        in_tests = any(path.startswith(d) for d in cfg["protected_dirs"])
        if (in_tests and status != "A") or path in cfg["protected_files"] or name in cfg["protected_names"]:
            touched.append(path)
    check = {"name": "protected tests", "kind": "other", "passed": not touched}
    if touched:
        check["findings"] = len(touched)
        check["summary"] = (
            "changed after write_tests: " + ", ".join(sorted(set(touched))[:10])
            + ". The tests from write_tests, the pytest configuration and INVARIANTS.md are read-only for"
            " implement and fix: restore them and fix the code. If a test itself is wrong, say so;"
            " a human decides (reject the run and start again)."
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


def _security_scan(cwd: Path, files: list[str]) -> dict[str, Any]:
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
    check = {"name": "bandit", "kind": "security_scan", "passed": not results}
    if results:
        check["findings"] = len(results)
        check["summary"] = "; ".join(
            f"{r['test_id']} {r['issue_severity'].lower()} in {r['filename']}:{r['line_number']}" for r in results[:10]
        )
    else:
        check["summary"] = "ok"
    return check


def run_gate(cwd: Path, base: str, overrides: dict[str, Any] | None = None,
             tests_base: str | None = None) -> dict[str, Any]:
    """`tests_base` is the commit of write_tests; without one, the run's base commit."""
    cfg = {**DEFAULTS, **(overrides or {})}
    files = changed_files(cwd, base)
    checks = [
        _scope(files, cfg["scope"]),
        _protected(cwd, tests_base or base, cfg),
        _pytest("pytest", "tests", cfg["tests"], cwd, cfg),
        _pytest("hypothesis invariants", "property_tests", cfg["property_tests"], cwd, cfg),
        _secret_scan(cwd, base),
        _security_scan(cwd, files),
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def report(gate: dict[str, Any]) -> str:
    lines = []
    for c in gate["checks"]:
        lines.append(f"- {c['name']} ({c['kind']}): {'PASS' if c['passed'] else 'FAIL'}")
        if not c["passed"] and c.get("summary"):
            lines.extend("    " + ln for ln in c["summary"].splitlines())
    return "\n".join(lines)
