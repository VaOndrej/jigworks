"""Node functions of feature-development. Every agent call goes through the runtime, which
picks the model from the release (`[models]`), runs the adapter in the run's worktree and
emits the events."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from string import Template
from typing import Any

from . import gate as gate_checks
from .runtime import GATE_KEY, STATUS_KEY, Runtime, step

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
# Fixes run on their own while they make progress. The human is asked (approve_fix), never
# the run failed, when two fixes in a row did not lower the number of open problems, when the
# reviewer has a question only the human can answer, or at the cap below.
MAX_FIX_LOOPS = 8
STALL_ROUNDS = 2
EXTRA_FIXES = 3  # what Continue at approve_fix adds to the cap
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
    # Deleting a file (scratch files, a module the plan drops) and the gate's own scanners.
    "Bash(git rm:*)", "Bash(bandit:*)", "Bash(gitleaks:*)",
)
SCANNERS = ("`bandit -q -ll -s B101 <the changed .py files>` (medium and up) and `gitleaks` on the added lines "
            "(`git diff <base> | gitleaks stdin`)")

VERDICT = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\b", re.IGNORECASE | re.MULTILINE)
FINDING = re.compile(r"^\s*[-*]?\s*\**\[?F(\d+)\]?\**[:.)]?\s+(.*)$", re.MULTILINE)
BULLET = re.compile(r"^\s*[-*]\s+\S", re.MULTILINE)
REVIEW_QUESTION = re.compile(r"^\s*(?:[-*]\s*)?\**QUESTION\**:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
# What the fixer cannot do itself (a denied download, an approval, a decision): the human is asked at once.
FIXER_NEEDS = re.compile(r"^\s*(?:[-*]\s*)?\**NEEDS HUMAN\**:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


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
        section("Agreed with the human (planning, review and fix rounds; these decisions are final)", "\n\n".join(talk)),
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


def is_fixed(rest: str) -> bool:
    """`FIXED`, `— fixed`, `: Fixed.` after a finding ID, or `ACCEPTED` (the human accepted or
    waived it); `NOT FIXED` is open."""
    return rest.strip(" \t-—–:*").upper().startswith(("FIXED", "ACCEPTED"))


def open_findings(text: str) -> int:
    """Open findings in a review reply: lines with a finding ID (`- F3 ...`) that are not marked
    FIXED; without IDs, the bullet lines. A failed review counts at least one."""
    ids = {}
    for num, rest in FINDING.findall(text or ""):
        ids[num] = not is_fixed(rest)
    count = sum(ids.values()) if ids else len(BULLET.findall(text or ""))
    return max(count, 0 if verdict(text) else 1)


def first_open_finding(text: str) -> str:
    for line in (text or "").splitlines():
        found = FINDING.match(line)
        if found and not is_fixed(found.group(2)):
            return first_line(line)
    return first_line(text)


def without_questions(text: str) -> str:
    """A review reply without its QUESTION lines (once the human has answered them)."""
    return "\n".join(ln for ln in (text or "").splitlines() if not REVIEW_QUESTION.match(ln)).strip()


def review_questions(text: str) -> list[str]:
    return [q.strip() for q in REVIEW_QUESTION.findall(text or "")]


def fixer_needs(text: str) -> list[str]:
    return [n.strip() for n in FIXER_NEEDS.findall(text or "")]


def gate_problems(result: dict) -> int:
    return sum(int(c.get("findings") or 1) for c in result.get("checks", []) if not c.get("passed"))


def fix_cap(state: dict, rt: Runtime) -> int:
    return int(state.get("fix_cap") or rt.options.get("max_fix_loops", MAX_FIX_LOOPS))


def stalled(history: list[dict], check: str) -> bool:
    """Two fixes in a row did not lower the number of open problems of this check below the best
    count before them (only rounds since the human last said Continue)."""
    counts = [h["open"] for h in history if h.get("kind") == "check" and h.get("check") == check and not h.get("passed")]
    if len(counts) <= STALL_ROUNDS:
        return False
    return min(counts[-STALL_ROUNDS:]) >= min(counts[:-STALL_ROUNDS])


def escalation(state: dict, rt: Runtime, history: list[dict], check: str, questions: list[str]) -> str:
    """Why the human must decide before the next fix ("" = the fixer goes on by itself)."""
    if questions:
        return "questions"
    if state.get("fix_loops", 0) >= fix_cap(state, rt):
        return "limit"
    if stalled(history[state.get("fix_stall_from", 0):], check):
        return "stalled"
    return ""


def first_line(text: str, limit: int = 100) -> str:
    line = next((ln.strip(" #*-") for ln in (text or "").splitlines() if ln.strip()), "")
    return line if len(line) <= limit else line[: limit - 1] + "…"


def shortstat(cwd: Path, since: str | None) -> str:
    """What changed since `since`, committed or not (e.g. `2 files, +14 −3`)."""
    if not since:
        return ""
    try:
        out = subprocess.run(["git", "diff", "--numstat", since], cwd=cwd, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return ""
    rows = [ln.split("\t") for ln in out.splitlines() if ln.strip()]
    try:
        new = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=cwd, capture_output=True,
                             text=True, check=True).stdout.split("\n")
    except (subprocess.CalledProcessError, OSError):
        new = []
    rows += [["-", "-", f] for f in new if f.strip()]  # git diff does not list untracked files
    if not rows:
        return NO_CHANGES
    added = sum(int(r[0]) for r in rows if r[0].isdigit())
    removed = sum(int(r[1]) for r in rows if r[1].isdigit())
    return f"{len(rows)} file{'s' if len(rows) != 1 else ''}, +{added} −{removed}"


def head(cwd: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None


NO_CHANGES = "no changes"
CHECK_NAMES = {"review": "independent review", "gate": "gate"}
WHY = {
    "questions": "The reviewer has questions only you can answer. Answer them in the comment field.",
    "needs_human": "The fixer is blocked on something only you can do (see below). Do it and say what you did, "
                   "or Approve (in VS Code: Re-run the check) to check the change as it is.",
    "no_changes": "The last fix changed nothing and nobody had answered since the last check; another fix "
                  "round would cost tokens without progress.",
    "stalled": f"The last {STALL_ROUNDS} fixes did not lower the number of open problems.",
    "limit": "The fixes reached their cap.",
}


def fix_report(state: dict, protected: str = "", suppressions: str = "", commented_before: bool = False) -> str:
    """Markdown the human reads at approve_fix: why, the reviewer's questions, every round
    (what was found, what the fixer changed) and the trend of open problems. `protected` and
    `suppressions`: what the gate rejects and only Approve accepts."""
    history = state.get("fix_history") or []
    reason = state.get("escalation", "")
    why = WHY.get(reason, reason)
    if protected or suppressions:
        why = "The gate rejects changes that only you can accept (see below); nothing else is open for the fixer."
        if reason in ("questions", "stalled", "limit"):
            why += " " + WHY[reason]
    parts = [f"**Why you are asked:** {why}"]
    if commented_before:
        parts.append("**You answered with a comment last time.** A comment does not accept the changes below, so "
                     "the gate rejected them again. Press **Approve** (in VS Code: **Accept these changes**, with "
                     "the comment field empty) to accept them.")
    if protected:
        parts.append("## Changes to protected files\n\nThe gate rejects these changes to files the agents may not "
                     "touch (tests from write_tests, test configuration, INVARIANTS.md). **Approve accepts exactly "
                     "this content** (in VS Code: Accept these changes) and re-runs the gate; any later edit of these files fails it again. To have "
                     "them restored instead, say so in the comment.\n\n" + protected)
    if suppressions:
        parts.append("## New suppressions\n\nimplement or fix silenced a scanner, a type check or a test instead of "
                     "fixing the cause. **Approve accepts exactly these lines** and re-runs the gate. To have the "
                     "cause fixed instead, say so in the comment.\n\n" + suppressions)
    questions = state.get("review_questions") or []
    if questions:
        parts.append("## Questions from the reviewer\n\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)))
    needs = state.get("fixer_requests") or []
    if needs:
        parts.append("## What the fixer needs from you\n\n" + "\n".join(f"{i}. {n}" for i, n in enumerate(needs, 1)))
    if reason in ("needs_human", "no_changes") and state.get("implement_summary"):
        parts.append("## The fixer's last reply\n\n" + state["implement_summary"])
    rows = ["| # | Step | Result | What happened |", "|---|---|---|---|"]
    n = 0
    for h in history:
        kind = h.get("kind")
        if kind == "check":
            result = "PASS" if h.get("passed") else f"FAIL · {h['open']} open"
            rows.append(f"|  | {h['check']} | {result} | {h.get('note', '')} |")
        elif kind == "fix":
            n += 1
            changed = f" ({h['changed']})" if h.get("changed") else ""
            rows.append(f"| {n} | fix | | {h.get('summary', '')}{changed} |")
        elif kind == "human":
            rows.append(f"|  | you | {h.get('decision', '')} | {h.get('note', '')} |")
    parts.append("## Rounds\n\n" + "\n".join(r.replace("\n", " ") for r in rows))
    for check in ("review", "gate"):
        counts = [str(h["open"]) for h in history if h.get("kind") == "check" and h.get("check") == check]
        if len(counts) > 1:
            parts.append(f"**Open {CHECK_NAMES[check]} problems per round:** {' → '.join(counts)}")
    check = state.get("fix_target", "review")
    latest = state.get("review_findings") if check == "review" else state.get("gate_report")
    if latest:
        if answered_since_check(history):
            # The human already answered after this check: show what it found, not its questions again.
            parts.append(f"## Findings of the last {CHECK_NAMES.get(check, check)} (before your answers above)\n\n"
                         + without_questions(latest))
        else:
            parts.append("## Latest findings\n\n" + latest)
    return "\n\n".join(parts)


def answered_since_check(history: list[dict]) -> bool:
    """The human decided at approve_fix after the last review or gate."""
    for h in reversed(history):
        if h.get("kind") == "check":
            return False
        if h.get("kind") == "human":
            return True
    return False


def record_check(state: dict, rt: Runtime, check: str, passed: bool, problems: int, note: str,
                 questions: list[str] | None = None) -> dict:
    """The state update every review and gate adds: the round in the history and, on FAIL,
    whether the human must decide before the next fix."""
    history = [*(state.get("fix_history") or []), {"kind": "check", "check": check, "passed": passed, "open": problems,
                                                    "note": note}]
    update: dict[str, Any] = {"fix_history": history, "review_questions": questions or [], "escalation": ""}
    if not passed:
        update["escalation"] = escalation(state, rt, history, check, questions or [])
    return update


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
                  scope=scope_text(rt), tests=tests_text(rt), scanners=SCANNERS)
    reply = call(rt, "implement", text, WRITE)
    return {"implement_session": reply.session_id or "", "implement_summary": reply.text.strip()}


@step("review")
def review(state: dict, rt: Runtime) -> dict:
    # Independent: a new session that did not write the code. After a fix it re-checks the
    # previous findings by their IDs and looks for regressions, instead of starting over.
    previous = state.get("review_findings")
    if previous:
        text = prompt("rereview", prompt=state["prompt"], spec=spec(state), previous=previous,
                      fixer=state.get("implement_summary", "(none)"), base=rt.base_commit,
                      since=(state.get("commits") or {}).get("review", rt.base_commit), scope=scope_text(rt),
                      tests=tests_text(rt))
    else:
        text = prompt("review", prompt=state["prompt"], spec=spec(state), earlier=earlier(state, "tests_summary", "implement_summary"),
                      base=rt.base_commit, scope=scope_text(rt), tests=tests_text(rt))
    reply = call(rt, "review", text, READ_ONLY)
    passed = verdict(reply.text)
    problems = 0 if passed else open_findings(reply.text)
    questions = [] if passed else review_questions(reply.text)
    note = ("all findings fixed" if previous else "") if passed else first_open_finding(reply.text)
    return {
        "review_passed": passed,
        "review_findings": "" if passed else reply.text.strip(),
        "fix_target": "review",
        "fix_reason": "review",
        **record_check(state, rt, "review", passed, problems, note, questions),
        STATUS_KEY: "succeeded" if passed else "failed",
    }


@step("fix")
def fix(state: dict, rt: Runtime) -> dict:
    # No limit here: review and gate decide whether the human is asked first (approve_fix).
    loops = state.get("fix_loops", 0)
    reason = state.get("fix_reason", "review")
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
    human = state.get("fix_note") or ""
    note = section("From the human (answers and notes; they take precedence over the findings)", human)
    before = head(Path(rt.cwd))
    text = prompt("fix", problem=problem, context=context, note=note, scope=scope_text(rt), tests=tests_text(rt),
                  scanners=SCANNERS)
    reply = call(rt, "fix", text, WRITE, resume=session)
    changed = shortstat(Path(rt.cwd), before)
    history = [*(state.get("fix_history") or []), {"kind": "fix", "reason": reason, "summary": first_line(reply.text),
                                                    "changed": changed}]
    needs = fixer_needs(reply.text)
    # A fixer that is blocked or changed nothing goes straight to the human: another review
    # round would only re-find the same problems (and a new reviewer words them differently).
    # Except right after the human answered: then changing nothing is the right fix (the answer
    # settled it), and only a new check can tell; asking the human again would loop
    # approve_fix → fix → approve_fix forever (run_20261120161021_60bbf3).
    escalate = "needs_human" if needs else ("no_changes" if changed == NO_CHANGES and not human.strip() else "")
    update: dict[str, Any] = {"fix_loops": loops + 1, "implement_summary": reply.text.strip(), "fix_history": history,
                              "fix_note": "", "fixer_requests": needs, "escalation": escalate}
    if reply.session_id:
        update["implement_session"] = reply.session_id
    return update


@step("gate")
def gate(state: dict, rt: Runtime) -> dict:
    result = gate_checks.run_gate(rt.cwd, rt.base_commit, rt.options.get("gate"),
                                  tests_base=(state.get("commits") or {}).get("write_tests"),
                                  accepted=state.get("protected_accepted"),
                                  accepted_suppressions=state.get("suppressions_accepted"))
    return {
        "gate_passed": result["passed"],
        "gate_report": gate_checks.report(result),
        "fix_target": "gate",
        "fix_reason": "gate",
        **record_check(state, rt, "gate", result["passed"], 0 if result["passed"] else gate_problems(result),
                       ", ".join(c["name"] for c in result["checks"] if not c["passed"])),
        GATE_KEY: result,
        STATUS_KEY: "succeeded" if result["passed"] else "failed",
    }


PROTECTED_DIFF_LIMIT = 8000


def protected_pending(state: dict, rt: Runtime) -> tuple[dict[str, str], str]:
    """Protected files the last gate rejected and the human has not accepted: path →
    content_id, and their diff since write_tests (what the human accepts with Approve)."""
    tests_base = (state.get("commits") or {}).get("write_tests")
    if state.get("fix_target") != "gate" or not tests_base:
        return {}, ""
    cwd = Path(rt.cwd)
    cfg = gate_checks.settings(cwd, rt.base_commit, rt.options.get("gate"))
    changes = gate_checks.protected_changes(cwd, rt.base_commit, tests_base, cfg, state.get("protected_accepted"))
    paths = list(dict.fromkeys(p for p, _ in changes))
    if not paths:
        return {}, ""
    diff = subprocess.run(["git", "diff", "--no-color", tests_base, "--", *paths], cwd=cwd, capture_output=True,
                          text=True).stdout
    if len(diff) > PROTECTED_DIFF_LIMIT:
        diff = diff[:PROTECTED_DIFF_LIMIT] + f"\n… (cut; the whole diff: git diff {tests_base[:12]} -- {' '.join(paths)})"
    listing = "\n".join(f"- `{label}`" for _, label in changes)
    return {p: gate_checks.content_id(cwd, p) for p in paths}, f"{listing}\n\n```diff\n{diff.strip()}\n```"


def suppressions_pending(state: dict, rt: Runtime) -> tuple[list[str], str]:
    """Suppression markers implement/fix added that the gate rejects and the human has not
    accepted: their keys and a list for the report."""
    tests_base = (state.get("commits") or {}).get("write_tests") or rt.base_commit
    if state.get("fix_target") != "gate":
        return [], ""
    scope = rt.options.get("gate", {}).get("scope", gate_checks.DEFAULTS["scope"])
    found = gate_checks.new_suppressions(Path(rt.cwd), tests_base, scope, state.get("suppressions_accepted"))
    if not found:
        return [], ""
    keys = list(dict.fromkeys(gate_checks.suppression_key(p, ln) for p, ln in found))
    return keys, "\n".join(f"- `{p}`: `{ln.strip()}`" for p, ln in found)


@step("approve_fix")
def approve_fix(state: dict, rt: Runtime) -> dict:
    """The fixes stopped making progress, hit their cap, or the reviewer has a question: the
    human sees every round and decides. Continue (Approve) grants more fixes; a comment goes to
    the fixer (and the reviewer) as the human's answer; Reject stops the run."""
    reason = state.get("escalation", "")
    loops = state.get("fix_loops", 0)
    message = {
        "questions": "The reviewer needs your answer before the next fix. Type it and press Enter "
                     "(Request changes), Approve to let the fixer decide, or Reject to stop.",
        "stalled": f"{loops} fixes so far and the last {STALL_ROUNDS} did not reduce the open problems. "
                   f"Approve to continue ({EXTRA_FIXES} more fixes), type a hint for the fixer and press Enter, "
                   "or Reject to stop the run.",
        "limit": f"{loops} fixes so far: the cap is reached. Approve to continue ({EXTRA_FIXES} more fixes), "
                 "type a hint for the fixer and press Enter, or Reject to stop the run.",
        "needs_human": "The fixer is blocked on something only you can do. Do it, then type what you did and "
                       "press Enter (the fixer reads it first), Approve (in VS Code: Re-run the check) to re-run the "
                       f"{CHECK_NAMES.get(state.get('fix_target', 'review'), 'check')} as it is, or Reject to stop the run.",
        "no_changes": f"The last fix changed nothing. Approve (in VS Code: Re-run the check) to re-run the {CHECK_NAMES.get(state.get('fix_target', 'review'), 'check')} "
                      "on the current change, type a hint for the fixer and press Enter, or Reject to stop the run.",
    }.get(reason, "Approve to continue fixing, type a hint and press Enter, or Reject to stop.")
    pending, protected = protected_pending(state, rt)
    silenced, suppressions = suppressions_pending(state, rt)
    waiting = sorted([*pending, *silenced])
    if waiting:
        message = ("The gate rejects changes only you can accept (protected files or new suppressions, see the "
                   "report). Approve (in VS Code: **Accept these changes**) accepts exactly these and re-runs the "
                   "gate. A comment does not accept them: it goes to the fixer (e.g. restore them, fix the cause). "
                   "Reject stops the run.")
    commented_before = bool(waiting) and state.get("pending_commented") == waiting
    answer = rt.ask_human("approve_fix", "plan", message,
                          plan=fix_report(state, protected, suppressions, commented_before))
    decision = answer["decision"]
    if decision == "reject":
        return {"decision": decision, "outcome": "rejected", "escalation": "",
                "failure": f"stopped by the human after {loops} fixes", STATUS_KEY: "failed"}
    comment = (answer.get("comment") or "").strip()
    if not comment and reason == "questions":
        comment = ("The human approved without answering the reviewer's questions. Decide them yourself "
                   "(the option the reviewer recommended) and say so in your reply.")
    accept = decision == "approve" and bool(waiting)
    # Approve after a fix that changed nothing or that only the human could unblock: nothing new
    # for the fixer, so check the change again (accepted protected files: the gate again).
    recheck = accept or (reason in ("no_changes", "needs_human") and not comment)
    check = state.get("fix_target", "review")
    note = first_line(comment) if comment else (f"re-run the {check}" if recheck else f"+{EXTRA_FIXES} fixes")
    if accept:
        note = "accepted " + ", ".join([*pending, *(k.split("\t", 1)[0] + " (suppression)" for k in silenced)])
    history = [*(state.get("fix_history") or []), {"kind": "human", "decision": "continue", "note": note}]
    update: dict[str, Any] = {
        "decision": decision,
        "escalation": "",
        "recheck": recheck,
        "fix_cap": loops + EXTRA_FIXES,
        "fix_history": history,
        "fix_stall_from": len(history),
        "fix_note": comment,
        "fixer_requests": [],
        "review_questions": [],  # answered (or left to the fixer): never shown again
        # A comment while something waits for acceptance: the next screen says that it is still waiting.
        "pending_commented": waiting if waiting and not accept else [],
        STATUS_KEY: "succeeded",
    }
    if accept:
        update["protected_accepted"] = {**(state.get("protected_accepted") or {}), **pending}
        update["suppressions_accepted"] = [*(state.get("suppressions_accepted") or []), *silenced]
        accepted = [*pending, *(k.replace("\t", ": ") for k in silenced)]
        update["clarifications"] = [*(state.get("clarifications") or []),
                                    "The human accepted these changes the gate rejects (final; do not undo them): "
                                    + "; ".join(accepted)]
    if comment:
        # Every answer is kept for the rest of the run (spec()), so the next reviewer and fixer
        # see it too and nobody asks the same thing again.
        who, asked = {"questions": ("Reviewer asked", state.get("review_questions")),
                      "needs_human": ("Fixer asked", state.get("fixer_requests"))}.get(reason, ("", None))
        if asked:
            context = f"{who}:\n" + "\n".join(f"- {q}" for q in asked)
        else:
            context = f"During the fix rounds ({WHY.get(reason, 'a note for the fixer')}):"
        update["clarifications"] = [*(update.get("clarifications") or state.get("clarifications") or []),
                                    f"{context}\n\nHuman:\n{comment}"]
    return update


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
