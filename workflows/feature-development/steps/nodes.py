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
MAX_BRAINSTORM_ROUNDS = 15
QUESTIONS = re.compile(r"^\s*QUESTIONS:", re.IGNORECASE)
DESIGN = re.compile(r"^[ \t]*DESIGN:[ \t]*", re.IGNORECASE | re.MULTILINE)
ROUTE = re.compile(r"^\s*ROUTE:\s*(QUICK|BRAINSTORM)\b", re.IGNORECASE | re.MULTILINE)
# The human asked for brainstorming in the prompt: no agent needs to decide.
BRAINSTORM_WORDS = re.compile(r"\bbrainstorm(?:ing|ed|s)?\b", re.IGNORECASE)
APPROVED_OPEN_QUESTIONS = ("The human approved without answering your questions. State your assumptions "
                           "explicitly at the top, then write the plan.")
APPROVED_OPEN_DESIGN_QUESTIONS = ("The human approved without answering your questions. Decide every open "
                                  "point yourself (the option you recommended), list it under "
                                  "`## Decisions and assumptions`, and reply with `DESIGN:` and the complete design.")

READ_ONLY = ("Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)")
# The repo's own test and install commands, so the agent can run what the gate runs.
WRITE = (
    "Read", "Glob", "Grep", "Edit", "Write",
    "Bash(python -m pytest:*)", "Bash(uv run pytest:*)", "Bash(uv add:*)", "Bash(uv sync:*)",
    "Bash(pnpm test:*)", "Bash(pnpm install:*)", "Bash(pnpm add:*)",
    "Bash(npm test:*)", "Bash(npm install:*)", "Bash(yarn test:*)", "Bash(yarn add:*)",
    "Bash(go test:*)", "Bash(cargo test:*)",
)

VERDICT = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\b", re.IGNORECASE | re.MULTILINE)


class AgentFailed(RuntimeError):
    pass


def prompt(name: str, **values: Any) -> str:
    return Template((PROMPTS / f"{name}.md").read_text()).safe_substitute(**{k: str(v) for k, v in values.items()})


def scope_text(rt: Runtime) -> str:
    return gate_checks.scope_label(rt.options.get("gate", {}).get("scope", gate_checks.DEFAULTS["scope"]))


def tests_text(rt: Runtime) -> str:
    """The test commands the gate will run, for the prompts (detected now, on the current tree)."""
    try:
        cfg = gate_checks.settings(Path(rt.cwd), rt.base_commit, rt.options.get("gate"))
    except Exception:  # noqa: BLE001 - only prompt text; the gate itself reports real errors
        return "the repo's test command"
    cmds = gate_checks._commands(cfg.get("tests")) + gate_checks._commands(cfg.get("property_tests"))
    if not cmds:
        root = gate_checks.gate_root(cfg.get("scope", gate_checks.DEFAULTS["scope"])) or "the repo root"
        return (f"no test command found yet. write_tests sets one up, and it must be found in `{root}` itself: "
                "the gate detects a package.json `test` script, pytest (`pytest.ini`, `conftest.py`, "
                "`tests/`), `go.mod` or `Cargo.toml` only there, not in subfolders (a project in a "
                "subfolder needs a root `pytest.ini` with `testpaths`, or a root package.json test script "
                "that runs it)")
    return ", ".join(f"`{' '.join(c)}`" for c in cmds)


def call(rt: Runtime, node: str, text: str, tools: tuple[str, ...], resume: str | None = None):
    reply = rt.agent(node, text, tools=tools, resume=resume)
    if reply.status != "succeeded":
        raise AgentFailed(f"{node}: agent {reply.status}")
    return reply


def asks_questions(plan_text: str) -> bool:
    return bool(QUESTIONS.match(plan_text or ""))


def asks_design_questions(text: str) -> bool:
    """The brainstormer is still asking unless it delivered a design (a `DESIGN:` line, normally
    the first; a stray preamble before it is dropped)."""
    return bool(QUESTIONS.match(text or "")) or not DESIGN.search(text or "")


def design_text(text: str) -> str:
    found = DESIGN.search(text or "")
    return (text or "")[found.end():].strip() if found else (text or "").strip()


