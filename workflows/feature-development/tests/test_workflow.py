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
from jigworks_runner.package import bundle_files, load_package

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


def touch(path: str = "sample-repo/sample_repo/notes.py"):
    """A fixer that changes something every round (a fixer that changes nothing goes to the human)."""
    def apply(cwd: Path) -> None:
        p = cwd / path
        p.write_text(p.read_text() + "# fix round\n")
    return apply


def script(**overrides) -> dict:
    base = {
        "triage": [FakeStep("ROUTE: QUICK\nREASON: one small function.")],
        "plan": [FakeStep("1. Add describe(order) in sample-repo/sample_repo/notes.py.\n2. Test it.")],
        "write_tests": [FakeStep("added test_describe_order", files={"sample-repo/tests/test_notes.py": FEATURE_TEST})],
        "implement": [FakeStep("implemented describe", files={"sample-repo/sample_repo/notes.py": FEATURE})],
        "review": [FakeStep("Looks right.\nVERDICT: PASS")],
        "fix": [FakeStep("fixed", edit=touch())],
        "summary": [FakeStep("Added describe(order); gate green.")],
    }
    base.update(overrides)
    return base


def new_run(repo: Path, steps: dict, run_id: str = "run_t05", **options) -> tuple[WorkflowRun, FakeAdapter]:
    agent = FakeAdapter(steps)
    options = {"gate": {"scope": ["sample-repo/"]}, **options}  # like `jigworks run --repo sample-repo`
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
    """Approve every gate except approve_fix: approving that one grants more fixes, so a fixer
    that never fixes would loop forever. The test decides there itself."""
    for _ in range(20):
        if outcome.status != "waiting_human" or outcome.interrupt["node"] == "approve_fix":
            return outcome
        outcome = run.decide("approve", APPROVER)
    raise AssertionError("still waiting for a human after 20 approvals")


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
        ("triage", "succeeded"), ("plan", "succeeded"), ("approve_plan", "waiting_human"), ("approve_plan", "succeeded"),
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
    assert log[-1].startswith("jigworks: triage (attempt 1)")
    assert len(log) == len([s for s in run.ledger.steps if s.get("commit")])
    assert all(s.get("commit") for s in run.ledger.steps)


def test_models_come_from_the_release(repo):
    run, agent = new_run(repo, script())
    approve_all(run, run.start("Add describe(order)"))
    models = {c.node: c.options.model for c in agent.calls}
    assert models == {
        "triage": "claude-sonnet-5-5", "plan": "claude-opus-5-5", "write_tests": "claude-opus-5-5", "implement": "claude-sonnet-5-5",
        "review": "claude-opus-5-5", "summary": "claude-sonnet-5-5",
    }
    efforts = {c.node: c.options.effort for c in agent.calls}
    assert efforts["review"] == "medium" and efforts["triage"] == "low" and efforts["implement"] is None
    declared = set(run.package.allowed_tools())
    assert all(set(c.options.allowed_tools) <= declared for c in agent.calls)


def test_every_agent_gets_the_skills_of_the_release(repo):
    run, agent = new_run(repo, script())
    approve_all(run, run.start("Add describe(order)"))
    plugin = PACKAGE_DIR / "plugin"
    assert all(c.options.plugin_dirs == (str(plugin),) for c in agent.calls)
    files = bundle_files(PACKAGE_DIR)
    assert json.loads(files["plugin/.claude-plugin/plugin.json"])["name"] == "feature-development"
    skills = [p for p in files if p.startswith("plugin/skills/") and p.endswith("/SKILL.md")]
    assert len(skills) >= 3
    for path in skills:
        head = files[path].decode().split("---")[1]
        assert "name:" in head and "description:" in head, path


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
    assert "property tests" in fix_call.prompt
    check_stream(run)


def failing_review(*open_counts: int) -> list[FakeStep]:
    """One failing review per count, with that many open findings (IDs F1..Fn)."""
    return [FakeStep("\n".join(f"- F{i} notes.py:{i} problem {i}" for i in range(1, n + 1)) + "\nVERDICT: FAIL")
            for n in open_counts]


def test_fixes_go_on_by_themselves_while_the_findings_shrink(repo):
    run, agent = new_run(repo, script(review=[*failing_review(4, 3, 2, 1), FakeStep("- F1 FIXED\nVERDICT: PASS")],
                                      fix=[FakeStep("fixed one more", edit=touch())]))
    out = run.start("Add describe(order)")
    assert out.interrupt["node"] == "approve_plan"
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_pr", "progress never asks the human"
    assert [c.node for c in agent.calls].count("fix") == 4
    assert out.status == "waiting_human"
    check_stream(run)


