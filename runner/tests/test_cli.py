"""The `jigworks` CLI end to end with the fake adapter: real processes, real git worktrees,
real SQLite checkpoints, the real gate. Includes the kill-and-resume tests (design.md §11.1)."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import jigworks_contracts as contracts
import pytest

from jigworks_runner.ledger import Ledger
from jigworks_runner.progress import weights_from_history

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows" / "feature-development"
SAMPLE = ROOT / "sample-repo"
FIXTURES = Path(contracts.__file__).resolve().parent.parent / "fixtures"
AUTHOR = "dev@example.com"

FEATURE = 'def describe(order):\n    return f"{order.side.value} {order.quantity} {order.instrument}"\n'


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def env(tmp_path: Path):
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo / "sample-repo", ignore=shutil.ignore_patterns("__pycache__", ".hypothesis", "scripts"))
    (repo / ".gitignore").write_text("__pycache__/\n.hypothesis/\n.pytest_cache/\n")
    sh(repo, "git", "init", "-q", "-b", "main")
    sh(repo, "git", "config", "user.email", AUTHOR)
    sh(repo, "git", "config", "user.name", "Dev")
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-q", "-m", "base")
    remote = tmp_path / "remote.git"
    sh(tmp_path, "git", "clone", "-q", "--bare", str(repo), str(remote))
    home = tmp_path / "home"
    return {"repo": repo, "remote": remote, "home": home, "tmp": tmp_path}


def script(tmp: Path, name: str = "script.json", **overrides) -> Path:
    steps = {
        "plan": [{"text": "1. Add describe(order)."}],
        "write_tests": [{"text": "tests", "files": {"sample-repo/tests/test_notes.py":
            "from sample_repo.notes import describe\n\n\ndef test_import():\n    assert describe\n"}}],
        "implement": [{"text": "done", "files": {"sample-repo/sample_repo/notes.py": FEATURE}}],
        "review": [{"text": "VERDICT: PASS"}],
        "fix": [{"text": "fixed", "files": {"sample-repo/sample_repo/notes.py": FEATURE + "# fixed\n"}}],
        "summary": [{"text": "summary"}],
    }
    steps.update(overrides)
    path = tmp / name
    path.write_text(json.dumps(steps))
    return path


def jw(env, *args: str, check: bool = True, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "jigworks_runner.cli", *args]
    if args and args[0] not in ("run", "graph"):
        cmd += ["--home", str(env["home"])]
    proc = subprocess.run(cmd, cwd=env["repo"], capture_output=True, text=True,
                          env={**os.environ, **(extra_env or {})})
    if check and proc.returncode != 0:
        raise AssertionError(f"jigworks {' '.join(args)} exited {proc.returncode}\n{proc.stderr}")
    return proc


def start(env, run_id: str, script_path: Path, *extra: str, popen: bool = False):
    args = ["run", "--workflow", str(WORKFLOW), "--repo", str(env["repo"] / "sample-repo"),
            "--prompt", "Add describe(order)", "--adapter", "fake", "--fake-script", str(script_path),
            "--run-id", run_id, "--home", str(env["home"]), "--pr-remote", str(env["remote"]), *extra]
    if popen:
        return subprocess.Popen([sys.executable, "-m", "jigworks_runner.cli", *args], cwd=env["repo"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return jw(env, *args)


def stdout_events(proc) -> list[dict]:
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def log(env, run_id: str) -> list[dict]:
    path = env["home"] / "runs" / run_id / "events.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def check_log(events: list[dict]) -> None:
    assert [e["seq"] for e in events] == list(range(len(events)))
    for e in events:
        assert contracts.validate("RunEvent", e) == [], e
    progress = [e["progress"] for e in events if "progress" in e]
    assert progress == sorted(progress)


def node_events(events, node):
    return [(e["status"], e["attempt"]) for e in events if e["kind"] == "node_status" and e["node"] == node]


def wait_for(predicate, timeout: float = 60.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("timed out")


# --- lifecycle ---------------------------------------------------------------------------------


def test_cli_run_approve_in_a_fresh_worktree(env):
    p = start(env, "run_cli_a", script(env["tmp"]))
    out = stdout_events(p)
    assert out[0]["kind"] == "run_started" and out[-1]["kind"] == "interrupt"
    assert "waiting for a human" in p.stderr
    worktree = env["home"] / "worktrees" / "run_cli_a"
    assert sh(worktree, "git", "rev-parse", "--abbrev-ref", "HEAD").strip() == "jigworks/run_cli_a"
    assert sh(env["repo"], "git", "status", "--porcelain") == "", "the user's checkout is untouched"

    a1 = jw(env, "approve", "run_cli_a")
    a2 = jw(env, "approve", "run_cli_a")
    assert stdout_events(a2)[-1]["kind"] == "run_finished" and "succeeded" in a2.stderr
    events = log(env, "run_cli_a")
    assert events == out + stdout_events(a1) + stdout_events(a2), "stdout carries exactly the logged events"
    check_log(events)

    # the commit hash of every node is stored in the graph state
    snaps = {e["node"]: e["snapshot"]["commit"] for e in events if e.get("snapshot")}
    from jigworks_runner.package import load_package
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    pkg = load_package(env["home"] / "runs" / "run_cli_a" / "package")
    with sqlite3.connect(env["home"] / "runs" / "run_cli_a" / "checkpoints.sqlite") as conn:
        graph = pkg.build_graph().compile(checkpointer=SqliteSaver(conn))
        state = graph.get_state({"configurable": {"thread_id": "run_cli_a"}}).values
    assert state["commits"] == snaps

    audit_lines = (env["home"] / "runs" / "run_cli_a" / "audit.jsonl").read_text().splitlines()
    assert len(audit_lines) == 3, "one audit record per command"
    audit = json.loads(audit_lines[-1])
    assert contracts.validate("AuditRecord", audit) == []
    assert audit["authorEmail"] == AUTHOR and audit["approverEmail"] == AUTHOR and audit["approvedAt"]
    assert audit["digest"].startswith("sha256:") and audit["status"] == "succeeded"
    assert any(s.get("gate") for s in audit["steps"]) and all(s.get("commit") for s in audit["steps"])
    assert {s.get("model") for s in audit["steps"] if s["node"] == "write_tests"} == {"claude-haiku-4-5-20251001"}
    assert {s.get("model") for s in audit["steps"] if s["node"] == "plan"} == {"claude-sonnet-5"}
    assert "model" not in next(s for s in audit["steps"] if s["node"] == "gate"), "no agent, no model"
    assert audit["changedFiles"] == ["sample-repo/tests/test_notes.py", "sample-repo/sample_repo/notes.py"]
    assert audit["prUrl"].endswith("#demo/run_cli_a")
    assert "refs/heads/demo/run_cli_a" in sh(env["repo"], "git", "ls-remote", str(env["remote"]))

    shown = json.loads(jw(env, "audit", "run_cli_a").stdout)
    # fake tokens (10 in / 20 out per call) priced with the release's models from the price table
    assert 0 < shown["apiEquivalentCostUsd"] < 0.01
    summary = json.loads(jw(env, "show", "run_cli_a").stdout)
    assert summary["status"] == "succeeded" and summary["progress"] == 100.0


def test_cli_request_changes_and_reject(env):
    start(env, "run_cli_rc", script(env["tmp"]))
    jw(env, "approve", "run_cli_rc")
    missing = jw(env, "request-changes", "run_cli_rc", check=False)
    assert missing.returncode == 2
    rc = jw(env, "request-changes", "run_cli_rc", "--comment", "Name the account too.")
    kinds = [e["kind"] for e in stdout_events(rc)]
    assert kinds[0] == "review_decision" and kinds[-1] == "interrupt"
    r = jw(env, "reject", "run_cli_rc")
    assert "rejected" in r.stderr
    summary = json.loads(jw(env, "show", "run_cli_rc").stdout)
    assert summary["followUpPrompts"] == 1 and summary["status"] == "rejected" and summary["fixLoops"] == 1
    assert jw(env, "approve", "run_cli_rc", check=False).returncode == 2, "nothing left to approve"


# --- resume after a restart (design.md §11.1) --------------------------------------------------


def test_cli_kill_mid_node_then_resume(env):
    s = script(env["tmp"], implement=[
        {"text": "slow", "sleep": 60, "files": {"sample-repo/sample_repo/partial.py": "x = 1\n"}},
        {"text": "done", "files": {"sample-repo/sample_repo/notes.py": FEATURE}},
    ])
    start(env, "run_cli_kill", s)
    approver = subprocess.Popen([sys.executable, "-m", "jigworks_runner.cli", "approve", "run_cli_kill", "--home", str(env["home"])],
                                cwd=env["repo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    wait_for(lambda: ("running", 1) in node_events(log(env, "run_cli_kill"), "implement"))
    time.sleep(0.3)
    approver.send_signal(signal.SIGKILL)
    approver.wait()

    ls = json.loads(jw(env, "ls", "--json").stdout)
    assert [(r["runId"], r["status"], r["node"]) for r in ls] == [("run_cli_kill", "interrupted", "implement")]

    resumed = jw(env, "resume", "run_cli_kill")
    assert "waiting for a human (pr review)" in resumed.stderr
    events = log(env, "run_cli_kill")
    check_log(events)
    assert node_events(events, "implement") == [("running", 1), ("cancelled", 1), ("running", 2), ("succeeded", 2)]
    assert node_events(events, "write_tests") == [("running", 1), ("succeeded", 1)], "finished nodes are not re-run"
    worktree = env["home"] / "worktrees" / "run_cli_kill"
    assert not (worktree / "sample-repo/sample_repo/partial.py").exists(), "the cut-off node's partial edit was reset"
    jw(env, "approve", "run_cli_kill")
    assert json.loads(jw(env, "show", "run_cli_kill").stdout)["status"] == "succeeded"


def test_cli_crash_after_commit_does_not_run_the_node_twice(env):
    start(env, "run_cli_crash", script(env["tmp"]))
    crashed = jw(env, "approve", "run_cli_crash", check=False, extra_env={"JIGWORKS_TEST_CRASH_AFTER_COMMIT": "implement"})
    assert crashed.returncode == 137
    events = log(env, "run_cli_crash")
    assert node_events(events, "implement") == [("running", 1), ("succeeded", 1)]
    implement_commit = next(e["snapshot"]["commit"] for e in events if e.get("node") == "implement" and e.get("snapshot"))

    jw(env, "resume", "run_cli_crash")
    events = log(env, "run_cli_crash")
    check_log(events)
    assert node_events(events, "implement") == [("running", 1), ("succeeded", 1)], "implement was not executed again"
    agent_calls = [e for e in events if e["kind"] == "agent_output" and e["node"] == "implement"]
    assert len(agent_calls) == 1
    assert node_events(events, "review")[0] == ("running", 1)
    worktree = env["home"] / "worktrees" / "run_cli_crash"
    log_lines = sh(worktree, "git", "log", "--format=%H %s").splitlines()
    assert sum("jigworks: implement" in line for line in log_lines) == 1
    assert any(line.startswith(implement_commit) for line in log_lines)


def test_cli_relative_pr_remote_and_retry_of_a_failed_push(env):
    """Regression from the T06 live run: a relative --pr-remote was resolved against the worktree.
    A node that crashes (here: the push) fails the run, and `resume` retries it."""
    later = env["tmp"] / "later.git"
    args = ["run", "--workflow", str(WORKFLOW), "--repo", str(env["repo"] / "sample-repo"), "--prompt", "Add describe(order)",
            "--adapter", "fake", "--fake-script", str(script(env["tmp"])), "--run-id", "run_retry",
            "--home", str(env["home"]), "--pr-remote", "../later.git"]
    jw(env, *args)
    jw(env, "approve", "run_retry")
    failed = jw(env, "approve", "run_retry", check=False)
    assert failed.returncode == 1 and "failed" in failed.stderr
    assert node_events(log(env, "run_retry"), "open_pr") == [("running", 1), ("failed", 1)]

    sh(env["tmp"], "git", "init", "-q", "--bare", str(later))
    retried = jw(env, "resume", "run_retry")
    assert "succeeded" in retried.stderr
    events = log(env, "run_retry")
    check_log(events)
    assert node_events(events, "open_pr") == [("running", 1), ("failed", 1), ("running", 2), ("succeeded", 2)]
    assert "refs/heads/demo/run_retry" in sh(env["repo"], "git", "ls-remote", str(later))
    assert json.loads(jw(env, "show", "run_retry").stdout)["status"] == "succeeded"


# --- parallel sessions -------------------------------------------------------------------------


def test_cli_parallel_runs_are_isolated(env):
    a = script(env["tmp"], "a.json", plan=[{"text": "plan A", "sleep": 1.5}],
               implement=[{"text": "A", "files": {"sample-repo/sample_repo/notes.py": FEATURE, "sample-repo/sample_repo/only_a.py": "A = 1\n"}}])
    b = script(env["tmp"], "b.json", plan=[{"text": "plan B", "sleep": 1.5}],
               implement=[{"text": "B", "files": {"sample-repo/sample_repo/notes.py": FEATURE, "sample-repo/sample_repo/only_b.py": "B = 2\n"}}])
    pa, pb = start(env, "run_par_a", a, popen=True), start(env, "run_par_b", b, popen=True)
    assert pa.wait(60) == 0 and pb.wait(60) == 0

    for rid in ("run_par_a", "run_par_b"):
        p = subprocess.Popen([sys.executable, "-m", "jigworks_runner.cli", "approve", rid, "--home", str(env["home"])],
                             cwd=env["repo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        globals().setdefault("_procs", []).append(p)
    for p in globals().pop("_procs"):
        assert p.wait(120) == 0, p.stderr.read()

    ls = jw(env, "ls")
    print(ls.stdout)
    rows = {r["runId"]: r for r in json.loads(jw(env, "ls", "--json").stdout)}
    assert {k: (v["status"], v["node"]) for k, v in rows.items()} == {
        "run_par_a": ("waiting_human", "approve_pr"), "run_par_b": ("waiting_human", "approve_pr")}
    wa, wb = Path(rows["run_par_a"]["worktree"]), Path(rows["run_par_b"]["worktree"])
    assert wa != wb
    assert (wa / "sample-repo/sample_repo/only_a.py").exists() and not (wa / "sample-repo/sample_repo/only_b.py").exists()
    assert (wb / "sample-repo/sample_repo/only_b.py").exists() and not (wb / "sample-repo/sample_repo/only_a.py").exists()
    for rid in rows:
        events = log(env, rid)
        check_log(events)
        assert {e["runId"] for e in events} == {rid}
        assert (env["home"] / "runs" / rid / "checkpoints.sqlite").exists()


def test_cli_second_command_on_a_busy_run_is_refused(env):
    s = script(env["tmp"], implement=[{"text": "slow", "sleep": 30}])
    start(env, "run_busy", s)
    p = subprocess.Popen([sys.executable, "-m", "jigworks_runner.cli", "approve", "run_busy", "--home", str(env["home"])],
                         cwd=env["repo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    wait_for(lambda: ("running", 1) in node_events(log(env, "run_busy"), "implement"))
    second = jw(env, "resume", "run_busy", check=False)
    p.kill()
    p.wait()
    assert second.returncode == 2 and "another runner process" in second.stderr


# --- progress -----------------------------------------------------------------------------------


def test_progress_matches_recorded_run_and_never_moves_back():
    manifest = tomllib.loads((FIXTURES / "bundles/src/feature-development/workflow.toml").read_text())
    events = [json.loads(x) for x in (FIXTURES / "runs/run_fd_0002-fix-loops-request-changes.jsonl").read_text().splitlines()]
    ledger = Ledger(weights={k: float(v) for k, v in manifest["weights"].items()})
    seen = []
    for e in events:
        ledger.apply(e)
        if e["kind"] == "node_status":
            assert ledger.progress() == e["progress"], (e["seq"], e["node"], e["status"])
            seen.append(ledger.progress())
    assert seen == sorted(seen) and seen[-1] == 100.0
    assert ledger.fix_loops == 3 and ledger.follow_ups == 1


def test_progress_weights_from_history_of_the_same_digest():
    manifest = tomllib.loads((WORKFLOW / "workflow.toml").read_text())
    digest = "sha256:" + "a" * 64

    def audit(d, secs):
        steps = [{"node": n, "attempt": 1, "status": "succeeded", "startedAt": "2026-11-19T10:00:00Z",
                  "finishedAt": f"2026-11-19T10:{secs.get(n, 1) // 60:02d}:{secs.get(n, 1) % 60:02d}Z"}
                 for n in manifest["plannedPath"]]
        return {"digest": d, "status": "succeeded", "steps": steps}

    secs = {"plan": 60, "write_tests": 120, "implement": 600, "review": 60, "gate": 30, "open_pr": 5, "summary": 10}
    weights, source = weights_from_history(manifest, digest, [audit(digest, secs), audit("sha256:" + "b" * 64, {})])
    assert source == "history (1 runs)"
    assert weights["implement"] == 600 and weights["plan"] == 60
    scale = sum(secs.values()) / sum(manifest["weights"][n] for n in secs)
    assert weights["approve_pr"] == round(manifest["weights"]["approve_pr"] * scale, 3)
    fallback, source = weights_from_history(manifest, digest, [audit("sha256:" + "b" * 64, secs)])
    assert source == "workflow.toml" and fallback["implement"] == 30


def test_cli_graph_prints_graph_json(env):
    out = jw(env, "graph", str(WORKFLOW))
    graph = json.loads(out.stdout)
    assert contracts.validate("GraphJSON", graph) == [] and graph["release"] == "feature-development@1.5.0"