def route(prompt_text: str, reply_text: str | None = None) -> tuple[str, str]:
    """(route, reason). Keywords in the prompt win; otherwise the triage agent's `ROUTE:` line.
    An answer without a route line goes the quick way, which still plans with the human."""
    if BRAINSTORM_WORDS.search(prompt_text or ""):
        return "brainstorm", "the prompt asks for brainstorming"
    found = ROUTE.findall(reply_text or "")
    if not found:
        return "quick", "no route in the triage answer; the quick path"
    reason = re.search(r"^\s*REASON:\s*(.+)$", reply_text or "", re.IGNORECASE | re.MULTILINE)
    return found[-1].lower(), (reason.group(1).strip() if reason else "")


def section(title: str, body: str | None) -> str:
    body = (body or "").strip()
    return f"## {title}\n\n{body}" if body else ""


def spec(state: dict) -> str:
    """What every agent after the plan works from, as Markdown sections: the approved plan, the
    approved design (brainstorming route) and what the human agreed while planning. Built from
    the checkpointed state, so a resumed run hands over exactly the same context."""
    talk = state.get("clarifications") or []
    parts = [
        section("Approved plan", state.get("plan")),
        section("Approved design (agreed with the human while brainstorming)", state.get("design")),
        section("Agreed with the human while planning", "\n\n".join(talk)),
    ]
    return "\n\n".join(p for p in parts if p)


def earlier(state: dict, *keys: str) -> str:
    """Results of earlier steps, by state key, as sections (empty ones are left out)."""
    titles = {
        "tests_summary": "Tests written for this change (by the test writer, from the spec)",
        "implement_summary": "What the implementer reports",
        "review_findings": "Findings of the independent review",
    }
    parts = [section(titles[k], state.get(k)) for k in keys]
    return "\n\n".join(p for p in parts if p) or "(none)"


def verdict(text: str) -> bool:
    """PASS only when the reviewer says so explicitly; the last verdict line wins."""
    found = VERDICT.findall(text or "")
    return bool(found) and found[-1].upper() == "PASS"


@step("triage")
def triage(state: dict, rt: Runtime) -> dict:
    """Quick path (plan → build) or brainstorming first. Keywords in the prompt decide without an
    agent call; otherwise a short read-only agent call judges the size of the change."""
    if BRAINSTORM_WORDS.search(state["prompt"]):
        chosen, reason = route(state["prompt"])
    else:
        reply = call(rt, "triage", prompt("triage", prompt=state["prompt"], scope=scope_text(rt)), READ_ONLY)
        chosen, reason = route(state["prompt"], reply.text)
    return {"route": chosen, "route_reason": reason}


@step("brainstorm")
def brainstorm(state: dict, rt: Runtime) -> dict:
    rounds = state.get("brainstorm_rounds", 0)
    limit = int(rt.options.get("max_brainstorm_rounds", MAX_BRAINSTORM_ROUNDS))
    if rounds >= limit:
        return {"outcome": "failed", "failure": f"brainstorming round limit reached ({limit} rounds)",
                STATUS_KEY: "failed"}
    session, feedback = state.get("brainstorm_session"), state.get("brainstorm_feedback")
    if session and feedback:
        reply = call(rt, "brainstorm", prompt("rebrainstorm", comment=feedback), READ_ONLY, resume=session)
    else:
        text = prompt("brainstorm", prompt=state["prompt"], scope=scope_text(rt), tests=tests_text(rt))
        reply = call(rt, "brainstorm", text, READ_ONLY)
    return {"brainstorm": reply.text.strip(), "brainstorm_session": reply.session_id or session or "",
            "brainstorm_feedback": "", "brainstorm_rounds": rounds + 1}


