"""Node functions of feature-development. Every agent call goes through the runtime, which
picks the model from the release (`[models]`), runs the adapter in the run's worktree and
emits the events."""

from __future__ import annotations

import re
from pathlib import Path
from string import Template
from typing import Any

from . import gate as gate_checks
from .runtime import GATE_KEY, STATUS_KEY, Runtime, step

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
MAX_FIX_LOOPS = 3
MAX_PLAN_ROUNDS = 5
QUESTIONS = re.compile(r"^\s*QUESTIONS:", re.IGNORECASE)
APPROVED_OPEN_QUESTIONS = ("The human approved without answering your questions. State your assumptions "
                           "explicitly at the top, then write the plan.")

READ_ONLY = ("Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)")
WRITE = ("Read", "Glob", "Grep", "Edit", "Write", "Bash(python -m pytest:*)", "Bash(uv run pytest:*)")

VERDICT = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\b", re.IGNORECASE | re.MULTILINE)


class AgentFailed(RuntimeError):
    pass


def prompt(name: str, **values: Any) -> str:
    return Template((PROMPTS / f"{name}.md").read_text()).safe_substitute(**{k: str(v) for k, v in values.items()})


def scope_text(rt: Runtime) -> str:
    return ", ".join(rt.options.get("gate", {}).get("scope", gate_checks.DEFAULTS["scope"]))


def call(rt: Runtime, node: str, text: str, tools: tuple[str, ...], resume: str | None = None):
    reply = rt.agent(node, text, tools=tools, resume=resume)
    if reply.status != "succeeded":
        raise AgentFailed(f"{node}: agent {reply.status}")
    return reply


def asks_questions(plan_text: str) -> bool:
    return bool(QUESTIONS.match(plan_text or ""))


def spec(state: dict) -> str:
    """The approved plan plus the planning conversation that led to it, for the agents after the plan."""
    talk = state.get("clarifications") or []
    if not talk:
        return state.get("plan", "")
    return state.get("plan", "") + "\n\nAgreed with the human while planning:\n\n" + "\n\n".join(talk)


def verdict(text: str) -> bool:
    """PASS only when the reviewer says so explicitly; the last verdict line wins."""
    found = VERDICT.findall(text or "")
    return bool(found) and found[-1].upper() == "PASS"


@step("plan")
def plan(state: dict, rt: Runtime) -> dict:
    rounds = state.get("plan_rounds", 0)
    limit = int(rt.options.get("max_plan_rounds", MAX_PLAN_ROUNDS))
    if rounds >= limit:
        return {"outcome": "failed", "failure": f"planning round limit reached ({limit} rounds)", STATUS_KEY: "failed"}
    session, feedback = state.get("plan_session"), state.get("plan_feedback")
    if session and feedback:
        # Another planning round: the same session, so the planner remembers the conversation.
        reply = call(rt, "plan", prompt("replan", comment=feedback, scope=scope_text(rt)), READ_ONLY, resume=session)
    else:
        reply = call(rt, "plan", prompt("plan", prompt=state["prompt"], scope=scope_text(rt)), READ_ONLY)
    return {"plan": reply.text.strip(), "plan_session": reply.session_id or session or "", "plan_feedback": "",
            "plan_rounds": rounds + 1}


@step("approve_plan")
def approve_plan(state: dict, rt: Runtime) -> dict:
    plan_text = state.get("plan", "")
    questions = asks_questions(plan_text)
    message = ("The planner has questions. Answer them with Request changes." if questions
               else "Approve the plan? Request changes to discuss it with the planner.")
    answer = rt.ask_human("approve_plan", "plan", message, plan=plan_text)
    decision = answer["decision"]
    status = "failed" if decision == "reject" else "succeeded"
    update: dict[str, Any] = {"decision": decision, STATUS_KEY: status}
    if decision == "reject":
        update["outcome"] = "rejected"
    feedback = ""
    if decision == "request_changes":
        feedback = answer.get("comment") or ""
    elif decision == "approve" and questions:
        feedback = APPROVED_OPEN_QUESTIONS  # a question is not a plan
    if feedback:
        # Back to the planner; nothing is built on a plan under discussion.
        update["plan_feedback"] = feedback
        update["clarifications"] = [*(state.get("clarifications") or []),
                                    f"Planner:\n{plan_text}\n\nHuman:\n{feedback}"]
    return update


