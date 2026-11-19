"""feature-development with the fake adapter, on a real git repo holding a copy of sample-repo.

The gate is real (pytest, Hypothesis property tests, secret scan, bandit, scope), so every
"gate FAIL" here is caused by an actual change in the worktree, not by a stub.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jigworks_contracts as contracts
import pytest

from jigworks_runner.adapters.fake import FakeAdapter, FakeStep
from jigworks_runner.engine import RunStateError, WorkflowRun
from jigworks_runner.package import load_package

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = ROOT / "workflows" / "feature-development"
SAMPLE = ROOT / "sample-repo"
AUTHOR = "dev@example.com"
APPROVER = "lead@example.com"

FEATURE_TEST = '''from sample_repo.notes import describe
from sample_repo import OrderService, Side


def test_describe_order():
    svc = OrderService()
    order = svc.place("acc-1", "SYN-A", Side.BUY, 3)
    assert describe(order) == "buy 3 SYN-A (new)"
'''
FEATURE = '''def describe(order):
    return f"{order.side.value} {order.quantity} {order.instrument} ({order.status.value})"
'''
OVERFILL = ("if quantity > self.remaining:", "if quantity > self.quantity:")
FAKE_KEY = "AKIA" + "Q" * 4 + "7" * 4 + "ZXCV" + "BNML"  # built here so no scanner sees a literal key


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    shutil.copytree(SAMPLE, work / "sample-repo", ignore=shutil.ignore_patterns("__pycache__", ".hypothesis", "scripts"))
    (work / ".gitignore").write_text("__pycache__/\n.hypothesis/\n.pytest_cache/\n")
    sh(work, "git", "init", "-q", "-b", "main")
    sh(work, "git", "config", "user.email", AUTHOR)
    sh(work, "git", "config", "user.name", "Dev")
    sh(work, "git", "add", "-A")
    sh(work, "git", "commit", "-q", "-m", "base")
    bare = tmp_path / "origin.git"
    sh(tmp_path, "git", "init", "-q", "--bare", str(bare))
    sh(work, "git", "remote", "add", "origin", str(bare))
    sh(work, "git", "push", "-q", "origin", "main")
    return work


def edit(path: str, old: str, new: str):
    def apply(cwd: Path) -> None:
        p = cwd / path
        p.write_text(p.read_text().replace(old, new))
    return apply


def script(**overrides) -> dict:
    base = {
        "plan": [FakeStep("1. Add describe(order) in sample-repo/sample_repo/notes.py.\n2. Test it.")],
        "write_tests": [FakeStep("added test_describe_order", files={"sample-repo/tests/test_notes.py": FEATURE_TEST})],
        "implement": [FakeStep("implemented describe", files={"sample-repo/sample_repo/notes.py": FEATURE})],
        "review": [FakeStep("Looks right.\nVERDICT: PASS")],
        "fix": [FakeStep("fixed")],
        "summary": [FakeStep("Added describe(order); gate green.")],
    }
    base.update(overrides)
    return base


def new_run(repo: Path, steps: dict, run_id: str = "run_t05", **options) -> tuple[WorkflowRun, FakeAdapter]:
    agent = FakeAdapter(steps)
    run = WorkflowRun(load_package(PACKAGE_DIR), run_id=run_id, cwd=repo, agent=agent, author_email=AUTHOR,
                      options=options, branch=f"jigworks/{run_id}", repo="jigworks")
    return run, agent


def events(run: WorkflowRun) -> list[dict]:
    return run.sink.events


def node_trace(run: WorkflowRun) -> list[tuple[str, str]]:
    return [(e["node"], e["status"]) for e in events(run) if e["kind"] == "node_status" and e["status"] != "running"]


def check_stream(run: WorkflowRun) -> None:
    evs = events(run)
    assert [e["seq"] for e in evs] == list(range(len(evs))), "seq must count from 0 without gaps"
    for e in evs:
        assert contracts.validate("RunEvent", e) == [], e
    progress = [e["progress"] for e in evs if "progress" in e]
    assert progress == sorted(progress), f"progress moved backwards: {progress}"
    assert contracts.validate("AuditRecord", run.audit()) == []


def approve_all(run: WorkflowRun, outcome):
    while outcome.status == "waiting_human":
        outcome = run.decide("approve", APPROVER)
    return outcome


# --- paths ------------------------------------------------------------------------------------


def test_happy_path_approved_first_time(repo):
    run, agent = new_run(repo, script())
    out = run.start("Add describe(order)")
    assert out.status == "waiting_human" and out.interrupt["stage"] == "plan"
    assert "describe" in out.interrupt["plan"]
    out = run.decide("approve", APPROVER)
    assert out.status == "waiting_human" and out.interrupt["stage"] == "pr"
    out = run.decide("approve", APPROVER)
    assert out.status == "succeeded"
    assert node_trace(run) == [
        ("plan", "succeeded"), ("approve_plan", "waiting_human"), ("approve_plan", "succeeded"),
        ("write_tests", "succeeded"), ("implement", "succeeded"), ("review", "succeeded"),
        ("gate", "succeeded"), ("approve_pr", "waiting_human"), ("approve_pr", "succeeded"),
        ("open_pr", "succeeded"), ("summary", "succeeded"),
    ]
    finished = events(run)[-1]
    assert finished["kind"] == "run_finished" and finished["progress"] == 100.0
    summary = finished["summary"]
    assert summary["followUpPrompts"] == 0 and summary["fixLoops"] == 0
    assert summary["firstResultCommit"] and summary["approverEmail"] == APPROVER
    assert summary["changedFiles"] == ["sample-repo/tests/test_notes.py", "sample-repo/sample_repo/notes.py"]
    gate = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    assert gate["passed"] and {c["kind"] for c in gate["checks"]} >= {"tests", "property_tests", "secret_scan", "security_scan"}
    check_stream(run)


def test_one_git_commit_per_node(repo):
    run, _ = new_run(repo, script())
    approve_all(run, run.start("Add describe(order)"))
    log = sh(repo, "git", "log", "--format=%s", f"{run.base_commit}..HEAD").splitlines()
    assert log[-1].startswith("jigworks: plan (attempt 1)")
    assert len(log) == len([s for s in run.ledger.steps if s.get("commit")])
    assert all(s.get("commit") for s in run.ledger.steps)


def test_models_come_from_the_release(repo):
    run, agent = new_run(repo, script())
    approve_all(run, run.start("Add describe(order)"))
    models = {c.node: c.options.model for c in agent.calls}
    assert models == {
        "plan": "claude-sonnet-5", "write_tests": "claude-haiku-4-5-20251001", "implement": "claude-sonnet-5",
        "review": "claude-sonnet-5", "summary": "claude-haiku-4-5-20251001",
    }
    declared = set(run.package.allowed_tools())
    assert all(set(c.options.allowed_tools) <= declared for c in agent.calls)


def test_tests_and_review_run_in_separate_sessions(repo):
    run, agent = new_run(repo, script(review=[FakeStep("VERDICT: FAIL\n- missing docstring"), FakeStep("VERDICT: PASS")]))
    approve_all(run, run.start("Add describe(order)"))
    by_node = {}
    for c in agent.calls:
        by_node.setdefault(c.node, []).append(c)
    sessions = {n: {c.session_id for c in calls} for n, calls in by_node.items()}
    assert sessions["write_tests"].isdisjoint(sessions["implement"])
    assert sessions["review"].isdisjoint(sessions["implement"])
    assert by_node["write_tests"][0].options.resume_session_id is None
    assert all(c.options.resume_session_id is None for c in by_node["review"])
    # fix resumes the implementer's session
    assert by_node["fix"][0].options.resume_session_id == by_node["implement"][0].session_id
    assert "notes.py" not in by_node["write_tests"][0].prompt.split("## Approved plan")[0]


def test_review_fail_then_fix_then_pass(repo):
    run, agent = new_run(repo, script(review=[FakeStep("- describe() ignores the limit\nVERDICT: FAIL"), FakeStep("VERDICT: PASS")]))
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    trace = node_trace(run)
    i = trace.index(("review", "failed"))
    assert trace[i + 1] == ("fix", "succeeded") and trace[i + 2] == ("review", "succeeded")
    fix_call = next(c for c in agent.calls if c.node == "fix")
    assert "describe() ignores the limit" in fix_call.prompt
    assert events(run)[-1]["summary"]["fixLoops"] == 1
    check_stream(run)


def test_gate_fail_on_broken_invariant_then_fix_then_pass(repo):
    steps = script(
        implement=[FakeStep("implemented, and 'simplified' the overfill guard",
                            files={"sample-repo/sample_repo/notes.py": FEATURE},
                            edit=edit("sample-repo/sample_repo/orders.py", *OVERFILL))],
        fix=[FakeStep("restored the remaining check", edit=edit("sample-repo/sample_repo/orders.py", OVERFILL[1], OVERFILL[0]))],
    )
    run, agent = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    gates = [e for e in events(run) if e["kind"] == "gate_result"]
    assert [g["gateResult"]["passed"] for g in gates] == [False, True]
    failed = {c["kind"]: c["passed"] for c in gates[0]["gateResult"]["checks"]}
    assert failed["property_tests"] is False and failed["tests"] is True, "only the property tests see the bug"
    trace = node_trace(run)
    i = trace.index(("gate", "failed"))
    assert trace[i + 1] == ("fix", "succeeded") and trace[i + 2] == ("gate", "succeeded")
    fix_call = next(c for c in agent.calls if c.node == "fix")
    assert "hypothesis invariants" in fix_call.prompt
    check_stream(run)


def test_fix_loop_limit_ends_the_run_failed(repo):
    run, agent = new_run(repo, script(review=[FakeStep("VERDICT: FAIL")]), max_fix_loops=2)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "failed"
    assert [c.node for c in agent.calls].count("fix") == 2
    trace = node_trace(run)
    assert trace[-1] == ("fix", "failed")
    err = [e for e in events(run) if e["kind"] == "error"][-1]
    assert "fix loop limit" in err["error"]["message"]
    assert events(run)[-1]["runStatus"] == "failed"
    check_stream(run)


def test_reject_at_the_plan(repo):
    run, agent = new_run(repo, script())
    run.start("Add describe(order)")
    out = run.decide("reject", APPROVER)
    assert out.status == "rejected"
    assert [c.node for c in agent.calls] == ["plan"]
    decision = next(e for e in events(run) if e["kind"] == "review_decision")
    assert decision["runStatus"] == "rejected" and decision["reviewDecision"]["approverEmail"] == APPROVER
    assert node_trace(run)[-1] == ("approve_plan", "failed")
    assert events(run)[-1]["summary"]["status"] == "rejected"
    check_stream(run)


def test_reject_at_the_pr_review(repo):
    run, _ = new_run(repo, script())
    run.start("Add describe(order)")
    run.decide("approve", APPROVER)
    out = run.decide("reject", APPROVER)
    assert out.status == "rejected"
    assert "open_pr" not in [n for n, _ in node_trace(run)]
    branches = sh(repo, "git", "ls-remote", "--heads", "origin")
    assert "demo/" not in branches


def test_request_changes_goes_fix_gate_review(repo):
    steps = script(fix=[FakeStep("used a clearer format", files={"sample-repo/sample_repo/notes.py": FEATURE + "\n# reviewed\n"})])
    run, agent = new_run(repo, steps)
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    first_commit = out.interrupt["commit"]
    with pytest.raises(RunStateError):
        run.decide("request_changes", APPROVER)  # a comment is required
    out = run.decide("request_changes", APPROVER, comment="Mention the account in the description.")
    assert out.status == "waiting_human" and out.interrupt["stage"] == "pr"
    assert out.interrupt["commit"] != first_commit
    out = run.decide("approve", APPROVER)
    assert out.status == "succeeded"
    trace = node_trace(run)
    i = trace.index(("approve_pr", "cancelled"))
    assert trace[i + 1 : i + 4] == [("fix", "succeeded"), ("gate", "succeeded"), ("approve_pr", "waiting_human")]
    fix_call = next(c for c in agent.calls if c.node == "fix")
    assert "Mention the account" in fix_call.prompt and "requested changes" in fix_call.prompt
    summary = events(run)[-1]["summary"]
    assert summary["followUpPrompts"] == 1 and summary["fixLoops"] == 1
    assert summary["firstResultCommit"] == first_commit != summary["finalCommit"]
    audit = run.audit()
    assert audit["firstResultCommit"] == first_commit
    assert [d["decision"] for d in audit["decisions"]] == ["approve", "request_changes", "approve"]
    check_stream(run)


def test_planted_secret_fails_the_gate(repo):
    leaky = FEATURE + f'\nAWS_ACCESS_KEY_ID = "{FAKE_KEY}"\n'
    steps = script(
        implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": leaky})],
        fix=[FakeStep("removed the key", files={"sample-repo/sample_repo/notes.py": FEATURE})],
    )
    run, agent = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    first, second = [e["gateResult"] for e in events(run) if e["kind"] == "gate_result"]
    secret = next(c for c in first["checks"] if c["kind"] == "secret_scan")
    assert not first["passed"] and not secret["passed"] and "aws-access-key-id" in secret["summary"]
    assert all(c["passed"] for c in first["checks"] if c["kind"] != "secret_scan")
    assert second["passed"]
    check_stream(run)


def test_security_finding_fails_the_gate(repo):
    risky = FEATURE + "\nimport subprocess\n\ndef run(cmd):\n    return subprocess.call(cmd, shell=True)\n"
    run, _ = new_run(repo, script(implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": risky})]),
                     max_fix_loops=1)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "failed"
    gate = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    bandit = next(c for c in gate["checks"] if c["kind"] == "security_scan")
    assert not bandit["passed"] and "B602" in bandit["summary"]


def test_change_outside_sample_repo_fails_the_gate(repo):
    steps = script(implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": FEATURE, "README.md": "hi\n"})],
                   fix=[FakeStep("reverted", files={"README.md": None})])
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    first = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    scope = next(c for c in first["checks"] if c["name"] == "scope")
    assert not scope["passed"] and "README.md" in scope["summary"]


def test_open_pr_pushes_demo_branch(repo):
    run, _ = new_run(repo, script(), run_id="run_t05_pr")
    approve_all(run, run.start("Add describe(order)"))
    heads = sh(repo, "git", "ls-remote", "--heads", "origin")
    assert "refs/heads/demo/run_t05_pr" in heads
    assert events(run)[-1]["summary"]["prUrl"].endswith("#demo/run_t05_pr")
    sh(repo, "git", "fetch", "-q", "origin")
    pushed = sh(repo, "git", "diff", "--name-only", "origin/main", "origin/demo/run_t05_pr").split()
    assert pushed
    assert all(f.startswith("sample-repo/") for f in pushed)


def test_usage_limit_pauses_and_resumes(repo):
    steps = script(implement=[FakeStep(status="usage_limit"), FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": FEATURE})])
    run, _ = new_run(repo, steps)
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.status == "paused_usage_limit"
    assert run.ledger.status == "paused_usage_limit"
    out = run.resume()
    assert out.status == "waiting_human"
    out = approve_all(run, out)
    assert out.status == "succeeded"
    implement = [e for e in events(run) if e["kind"] == "node_status" and e["node"] == "implement"]
    # the paused attempt is closed as cancelled, then the node runs again as attempt 2
    assert [(e["status"], e["attempt"]) for e in implement] == [("running", 1), ("cancelled", 1), ("running", 2), ("succeeded", 2)]
    check_stream(run)


def test_agent_failure_fails_the_run(repo):
    run, _ = new_run(repo, script(plan=[FakeStep(status="failed")]))
    out = run.start("Add describe(order)")
    assert out.status == "failed"
    kinds = [e["kind"] for e in events(run)]
    assert kinds.count("error") == 2 and kinds[-1] == "run_finished"  # adapter error + runner error
    assert node_trace(run) == [("plan", "failed")]
    check_stream(run)


def test_export_graph_prints_graph_json():
    proc = subprocess.run([sys.executable, "-m", "workflows.feature_development.export_graph"], cwd=ROOT,
                          capture_output=True, text=True, check=True)
    graph = json.loads(proc.stdout)
    assert contracts.validate("GraphJSON", graph) == []
    kinds = {n["id"]: n["kind"] for n in graph["nodes"]}
    assert kinds["approve_plan"] == kinds["approve_pr"] == "interrupt"
    edges = {(e["source"], e["target"]) for e in graph["edges"]}
    assert {("review", "fix"), ("fix", "review"), ("gate", "fix"), ("fix", "gate"), ("approve_pr", "fix"), ("fix", "__end__")} <= edges
