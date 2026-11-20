"""feature-development (design.md §9).

START → triage   (keyword "brainstorm" in the prompt, or the triage agent judges the size)
      quick      → plan
      brainstorm → brainstorm ⇄ [approve_brainstorm]   (rounds of questions, same session,
                   until the agent writes the design; round limit) → plan (from the design)
      plan ⇄ [approve_plan]   (questions / request changes → plan, same session; round limit)
      [approve_plan] approve → write_tests (separate session, from the spec) → implement
      → review (independent session; after a fix it re-checks the earlier findings and regressions)
            review FAIL → fix → review        (while the open findings shrink)
            review PASS → gate (tests, property tests, secret scan, security scan, scope)
            gate FAIL → fix → gate
            no progress for 2 fixes, the fix cap, or a reviewer question → [approve_fix]
                  approve / request changes (a note or the answers) → fix, with more fixes
                  reject                                            → END
            gate PASS → [approve_pr]
                  approve         → open_pr → summary → END
                  request changes → fix → gate → [approve_pr]   (follow-up prompt)
                  reject          → END
      [approve_plan] reject → END · planning or brainstorming round limit reached → END (run failed)

The runner injects the runtime (agent, git, events) through the LangGraph config; this
package never imports the runner, so it runs from a release bundle as-is.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .steps import nodes


def merge(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class State(TypedDict, total=False):
    commits: Annotated[dict[str, str], merge]  # node → git commit of its last snapshot
    prompt: str
    route: Literal["quick", "brainstorm"]
    route_reason: str
    brainstorm: str  # the brainstormer's latest reply: questions or the design
    brainstorm_session: str  # resumed on every brainstorming round
    brainstorm_feedback: str  # the human's latest answer, consumed by brainstorm
    brainstorm_rounds: int  # brainstormer calls so far (limit MAX_BRAINSTORM_ROUNDS)
    brainstorm_log: list[str]  # the brainstorming conversation
    design: str  # the approved design; the plan is made from it
    plan: str
    plan_session: str  # the planner's agent session, resumed on every planning round
    plan_feedback: str  # the human's latest answer or comment on the plan, consumed by plan
    plan_rounds: int  # planner calls so far (limit MAX_PLAN_ROUNDS)
    clarifications: list[str]  # the planning conversation, passed on with the plan
    tests_summary: str
    implement_session: str
    implement_summary: str  # the implementer's (or the last fixer's) report, for the reviewer
    review_passed: bool
    review_findings: str
    gate_passed: bool
    gate_report: str
    decision: Literal["approve", "request_changes", "reject"]
    comment: str
    fix_target: Literal["review", "gate"]
    fix_reason: Literal["review", "gate", "request_changes"]
    fix_loops: int
    fix_history: list[dict]  # every check and fix round, for the report the human sees at approve_fix
    fix_cap: int  # fixes allowed before the human is asked (raised by Continue at approve_fix)
    fix_stall_from: int  # index in fix_history where stall detection starts (after a Continue)
    escalation: str  # why the human is asked: questions | stalled | limit | needs_human | no_changes ("" = keep fixing)
    review_questions: list[str]  # questions the reviewer could not decide without the human
    fixer_requests: list[str]  # NEEDS HUMAN lines of the last fix: what only the human can do
    fix_note: str  # the human's note or answers for the next fix, consumed by fix
    outcome: Literal["succeeded", "failed", "rejected"]
    failure: str
    pr_url: str
    summary: str


def after_triage(state: State) -> Literal["plan", "brainstorm"]:
    return "brainstorm" if state.get("route") == "brainstorm" else "plan"


def after_brainstorm(state: State) -> Literal["approve_brainstorm", "__end__"]:
    return END if state.get("outcome") == "failed" else "approve_brainstorm"


def after_brainstorm_approval(state: State) -> Literal["brainstorm", "plan", "__end__"]:
    if state.get("decision") == "reject":
        return END
    return "brainstorm" if state.get("brainstorm_feedback") else "plan"


def after_plan(state: State) -> Literal["approve_plan", "__end__"]:
    return END if state.get("outcome") == "failed" else "approve_plan"


def after_plan_approval(state: State) -> Literal["plan", "write_tests", "__end__"]:
    if state.get("decision") == "reject":
        return END
    # A comment, an answer, or an approval of open questions: another planning round.
    return "plan" if state.get("plan_feedback") else "write_tests"


def after_review(state: State) -> Literal["fix", "gate", "approve_fix"]:
    if state.get("review_passed"):
        return "gate"
    return "approve_fix" if state.get("escalation") else "fix"


def after_gate(state: State) -> Literal["fix", "approve_pr", "approve_fix"]:
    if state.get("gate_passed"):
        return "approve_pr"
    return "approve_fix" if state.get("escalation") else "fix"


def after_fix_approval(state: State) -> Literal["fix", "__end__"]:
    return END if state.get("decision") == "reject" else "fix"


def after_fix(state: State) -> Literal["review", "gate", "approve_fix", "__end__"]:
    if state.get("outcome") == "failed":
        return END
    if state.get("escalation"):  # the fixer is blocked or changed nothing: ask before the next check
        return "approve_fix"
    return state.get("fix_target", "review")


def after_pr_review(state: State) -> Literal["open_pr", "fix", "__end__"]:
    decision = state.get("decision")
    if decision == "approve":
        return "open_pr"
    if decision == "request_changes":
        return "fix"
    return END


def build_graph() -> StateGraph:
    g = StateGraph(State)
    g.add_node("triage", nodes.triage)
    g.add_node("brainstorm", nodes.brainstorm)
    g.add_node("approve_brainstorm", nodes.approve_brainstorm)
    g.add_node("plan", nodes.plan)
    g.add_node("approve_plan", nodes.approve_plan)
    g.add_node("write_tests", nodes.write_tests)
    g.add_node("implement", nodes.implement)
    g.add_node("review", nodes.review)
    g.add_node("fix", nodes.fix)
    g.add_node("gate", nodes.gate)
    g.add_node("approve_fix", nodes.approve_fix)
    g.add_node("approve_pr", nodes.approve_pr)
    g.add_node("open_pr", nodes.open_pr)
    g.add_node("summary", nodes.summary)

    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", after_triage)
    g.add_conditional_edges("brainstorm", after_brainstorm)
    g.add_conditional_edges("approve_brainstorm", after_brainstorm_approval)
    g.add_conditional_edges("plan", after_plan)
    g.add_conditional_edges("approve_plan", after_plan_approval)
    g.add_edge("write_tests", "implement")
    g.add_edge("implement", "review")
    g.add_conditional_edges("review", after_review)
    g.add_conditional_edges("fix", after_fix)
    g.add_conditional_edges("gate", after_gate)
    g.add_conditional_edges("approve_fix", after_fix_approval)
    g.add_conditional_edges("approve_pr", after_pr_review)
    g.add_edge("open_pr", "summary")
    g.add_edge("summary", END)
    return g