@step("write_tests")
def write_tests(state: dict, rt: Runtime) -> dict:
    # A separate agent session that sees only the spec (prompt + plan), never the implementation.
    text = prompt("write_tests", prompt=state["prompt"], plan=spec(state), scope=scope_text(rt))
    reply = call(rt, "write_tests", text, WRITE)
    return {"tests_summary": reply.text.strip()}


@step("implement")
def implement(state: dict, rt: Runtime) -> dict:
    text = prompt("implement", prompt=state["prompt"], plan=spec(state), scope=scope_text(rt))
    reply = call(rt, "implement", text, WRITE)
    return {"implement_session": reply.session_id or ""}


@step("review")
def review(state: dict, rt: Runtime) -> dict:
    # Independent: a new session that did not write the code.
    text = prompt("review", prompt=state["prompt"], plan=spec(state), base=rt.base_commit, scope=scope_text(rt))
    reply = call(rt, "review", text, READ_ONLY)
    passed = verdict(reply.text)
    return {
        "review_passed": passed,
        "review_findings": "" if passed else reply.text.strip(),
        "fix_target": "review",
        "fix_reason": "review",
        STATUS_KEY: "succeeded" if passed else "failed",
    }


@step("fix")
def fix(state: dict, rt: Runtime) -> dict:
    loops = state.get("fix_loops", 0)
    limit = int(rt.options.get("max_fix_loops", MAX_FIX_LOOPS))
    reason = state.get("fix_reason", "review")
    if loops >= limit:
        return {
            "outcome": "failed",
            "failure": f"fix loop limit reached ({limit} fixes; last reason: {reason})",
            STATUS_KEY: "failed",
        }
    if reason == "request_changes":
        problem = "The human reviewer requested changes:\n\n" + state.get("comment", "")
    elif reason == "gate":
        problem = "The gate failed:\n\n" + state.get("gate_report", "")
    else:
        problem = "The independent review failed:\n\n" + state.get("review_findings", "")
    text = prompt("fix", problem=problem, scope=scope_text(rt))
    # Resume the implementer's session: it has the context of its own change.
    reply = call(rt, "fix", text, WRITE, resume=state.get("implement_session") or None)
    update: dict[str, Any] = {"fix_loops": loops + 1}
    if reply.session_id:
        update["implement_session"] = reply.session_id
    return update


@step("gate")
def gate(state: dict, rt: Runtime) -> dict:
    result = gate_checks.run_gate(rt.cwd, rt.base_commit, rt.options.get("gate"),
                                  tests_base=(state.get("commits") or {}).get("write_tests"))
    return {
        "gate_passed": result["passed"],
        "gate_report": gate_checks.report(result),
        "fix_target": "gate",
        "fix_reason": "gate",
        GATE_KEY: result,
        STATUS_KEY: "succeeded" if result["passed"] else "failed",
    }


@step("approve_pr")
def approve_pr(state: dict, rt: Runtime) -> dict:
    answer = rt.ask_human("approve_pr", "pr", "Review the change before the PR is opened.")
    decision = answer["decision"]
    update: dict[str, Any] = {"decision": decision}
    if decision == "approve":
        update[STATUS_KEY] = "succeeded"
    elif decision == "request_changes":
        # The comment goes back to the agent as a follow-up prompt: fix → gate → approve_pr.
        update.update(
            comment=answer.get("comment", ""), fix_reason="request_changes", fix_target="gate", **{STATUS_KEY: "cancelled"}
        )
    else:
        update.update(outcome="rejected", **{STATUS_KEY: "failed"})
    return update


@step("open_pr")
def open_pr(state: dict, rt: Runtime) -> dict:
    title = state["prompt"].strip().splitlines()[0][:72]
    body = "\n\n".join(
        [
            "Opened by the Jigworks `feature-development` workflow.",
            "## Plan\n\n" + state.get("plan", ""),
            "## Gate\n\n" + state.get("gate_report", ""),
        ]
    )
    return {"pr_url": rt.open_pr(title, body)}


@step("summary")
def summary(state: dict, rt: Runtime) -> dict:
    text = prompt(
        "summary",
        prompt=state["prompt"],
        plan=state.get("plan", ""),
        gate=state.get("gate_report", ""),
        pr=state.get("pr_url", ""),
        fixes=state.get("fix_loops", 0),
    )
    reply = call(rt, "summary", text, ("Read",))
    return {"summary": reply.text.strip(), "outcome": "succeeded"}