def test_stalled_fixes_ask_the_human_with_a_round_by_round_report(repo):
    run, agent = new_run(repo, script(review=failing_review(3, 2, 2, 2), fix=[FakeStep("tightened the limit check", edit=touch())]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.status == "waiting_human" and out.interrupt["node"] == "approve_fix"
    assert [c.node for c in agent.calls].count("fix") == 3, "3 → 2 is progress; 2 → 2 → 2 is two fixes without it"
    report = out.interrupt["plan"]
    assert "did not lower the number of open problems" in report
    assert "3 → 2 → 2 → 2" in report and "tightened the limit check" in report
    assert report.count("| fix |") == 3
    assert "## Latest findings" in report and "F2 notes.py:2" in report
    assert node_trace(run)[-1] == ("approve_fix", "waiting_human")
    check_stream(run)


def test_continue_at_approve_fix_grants_more_fixes_and_passes_the_hint(repo):
    run, agent = new_run(repo, script(review=[*failing_review(2, 2, 2), FakeStep("- F1 FIXED\n- F2 FIXED\nVERDICT: PASS")]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix"
    out = run.decide("request_changes", APPROVER, comment="Use the remaining quantity, not the total.")
    assert out.interrupt["node"] == "approve_pr"
    last_fix = [c for c in agent.calls if c.node == "fix"][-1]
    assert "Use the remaining quantity, not the total." in last_fix.prompt
    rereview = [c for c in agent.calls if c.node == "review"][-1]
    assert "Findings of the previous review" in rereview.prompt and "F2 notes.py:2" in rereview.prompt
    assert approve_all(run, out).status == "succeeded"
    check_stream(run)


def test_fix_cap_asks_the_human_even_with_progress(repo):
    run, agent = new_run(repo, script(review=failing_review(5, 4, 3, 2)), max_fix_loops=2)
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix" and "cap is reached" in out.interrupt["message"]
    assert [c.node for c in agent.calls].count("fix") == 2
    check_stream(run)


def test_a_reviewer_question_goes_to_the_human_before_any_fix(repo):
    question = "QUESTION: Should describe() print EUR or USD? I recommend USD."
    run, agent = new_run(repo, script(review=[FakeStep(f"- F1 notes.py:3 currency missing\n{question}\nVERDICT: FAIL"),
                                              FakeStep("- F1 FIXED\nVERDICT: PASS")]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix"
    assert "fix" not in [c.node for c in agent.calls], "the human answers before anyone fixes"
    assert "## Questions from the reviewer" in out.interrupt["plan"] and "EUR or USD" in out.interrupt["plan"]
    out = run.decide("request_changes", APPROVER, comment="USD.")
    fix_call = next(c for c in agent.calls if c.node == "fix")
    assert "USD." in fix_call.prompt
    rereview = [c for c in agent.calls if c.node == "review"][-1]
    assert "Human:\nUSD." in rereview.prompt, "the reviewer sees the human's answer too"
    assert out.interrupt["node"] == "approve_pr"
    check_stream(run)


def test_a_blocked_fixer_asks_the_human_at_once(repo):
    """The real run_20261120122836_6ab988: the fixer could not download a library (denied) and
    said so in prose for 5 rounds while new reviewers found 3 to 14 different problems."""
    blocked = ("I made no changes this round.\n"
               "NEEDS HUMAN: vendor the chart library: curl -sSLO https://example.com/lib.js\n"
               "NEEDS HUMAN: approve the load-test gap")
    run, agent = new_run(repo, script(review=[*failing_review(2), FakeStep("- F1 FIXED\n- F2 FIXED\nVERDICT: PASS")],
                                      fix=[FakeStep(blocked), FakeStep("used the vendored file", edit=touch())]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix"
    assert [c.node for c in agent.calls].count("review") == 1, "no second review after a blocked fix"
    report = out.interrupt["plan"]
    assert "## What the fixer needs from you" in report
    assert "1. vendor the chart library: curl -sSLO https://example.com/lib.js" in report
    assert "2. approve the load-test gap" in report
    assert "## The fixer's last reply" in report and "blocked on something only you can do" in report
    out = run.decide("request_changes", APPROVER, comment="Vendored lib.js; the load-test gap is approved.")
    assert "Vendored lib.js" in [c for c in agent.calls if c.node == "fix"][-1].prompt
    assert out.interrupt["node"] == "approve_pr"
    check_stream(run)


def test_a_fix_that_changes_nothing_asks_the_human(repo):
    run, agent = new_run(repo, script(review=failing_review(3, 3), fix=[FakeStep("I made no changes this round.")]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix"
    assert [c.node for c in agent.calls].count("fix") == 1
    assert "The last fix changed nothing" in out.interrupt["plan"]
    assert "(no changes)" in out.interrupt["plan"]
    check_stream(run)


def test_a_fix_that_changes_nothing_after_the_human_answered_goes_back_to_review(repo):
    """The real run_20261120161021_60bbf3: once the human had answered everything, the fixer
    rightly changed nothing, and approve_fix → fix → approve_fix looped with no way back to review."""
    question = "QUESTION: Should the test require `filled`? I recommend yes."
    run, agent = new_run(repo, script(
        review=[FakeStep(f"- F1 notes.py:1 race\n- F2 notes.py:2 scratch file\n{question}\nVERDICT: FAIL"),
                FakeStep("- F1 FIXED\n- F2 ACCEPTED: the human keeps the scratch file\nVERDICT: PASS")],
        fix=[FakeStep("fixed F1\nNEEDS HUMAN: approve keeping the scratch file", edit=touch()),
             FakeStep("No code changes this round: everything is settled.")]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix"
    out = run.decide("request_changes", APPROVER, comment="Yes, require filled.")
    assert out.interrupt["node"] == "approve_fix", "the fixer is blocked on the human"
    report = out.interrupt["plan"]
    assert "## Questions from the reviewer" not in report, "an answered question is not asked again"
    assert "QUESTION:" not in report
    out = run.decide("request_changes", APPROVER, comment="Keep the scratch file, it is fine.")
    assert out.interrupt["node"] == "approve_pr", "a no-change fix after the human's answer goes to review"
    assert [c.node for c in agent.calls].count("fix") == 2
    rereview = [c for c in agent.calls if c.node == "review"][-1]
    assert "Keep the scratch file, it is fine." in rereview.prompt, "the reviewer sees answers given to the fixer"
    assert "Yes, require filled." in rereview.prompt
    check_stream(run)


def test_approve_after_a_fix_that_changed_nothing_rechecks_without_another_fix(repo):
    run, agent = new_run(repo, script(review=[*failing_review(2), FakeStep("- F1 FIXED\n- F2 FIXED\nVERDICT: PASS")],
                                      fix=[FakeStep("Nothing left to change.")]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix"
    assert "Re-run the check) to re-run the independent review" in out.interrupt["message"]
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_pr"
    assert [c.node for c in agent.calls].count("fix") == 1, "Approve re-runs the review, not the fixer"
    check_stream(run)


def test_a_fixer_that_keeps_changing_nothing_cannot_loop_without_a_check(repo):
    run, agent = new_run(repo, script(review=failing_review(2, 2, 2), fix=[FakeStep("Nothing to change.")]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    for _ in range(3):
        assert out.interrupt["node"] == "approve_fix"
        out = run.decide("request_changes", APPROVER, comment="Try again.")
    calls = [c.node for c in agent.calls]
    assert calls.count("review") >= 3, f"every human answer leads to a check: {calls}"
    check_stream(run)


def test_an_accepted_finding_is_closed():
    pkg = load_package(PACKAGE_DIR)
    nodes = sys.modules[f"{pkg.module_name}.steps.nodes"]
    assert nodes.open_findings("- F1 FIXED\n- F2 ACCEPTED: the human waived it\nVERDICT: PASS") == 0
    assert nodes.open_findings("- F1 FIXED\n- F2 NOT FIXED: still racy\nVERDICT: FAIL") == 1


def test_a_fix_that_only_adds_a_file_is_a_change(repo):
    run, agent = new_run(repo, script(review=[*failing_review(1), FakeStep("- F1 FIXED\nVERDICT: PASS")],
                                      fix=[FakeStep("added the missing module",
                                                    files={"sample-repo/sample_repo/extra.py": "X = 1\n"})]))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_pr"
    check_stream(run)


def test_reject_at_approve_fix_stops_the_run(repo):
    run, _ = new_run(repo, script(review=failing_review(1)))
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_fix"
    out = run.decide("reject", APPROVER)
    assert out.status == "rejected"
    check_stream(run)


def test_reject_at_the_plan(repo):
    run, agent = new_run(repo, script())
    run.start("Add describe(order)")
    out = run.decide("reject", APPROVER)
    assert out.status == "rejected"
    assert [c.node for c in agent.calls] == ["triage", "plan"]
    decision = next(e for e in events(run) if e["kind"] == "review_decision")
    assert decision["runStatus"] == "rejected" and decision["reviewDecision"]["approverEmail"] == APPROVER
    assert node_trace(run)[-1] == ("approve_plan", "failed")
    assert events(run)[-1]["summary"]["status"] == "rejected"
    check_stream(run)


def test_request_changes_at_the_plan_replans_in_the_same_session(repo):
    steps = script(plan=[
        FakeStep("1. Add describe(order) in sample-repo/sample_repo/notes.py."),
        FakeStep("1. Add describe(order) in sample-repo/sample_repo/notes.py, lower-case side.\n2. Test it."),
    ])
    run, agent = new_run(repo, steps)
    run.start("Add describe(order)")
    out = run.decide("request_changes", APPROVER, comment="Use the lower-case side name.")
    assert out.status == "waiting_human" and out.interrupt["stage"] == "plan"
    assert "lower-case side" in out.interrupt["plan"]
    first, second = [c for c in agent.calls if c.node == "plan"]
    assert second.options.resume_session_id == first.session_id  # the planner keeps its memory
    assert "Use the lower-case side name." in second.prompt
    assert "write_tests" not in [c.node for c in agent.calls]  # nothing is built on a plan under discussion
    out = run.decide("approve", APPROVER)
    tests_call = next(c for c in agent.calls if c.node == "write_tests")
    assert "lower-case side" in tests_call.prompt
    out = run.decide("approve", APPROVER)
    # Agreeing on the plan comes before the first result, so it is not a correction of it (design.md §8).
    assert events(run)[-1]["summary"]["followUpPrompts"] == 0
    check_stream(run)


def test_planner_asks_questions_before_it_plans(repo):
    steps = script(plan=[
        FakeStep("QUESTIONS:\n1. Should the side be upper- or lower-case?"),
        FakeStep("1. Add describe(order) in sample-repo/sample_repo/notes.py, lower-case side.\n2. Test it."),
    ])
    run, agent = new_run(repo, steps)
    out = run.start("Add describe(order)")
    assert out.interrupt["stage"] == "plan" and "question" in out.interrupt["message"].lower()
    assert "upper- or lower-case" in out.interrupt["plan"]
    out = run.decide("request_changes", APPROVER, comment="Lower-case.")
    assert "Lower-case." in [c for c in agent.calls if c.node == "plan"][1].prompt
    run.decide("approve", APPROVER)
    # The agents after the plan see what was agreed, not only the final plan.
    for node in ("write_tests", "implement", "review"):
        call_ = next(c for c in agent.calls if c.node == node)
        assert "upper- or lower-case" in call_.prompt and "Lower-case." in call_.prompt, node
    check_stream(run)


def test_approving_open_questions_does_not_start_the_build(repo):
    steps = script(plan=[
        FakeStep("QUESTIONS:\n1. Should the side be upper- or lower-case?"),
        FakeStep("Assuming lower-case.\n1. Add describe(order) in sample-repo/sample_repo/notes.py."),
    ])
    run, agent = new_run(repo, steps)
    run.start("Add describe(order)")
    out = run.decide("approve", APPROVER)
    assert out.interrupt["stage"] == "plan"  # a question is not a plan; the planner states assumptions first
    assert "assumptions" in [c for c in agent.calls if c.node == "plan"][1].prompt
    assert "write_tests" not in [c.node for c in agent.calls]


def test_planning_round_limit_ends_the_run_failed(repo):
    run, agent = new_run(repo, script(plan=[FakeStep("QUESTIONS:\n1. Which one?")]))
    out = run.start("Add describe(order)")
    rounds = 1
    while out.status == "waiting_human":
        out = run.decide("request_changes", APPROVER, comment=f"Answer {rounds}.")
        rounds += 1
    assert out.status == "failed"
    assert len([c for c in agent.calls if c.node == "plan"]) == 5
    assert "planning round limit" in next(e for e in events(run) if e["kind"] == "error")["error"]["message"]
    check_stream(run)


# --- brainstorming (1.6.0) -----------------------------------------------------------------------

DESIGN_TEXT = ("DESIGN:\n## Goal\nA describe(order) helper for the order log.\n## Invariants\n"
               "- describe never changes the order.\n## Decisions and assumptions\n- lower-case side (human).")


def brainstorm_script(**overrides) -> dict:
    steps = {
        "triage": [FakeStep("ROUTE: BRAINSTORM\nREASON: a new module with open scope.")],
        "brainstorm": [
            FakeStep("QUESTIONS:\n## Scope\n1. Only orders, or fills too?\n2. Upper- or lower-case side?"),
            FakeStep("QUESTIONS:\n## Format\n1. You said fills too: one line per fill?"),
            FakeStep(DESIGN_TEXT),
        ],
    }
    steps.update(overrides)
    return script(**steps)


def test_quick_route_skips_brainstorming(repo):
    run, agent = new_run(repo, script())
    approve_all(run, run.start("Fix the typo in describe(order)"))
    assert "brainstorm" not in [c.node for c in agent.calls]
    assert run.ledger.steps[0]["node"] == "triage"


def test_keyword_in_the_prompt_goes_to_brainstorming_without_a_triage_call(repo):
    run, agent = new_run(repo, brainstorm_script(triage=[FakeStep("ROUTE: QUICK")]))
    out = run.start("Brainstorming: an order log for the desk")
    assert [c.node for c in agent.calls] == ["brainstorm"]  # no agent decided; the human did
    assert out.interrupt["stage"] == "plan" and "Brainstorming, round 1" in out.interrupt["message"]
    assert "Only orders, or fills too?" in out.interrupt["plan"]


def test_triage_agent_routes_a_large_change_to_brainstorming(repo):
    run, agent = new_run(repo, brainstorm_script())
    out = run.start("Build an order log module for the desk")
    assert [c.node for c in agent.calls] == ["triage", "brainstorm"]
    assert out.interrupt["stage"] == "plan" and "question" in out.interrupt["message"].lower()


def test_brainstorming_asks_rounds_until_the_design_is_complete(repo):
    run, agent = new_run(repo, brainstorm_script())
    run.start("Brainstorm an order log")
    out = run.decide("request_changes", APPROVER, comment="1. Fills too. 2. Lower-case.")
    assert "Brainstorming, round 2" in out.interrupt["message"] and "one line per fill" in out.interrupt["plan"]
    out = run.decide("request_changes", APPROVER, comment="Yes, one line per fill.")
    assert "design is complete" in out.interrupt["message"] and "## Goal" in out.interrupt["plan"]
    calls = [c for c in agent.calls if c.node == "brainstorm"]
    assert len(calls) == 3
    assert calls[1].options.resume_session_id == calls[0].session_id  # one conversation
    assert calls[2].options.resume_session_id == calls[0].session_id
    assert "Fills too" in calls[1].prompt and "one line per fill" in calls[2].prompt
    assert "plan" not in [c.node for c in agent.calls]  # nothing is planned before the design is approved
    out = run.decide("approve", APPROVER)
    # The design goes to the planner, then the usual plan approval.
    assert out.interrupt["stage"] == "plan" and "Approve the plan" in out.interrupt["message"]
    plan_call = next(c for c in agent.calls if c.node == "plan")
    assert "## Approved design" in plan_call.prompt and "describe never changes the order" in plan_call.prompt
    assert "DESIGN:" not in plan_call.prompt
    out = run.decide("approve", APPROVER)
    for node in ("write_tests", "implement", "review"):
        assert "describe never changes the order" in next(c for c in agent.calls if c.node == node).prompt, node
    assert approve_all(run, out).status == "succeeded"
    trace = [n for n, st in node_trace(run) if st != "waiting_human"]
    assert trace[:9] == ["triage", "brainstorm", "approve_brainstorm", "brainstorm", "approve_brainstorm",
                         "brainstorm", "approve_brainstorm", "plan", "approve_plan"]
    assert events(run)[-1]["progress"] == 100.0  # the planned path is complete on this branch too
    assert events(run)[-1]["summary"]["followUpPrompts"] == 0
    check_stream(run)


def test_approving_open_brainstorm_questions_asks_for_a_design(repo):
    run, agent = new_run(repo, brainstorm_script(brainstorm=[FakeStep("QUESTIONS:\n1. Fills too?"), FakeStep(DESIGN_TEXT)]))
    run.start("Brainstorm an order log")
    out = run.decide("approve", APPROVER)
    assert "design is complete" in out.interrupt["message"]
    assert "Decide every open point yourself" in [c for c in agent.calls if c.node == "brainstorm"][1].prompt
    assert "plan" not in [c.node for c in agent.calls]


def test_brainstorm_model_and_effort_come_from_the_release(repo):
    run, agent = new_run(repo, brainstorm_script())
    run.start("Brainstorm an order log")
    c = next(c for c in agent.calls if c.node == "brainstorm")
    assert c.options.model == "claude-opus-5-5" and c.options.effort == "high"
    assert set(c.options.allowed_tools) <= {"Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)"}


def test_reject_while_brainstorming(repo):
    run, agent = new_run(repo, brainstorm_script())
    run.start("Brainstorm an order log")
    out = run.decide("reject", APPROVER)
    assert out.status == "rejected"
    assert node_trace(run)[-1] == ("approve_brainstorm", "failed")


def test_brainstorming_round_limit_ends_the_run_failed(repo):
    run, agent = new_run(repo, brainstorm_script(brainstorm=[FakeStep("QUESTIONS:\n1. Which one?")]), max_brainstorm_rounds=3)
    out = run.start("Brainstorm an order log")
    while out.status == "waiting_human":
        out = run.decide("request_changes", APPROVER, comment="An answer.")
    assert out.status == "failed"
    assert len([c for c in agent.calls if c.node == "brainstorm"]) == 3
    assert "brainstorming round limit" in next(e for e in events(run) if e["kind"] == "error")["error"]["message"]


def test_brainstorming_survives_a_new_process_from_the_checkpoint(repo, tmp_path):
    """The run is driven by a new process between rounds (the extension calls the CLI once per
    decision): the LangGraph checkpoint brings back the brainstormer's session and the answers."""
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    db = tmp_path / "checkpoints.sqlite"
    with sqlite3.connect(db, check_same_thread=False) as conn:
        run, agent = new_run(repo, brainstorm_script())
        run.graph = run.package.build_graph().compile(checkpointer=SqliteSaver(conn))
        run.start("Brainstorm an order log")
        run.decide("request_changes", APPROVER, comment="1. Fills too. 2. Lower-case.")
        first_session = agent.calls[1].session_id
        saved_events, base = list(run.sink.events), run.base_commit
    with sqlite3.connect(db, check_same_thread=False) as conn:
        from jigworks_runner.events import EventSink

        agent2 = FakeAdapter(brainstorm_script())
        sink = EventSink(run_id="run_t05", events=saved_events, next_seq=len(saved_events))
        run2 = WorkflowRun(load_package(PACKAGE_DIR), run_id="run_t05", cwd=repo, agent=agent2, author_email=AUTHOR,
                           sink=sink, checkpointer=SqliteSaver(conn), base_commit=base,
                           options={"gate": {"scope": ["sample-repo/"]}}, branch="jigworks/run_t05", repo="jigworks")
        out = run2.decide("request_changes", APPROVER, comment="Yes, one line per fill.")
        assert "design is complete" in out.interrupt["message"]
        (call_,) = agent2.calls
        assert call_.node == "brainstorm" and call_.options.resume_session_id == first_session
        out = run2.decide("approve", APPROVER)
        plan_call = next(c for c in agent2.calls if c.node == "plan")
        assert "describe never changes the order" in plan_call.prompt  # the design came from the checkpoint


def test_every_agent_gets_the_context_it_needs(repo):
    run, agent = new_run(repo, brainstorm_script(
        write_tests=[FakeStep("tests/test_notes.py: test_describe_order checks the text",
                              files={"sample-repo/tests/test_notes.py": FEATURE_TEST})],
        implement=[FakeStep("notes.py: added describe()", files={"sample-repo/sample_repo/notes.py": FEATURE})],
        brainstorm=[FakeStep(DESIGN_TEXT)],
    ))
    approve_all(run, run.start("Brainstorm an order log"))
    by = {c.node: c.prompt for c in agent.calls}
    for node in ("write_tests", "implement", "review"):
        assert "## Task (from the human)" in by[node] and "## Approved plan" in by[node], node
        assert "## Approved design" in by[node] and "describe never changes the order" in by[node], node
    assert "test_describe_order checks the text" in by["implement"]  # the implementer knows the tests
    assert "test_describe_order checks the text" in by["review"] and "added describe()" in by["review"]
    assert "added describe()" not in by["write_tests"]  # the test writer never sees the implementation
    assert "Route: brainstorm" in by["summary"] and "describe never changes the order" in by["summary"]
    for text in by.values():
        assert "$" + "prompt" not in text and "$" + "spec" not in text and "$" + "earlier" not in text


def test_triage_answer_without_a_route_goes_the_quick_way(repo):
    run, agent = new_run(repo, script(triage=[FakeStep("I think this is small.")]))
    out = run.start("Add describe(order)")
    assert [c.node for c in agent.calls] == ["triage", "plan"] and out.interrupt["stage"] == "plan"


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


@pytest.mark.parametrize("scanner", ["built-in", "gitleaks"])
def test_planted_secret_fails_the_gate(repo, monkeypatch, scanner):
    real_which = shutil.which
    if scanner == "gitleaks":
        if not real_which("gitleaks"):
            pytest.skip("gitleaks is not installed")
    else:
        monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None if name == "gitleaks" else real_which(name, *a, **k))
    rule = "aws-access-key-id" if scanner == "built-in" else "aws-access-token"
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
    assert not first["passed"] and not secret["passed"] and rule in secret["summary"]
    assert FAKE_KEY not in json.dumps(first)
    assert all(c["passed"] for c in first["checks"] if c["kind"] != "secret_scan")
    assert second["passed"]
    check_stream(run)


def test_security_finding_fails_the_gate(repo):
    risky = FEATURE + "\nimport subprocess\n\ndef run(cmd):\n    return subprocess.call(cmd, shell=True)\n"
    run, _ = new_run(repo, script(implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": risky})]),
                     max_fix_loops=1)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "waiting_human" and out.interrupt["node"] == "approve_fix", "1.7.0 asks the human, never fails"
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


INVARIANT_TESTS = (SAMPLE / "tests" / "test_invariants.py").read_text()
EXTRA_PROPERTY = """

@given(qty=st.integers(min_value=1, max_value=50))
def test_new_order_starts_with_nothing_filled(qty):
    assert qty >= 1
"""


def test_implement_cannot_weaken_the_invariant_tests(repo):
    # design.md: tests and invariants are written by a different agent before implementation.
    # Here `implement` breaks I1 and guts the property tests that would catch it: without the
    # guard every check passes. The gate must fail, and `fix` must restore both.
    steps = script(
        implement=[FakeStep("implemented, and 'cleaned up' slow tests",
                            files={"sample-repo/sample_repo/notes.py": FEATURE,
                                   "sample-repo/tests/test_invariants.py": "def test_ok():\n    pass\n"},
                            edit=edit("sample-repo/sample_repo/orders.py", *OVERFILL))],
        fix=[FakeStep("restored the tests and the remaining check",
                      files={"sample-repo/tests/test_invariants.py": INVARIANT_TESTS},
                      edit=edit("sample-repo/sample_repo/orders.py", OVERFILL[1], OVERFILL[0]))],
    )
    run, agent = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    first, second = [e["gateResult"] for e in events(run) if e["kind"] == "gate_result"][:2]
    guard = next(c for c in first["checks"] if c["name"] == "protected tests")
    assert not first["passed"] and not guard["passed"]
    assert "sample-repo/tests/test_invariants.py" in guard["summary"]
    assert second["passed"]
    fix_call = next(c for c in agent.calls if c.node == "fix")
    assert "protected tests" in fix_call.prompt
    check_stream(run)


def test_the_human_can_accept_a_change_to_a_protected_test(repo):
    """run_20261120161021_60bbf3: the human ruled that a test from write_tests was wrong (option
    b) and the fixer changed it. The gate rejects that for ever, and the only way out was to
    reject the run and build everything again. Now the human accepts exactly that change."""
    fixed_test = FEATURE_TEST.replace('"buy 3 SYN-A (new)"', '"buy 3 SYN-A (new)"  # ruled by the human')
    steps = script(
        review=[FakeStep("- F1 tests/test_notes.py:8 the test asserts the wrong thing\nVERDICT: FAIL"),
                FakeStep("- F1 FIXED\nVERDICT: PASS")],
        fix=[FakeStep("changed the test as the human ruled", files={"sample-repo/tests/test_notes.py": fixed_test}),
             FakeStep("NEEDS HUMAN: approve the change to sample-repo/tests/test_notes.py (you ruled option b)")],
    )
    run, agent = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.interrupt["node"] == "approve_fix"
    report = out.interrupt["plan"]
    assert "## Changes to protected files" in report and "sample-repo/tests/test_notes.py" in report
    assert "# ruled by the human" in report, "the human sees the diff they accept"
    assert "Accept these changes**) accepts exactly these" in out.interrupt["message"]
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_pr", "the accepted change passes the gate"
    gates = [e["gateResult"] for e in events(run) if e["kind"] == "gate_result"]
    assert not gates[0]["passed"] and gates[-1]["passed"]
    assert [c.node for c in agent.calls].count("fix") == 2
    check_stream(run)


def test_a_comment_does_not_accept_protected_files_and_the_screen_says_so(repo):
    """run_20261120161021_60bbf3: the human typed "I agree with the change" instead of pressing
    Approve; the fixer then claimed the files were accepted and the gate failed again."""
    fixed_test = FEATURE_TEST + "\n# ruled by the human\n"
    steps = script(
        review=[FakeStep("- F1 the test is wrong\nVERDICT: FAIL"), FakeStep("- F1 FIXED\nVERDICT: PASS")],
        fix=[FakeStep("changed the test", files={"sample-repo/tests/test_notes.py": fixed_test}),
             FakeStep("NEEDS HUMAN: accept the change to sample-repo/tests/test_notes.py")],
    )
    run, agent = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert "## Changes to protected files" in out.interrupt["plan"]
    assert "A comment does not accept them" in out.interrupt["message"]
    out = run.decide("request_changes", APPROVER, comment="I agree with the change.")
    assert out.interrupt["node"] == "approve_fix"
    assert "You answered with a comment" in out.interrupt["plan"], "the screen says why it asks again"
    assert "only Approve" in [c for c in agent.calls if c.node == "fix"][-1].prompt
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_pr"
    check_stream(run)


def test_an_accepted_protected_change_is_pinned_to_its_contents(repo):
    fixed_test = FEATURE_TEST + "\n# ruled by the human\n"
    steps = script(
        review=[FakeStep("- F1 the test is wrong\nVERDICT: FAIL"), FakeStep("- F1 FIXED\nVERDICT: PASS")],
        fix=[FakeStep("changed the test", files={"sample-repo/tests/test_notes.py": fixed_test}),
             FakeStep("NEEDS HUMAN: approve the test change"),
             FakeStep("weakened it further", files={"sample-repo/tests/test_notes.py": "def test_ok():\n    pass\n"})],
    )
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_pr"
    out = run.decide("request_changes", APPROVER, comment="Tidy up.")  # → fix (weakens the test) → gate
    last = [e["gateResult"] for e in events(run) if e["kind"] == "gate_result"][-1]
    guard = next(c for c in last["checks"] if c["name"] == "protected tests")
    assert not guard["passed"], "a later edit of the accepted file fails the gate again"
    check_stream(run)


def test_a_new_suppression_marker_needs_the_human(repo):
    """run_20261120161021_60bbf3: the fixer silenced bandit B608 with `# nosec` and the gate would
    have passed without anyone approving it."""
    silenced = FEATURE + "import subprocess  # nosec B404\n"
    steps = script(
        implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": silenced})],
        fix=[FakeStep("NEEDS HUMAN: accept the `# nosec B404` in notes.py (only a constant is used)")],
    )
    run, agent = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.interrupt["node"] == "approve_fix"
    first = [e["gateResult"] for e in events(run) if e["kind"] == "gate_result"][0]
    check = next(c for c in first["checks"] if c["name"] == "suppressions")
    assert not check["passed"] and "sample-repo/sample_repo/notes.py" in check["summary"] and "nosec" in check["summary"]
    report = out.interrupt["plan"]
    assert "## New suppressions" in report and "# nosec B404" in report
    out = run.decide("approve", APPROVER)
    assert out.interrupt["node"] == "approve_pr", "the accepted suppression passes the gate"
    check_stream(run)


def test_suppressions_written_by_the_test_writer_are_not_flagged(repo):
    skipping = FEATURE_TEST + '\n\nimport pytest\n\n\n@pytest.mark.skip(reason="needs network")\ndef test_feed():\n    pass\n'
    steps = script(write_tests=[FakeStep("tests", files={"sample-repo/tests/test_notes.py": skipping})])
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"


def test_fixers_may_delete_files_and_run_the_gate_scanners(repo):
    run, agent = new_run(repo, script(review=[*failing_review(1), FakeStep("- F1 FIXED\nVERDICT: PASS")]))
    approve_all(run, run.start("Add describe(order)"))
    fix_call = next(c for c in agent.calls if c.node == "fix")
    tools = fix_call.options.allowed_tools
    assert {"Bash(git rm:*)", "Bash(bandit:*)", "Bash(gitleaks:*)"} <= set(tools)
    assert "bandit -q -ll -s B101" in fix_call.prompt, "the fixer is told how the gate scans"


def test_scratch_files_of_the_test_writer_are_not_protected(repo):
    steps = script(
        write_tests=[FakeStep("tests", files={"sample-repo/tests/test_notes.py": FEATURE_TEST,
                                              "sample-repo/check_tmp.py": "print(1)\n"})],
        review=[FakeStep("- F1 sample-repo/check_tmp.py scratch file left in\nVERDICT: FAIL"),
                FakeStep("- F1 FIXED\nVERDICT: PASS")],
        fix=[FakeStep("removed the scratch file", files={"sample-repo/check_tmp.py": None})],
    )
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded", "deleting the test writer's scratch file passes the gate"
    gate = [e["gateResult"] for e in events(run) if e["kind"] == "gate_result"][-1]
    assert next(c for c in gate["checks"] if c["name"] == "protected tests")["passed"]


def test_agents_are_told_how_to_treat_scratch_files_and_rules_outside_the_scope(repo):
    run, agent = new_run(repo, script(review=[*failing_review(1), FakeStep("- F1 FIXED\nVERDICT: PASS")]))
    approve_all(run, run.start("Add describe(order)"))
    prompts = {c.node: c.prompt for c in agent.calls}
    for node in ("write_tests", "implement", "fix"):
        assert "scratch" in prompts[node], node
    for node in ("review", "fix"):
        assert "outside the scope" in prompts[node] and "not a finding" in prompts[node], node


def test_write_tests_may_extend_the_invariant_tests(repo):
    steps = script(write_tests=[FakeStep("added a property test",
                                         files={"sample-repo/tests/test_notes.py": FEATURE_TEST,
                                                "sample-repo/tests/test_invariants.py": INVARIANT_TESTS + EXTRA_PROPERTY})])
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    gate = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    assert gate["passed"]
    assert next(c for c in gate["checks"] if c["name"] == "protected tests")["passed"]


def test_implement_cannot_add_pytest_configuration(repo):
    weaken = "from hypothesis import settings\nsettings.register_profile('x', max_examples=1)\nsettings.load_profile('x')\n"
    steps = script(implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": FEATURE,
                                                             "sample-repo/conftest.py": weaken})],
                   fix=[FakeStep("removed it", files={"sample-repo/conftest.py": None})])
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    first = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    guard = next(c for c in first["checks"] if c["name"] == "protected tests")
    assert not guard["passed"] and "sample-repo/conftest.py" in guard["summary"]


def test_implement_may_create_an_invariants_file_but_not_change_one(repo):
    """run_20261120122836_6ab988: the plan gave INVARIANTS.md to the implementer and a test from
    write_tests requires it, but the gate called any INVARIANTS.md "changed after write_tests", so
    no fix could pass. A new one is the implementer's; an existing one stays read-only."""
    new_doc = "# Invariants\n\n1. Filled never exceeds the order quantity.\n"
    steps = script(implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": FEATURE,
                                                             "sample-repo/sample_repo/INVARIANTS.md": new_doc})])
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    gate = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    assert next(c for c in gate["checks"] if c["name"] == "protected tests")["passed"]


def test_implement_cannot_change_the_existing_invariants_file(repo):
    steps = script(implement=[FakeStep("implemented", files={"sample-repo/sample_repo/notes.py": FEATURE},
                                       edit=lambda cwd: (cwd / "sample-repo/INVARIANTS.md").write_text("# none\n"))],
                   fix=[FakeStep("I made no changes this round.")])
    run, _ = new_run(repo, steps)
    approve_all(run, run.start("Add describe(order)"))
    gate = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    guard = next(c for c in gate["checks"] if c["name"] == "protected tests")
    assert not guard["passed"] and "sample-repo/INVARIANTS.md" in guard["summary"]


def test_security_findings_in_the_read_only_tests_do_not_block_the_fixer(repo):
    """run_20261120122836_6ab988: bandit B108 (a /tmp path) in a test from write_tests failed the
    gate on every round, and implement/fix may not edit that test. Reported, not counted."""
    tmp_test = FEATURE_TEST + '\n\ndef test_path():\n    assert "/tmp/x.sqlite3".endswith(".sqlite3")\n'
    steps = script(write_tests=[FakeStep("added tests", files={"sample-repo/tests/test_notes.py": tmp_test})])
    run, _ = new_run(repo, steps)
    out = approve_all(run, run.start("Add describe(order)"))
    assert out.status == "succeeded"
    gate = next(e for e in events(run) if e["kind"] == "gate_result")["gateResult"]
    bandit = next(c for c in gate["checks"] if c["kind"] == "security_scan")
    assert bandit["passed"]
    assert "B108" in bandit["summary"] and "read-only" in bandit["summary"]


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
    assert node_trace(run) == [("triage", "succeeded"), ("plan", "failed")]
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
