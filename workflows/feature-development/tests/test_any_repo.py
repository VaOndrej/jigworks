"""feature-development on repos other than sample-repo: the repo is the one the run starts in.

The gate finds the test command itself (pytest, the package.json test script, go, cargo) or
reads `.jigworks/gate.toml` from the run's base commit; nothing here is about sample-repo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from jigworks_runner.adapters.fake import FakeAdapter, FakeStep
from jigworks_runner.engine import WorkflowRun
from jigworks_runner.package import load_package

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = ROOT / "workflows" / "feature-development"
AUTHOR = "dev@example.com"
APPROVER = "lead@example.com"

PY_TEST = "from greet import greet\n\n\ndef test_greet():\n    assert greet('Ada') == 'Hello, Ada!'\n"
PY_IMPL = "def greet(name):\n    return f'Hello, {name}!'\n"
JS_TEST = "const assert = require('node:assert');\nconst { greet } = require('./greet');\nassert.strictEqual(greet('Ada'), 'Hello, Ada!');\n"
JS_IMPL = "exports.greet = (name) => `Hello, ${name}!`;\n"


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    work = tmp_path / "work"
    for rel, content in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(content)
    (work / ".gitignore").write_text("__pycache__/\n.pytest_cache/\nnode_modules/\n")
    sh(work, "git", "init", "-q", "-b", "main")
    sh(work, "git", "config", "user.email", AUTHOR)
    sh(work, "git", "config", "user.name", "Dev")
    sh(work, "git", "add", "-A")
    sh(work, "git", "commit", "-q", "-m", "base")
    return work


def script(tests: dict[str, str], impl: dict[str, str], **overrides) -> dict:
    base = {
        "plan": [FakeStep("1. Add greet(name).\n2. Test it.")],
        "write_tests": [FakeStep("added the greet test", files=tests)],
        "implement": [FakeStep("implemented greet", files=impl)],
        "review": [FakeStep("VERDICT: PASS")],
        "fix": [FakeStep("fixed")],
        "summary": [FakeStep("Added greet.")],
    }
    base.update(overrides)
    return base


def run_to_pr(repo: Path, steps: dict, **options):
    agent = FakeAdapter(steps)
    run = WorkflowRun(load_package(PACKAGE_DIR), run_id="run_any", cwd=repo, agent=agent, author_email=AUTHOR,
                      options={"max_fix_loops": 1, **options}, branch="jigworks/run_any", repo="demo")
    out = run.start("Add greet(name)")
    out = run.decide("approve", APPROVER)  # the plan
    return run, agent, out


def first_gate(run: WorkflowRun) -> dict:
    return next(e["gateResult"] for e in run.sink.events if e["kind"] == "gate_result")


def check(gate: dict, name_part: str) -> dict:
    return next(c for c in gate["checks"] if name_part in c["name"])


def suite_check(gate: dict) -> dict:
    return next(c for c in gate["checks"] if c["kind"] == "tests")


@pytest.fixture
def py_repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path, {"pyproject.toml": "[project]\nname = 'greet'\nversion = '0.1.0'\n",
                                "README.md": "greet\n"})


@pytest.fixture
def js_repo(tmp_path: Path) -> Path:
    pkg = {"name": "greet", "version": "0.1.0", "scripts": {"test": "node greet.test.js"}}
    return make_repo(tmp_path, {"package.json": json.dumps(pkg, indent=2) + "\n"})


def test_python_repo_is_gated_at_its_root_without_any_config(py_repo):
    run, agent, out = run_to_pr(py_repo, script({"tests/test_greet.py": PY_TEST}, {"greet.py": PY_IMPL}))
    assert out.status == "waiting_human" and out.interrupt["stage"] == "pr", first_gate(run)
    gate = first_gate(run)
    assert gate["passed"] and check(gate, "pytest")["passed"]
    assert check(gate, "scope")["summary"] == "ok"
    assert "sample-repo" not in next(c for c in agent.calls if c.node == "plan").prompt


def test_node_repo_runs_its_own_test_script(js_repo):
    run, _, out = run_to_pr(js_repo, script({"greet.test.js": JS_TEST}, {"greet.js": JS_IMPL}))
    gate = first_gate(run)
    assert gate["passed"], gate
    assert "npm test" in check(gate, "npm")["name"]


def test_a_failing_test_fails_the_gate_in_any_repo(js_repo):
    run, _, _ = run_to_pr(js_repo, script({"greet.test.js": JS_TEST}, {"greet.js": "exports.greet = () => 'Hi';\n"}))
    assert not check(first_gate(run), "npm")["passed"]


def test_repo_without_a_test_command_fails_the_gate_with_a_hint(tmp_path):
    repo = make_repo(tmp_path, {"README.md": "nothing to run\n"})
    run, _, _ = run_to_pr(repo, script({"notes.txt": "x\n"}, {"impl.txt": "y\n"}))
    tests = suite_check(first_gate(run))
    assert not tests["passed"] and ".jigworks/gate.toml" in tests["summary"]


def test_gate_config_in_the_repo_wins(tmp_path):
    repo = make_repo(tmp_path, {
        ".jigworks/gate.toml": 'tests = [["node", "check.js"]]\nproperty_tests = [["node", "props.js"]]\n',
        "check.js": "process.exit(require('node:fs').existsSync('greet.js') ? 0 : 1);\n",
        "props.js": "process.exit(0);\n",
    })
    run, _, out = run_to_pr(repo, script({"greet.test.js": JS_TEST}, {"greet.js": JS_IMPL}))
    gate = first_gate(run)
    assert gate["passed"], gate
    assert {c["kind"] for c in gate["checks"]} >= {"tests", "property_tests"}


def test_agents_cannot_change_the_gate_config(tmp_path):
    repo = make_repo(tmp_path, {".jigworks/gate.toml": 'tests = [["node", "-e", "process.exit(1)"]]\n'})
    impl = {"greet.js": JS_IMPL, ".jigworks/gate.toml": 'tests = [["true"]]\n'}
    run, _, _ = run_to_pr(repo, script({"greet.test.js": JS_TEST}, impl))
    gate = first_gate(run)
    assert not check(gate, "protected")["passed"] and ".jigworks/gate.toml" in check(gate, "protected")["summary"]
    assert not suite_check(gate)["passed"]  # the config from the base commit still applies


def test_tests_from_write_tests_are_read_only_in_any_repo(py_repo):
    impl = {"greet.py": PY_IMPL, "tests/test_greet.py": "def test_greet():\n    pass\n"}
    run, _, _ = run_to_pr(py_repo, script({"tests/test_greet.py": PY_TEST}, impl))
    protected = check(first_gate(run), "protected")
    assert not protected["passed"] and "tests/test_greet.py" in protected["summary"]


def test_implement_may_add_dependencies_but_not_change_the_test_script(js_repo):
    pkg = {"name": "greet", "version": "0.1.0", "scripts": {"test": "true"}}
    run, _, _ = run_to_pr(js_repo, script({"greet.test.js": JS_TEST},
                                          {"greet.js": JS_IMPL, "package.json": json.dumps(pkg)}))
    protected = check(first_gate(run), "protected")
    assert not protected["passed"] and "test script" in protected["summary"]


def test_a_run_started_in_a_subfolder_is_scoped_to_it(tmp_path):
    repo = make_repo(tmp_path, {"app/pyproject.toml": "[project]\nname = 'greet'\nversion = '0.1.0'\n"})
    run, _, _ = run_to_pr(repo, script({"app/tests/test_greet.py": PY_TEST},
                                       {"app/greet.py": PY_IMPL, "elsewhere.txt": "no\n"}),
                          gate={"scope": ["app/"]})
    gate = first_gate(run)
    assert check(gate, "pytest")["passed"]  # run inside app/
    assert not check(gate, "scope")["passed"] and "elsewhere.txt" in check(gate, "scope")["summary"]


def test_node_is_available():
    assert shutil.which("node"), "these tests need node on PATH"