@step("approve_brainstorm")
def approve_brainstorm(state: dict, rt: Runtime) -> dict:
    text = state.get("brainstorm", "")
    questions = asks_design_questions(text)
    n = state.get("brainstorm_rounds", 1)
    message = (f"Brainstorming, round {n}: answer the questions with Request changes "
               "(one line each is enough), or Approve to let the agent decide the rest." if questions
               else f"Brainstorming, round {n}: the design is complete. Approve it to plan the "
               "implementation, or Request changes to discuss it.")
    answer = rt.ask_human("approve_brainstorm", "plan", message, plan=text)
    decision = answer["decision"]
    update: dict[str, Any] = {"decision": decision, STATUS_KEY: "failed" if decision == "reject" else "succeeded"}
    if decision == "reject":
        update["outcome"] = "rejected"
        return update
    feedback = ""
    if decision == "request_changes":
        feedback = answer.get("comment") or ""
    elif questions:
        feedback = APPROVED_OPEN_DESIGN_QUESTIONS  # questions are not a design
    if feedback:
        update["brainstorm_feedback"] = feedback
        update["brainstorm_log"] = [*(state.get("brainstorm_log") or []), f"Brainstormer:\n{text}\n\nHuman:\n{feedback}"]
    else:
        update["design"] = design_text(text)
    return update


@step("plan")
def plan(state: dict, rt: Runtime) -> dict:
    rounds = state.get("plan_rounds", 0)
    limit = int(rt.options.get("max_plan_rounds", MAX_PLAN_ROUNDS))
    if rounds >= limit:
        return {"outcome": "failed", "failure": f"planning round limit reached ({limit} rounds)", STATUS_KEY: "failed"}
    session, feedback = state.get("plan_session"), state.get("plan_feedback")
    if session and feedback:
        # Another planning round: the same session, so the planner remembers the conversation.
        reply = call(rt, "plan", prompt("replan", comment=feedback, scope=scope_text(rt), tests=tests_text(rt)), READ_ONLY, resume=session)
    elif state.get("design"):
        text = prompt("plan_from_design", prompt=state["prompt"], design=state["design"], scope=scope_text(rt), tests=tests_text(rt))
        reply = call(rt, "plan", text, READ_ONLY)
    else:
        reply = call(rt, "plan", prompt("plan", prompt=state["prompt"], scope=scope_text(rt), tests=tests_text(rt)), READ_ONLY)
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
    text = prompt("write_tests", prompt=state["prompt"], spec=spec(state), scope=scope_text(rt), tests=tests_text(rt))
    reply = call(rt, "write_tests", text, WRITE)
    return {"tests_summary": reply.text.strip()}


@step("implement")
def implement(state: dict, rt: Runtime) -> dict:
    text = prompt("implement", prompt=state["prompt"], spec=spec(state), earlier=earlier(state, "tests_summary"),
                  scope=scope_text(rt), tests=tests_text(rt))
    reply = call(rt, "implement", text, WRITE)
    return {"implement_session": reply.session_id or "", "implement_summary": reply.text.strip()}


@step("review")
def review(state: dict, rt: Runtime) -> dict:
    # Independent: a new session that did not write the code.
    text = prompt("review", prompt=state["prompt"], spec=spec(state), earlier=earlier(state, "tests_summary", "implement_summary"),
                  base=rt.base_commit, scope=scope_text(rt), tests=tests_text(rt))
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
    session = state.get("implement_session") or None
    # Resume the implementer's session: it has the context of its own change. Without one (an
    # adapter without sessions), the fixer gets the whole specification instead.
    context = "" if session else "\n\n".join([section("Task", state["prompt"]), spec(state),
                                               earlier(state, "tests_summary", "implement_summary")])
    text = prompt("fix", problem=problem, context=context, scope=scope_text(rt), tests=tests_text(rt))
    reply = call(rt, "fix", text, WRITE, resume=session)
    update: dict[str, Any] = {"fix_loops": loops + 1, "implement_summary": reply.text.strip()}
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
            *(["## Design\n\n" + state["design"]] if state.get("design") else []),
            "## Gate\n\n" + state.get("gate_report", ""),
        ]
    )
    return {"pr_url": rt.open_pr(title, body)}


@step("summary")
def summary(state: dict, rt: Runtime) -> dict:
    text = prompt(
        "summary",
        prompt=state["prompt"],
        spec=spec(state),
        route=state.get("route", "quick"),
        gate=state.get("gate_report", ""),
        pr=state.get("pr_url", ""),
        fixes=state.get("fix_loops", 0),
    )
    reply = call(rt, "summary", text, ("Read",))
    return {"summary": reply.text.strip(), "outcome": "succeeded"}
