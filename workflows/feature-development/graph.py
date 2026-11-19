"""feature-development (design.md §9).

START → plan → [approve_plan] → write_tests (separate session, from the spec) → implement
      → review (independent session)
            review FAIL → fix → review        (fix loop limit)
            review PASS → gate (tests, property tests, secret scan, security scan, scope)
            gate FAIL → fix → gate
            gate PASS → [approve_pr]
                  approve         → open_pr → summary → END
                  request changes → fix → gate → [approve_pr]   (follow-up prompt)
                  reject          → END
      [approve_plan] reject → END · fix loop limit reached → END (run failed)

The runner injects the runtime (agent, git, events) through the LangGraph config; this
package never imports the runner, so it runs from a release bundle as-is.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .steps import nodes


class State(TypedDict, total=False):
    prompt: str
    plan: str
    tests_summary: str
    implement_session: str
    review_passed: bool
    review_findings: str
    gate_passed: bool
    gate_report: str
    decision: Literal["approve", "request_changes", "reject"]
    comment: str
    fix_target: Literal["review", "gate"]
    fix_reason: Literal["review", "gate", "request_changes"]
    fix_loops: int
    outcome: Literal["succeeded", "failed", "rejected"]
    failure: str
    pr_url: str
    summary: str


def after_plan_approval(state: State) -> Literal["write_tests", "__end__"]:
    return END if state.get("decision") == "reject" else "write_tests"


def after_review(state: State) -> Literal["fix", "gate"]:
    return "gate" if state.get("review_passed") else "fix"


def after_gate(state: State) -> Literal["fix", "approve_pr"]:
    return "approve_pr" if state.get("gate_passed") else "fix"


def after_fix(state: State) -> Literal["review", "gate", "__end__"]:
    if state.get("outcome") == "failed":
        return END
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
    g.add_node("plan", nodes.plan)
    g.add_node("approve_plan", nodes.approve_plan)
    g.add_node("write_tests", nodes.write_tests)
    g.add_node("implement", nodes.implement)
    g.add_node("review", nodes.review)
    g.add_node("fix", nodes.fix)
    g.add_node("gate", nodes.gate)
    g.add_node("approve_pr", nodes.approve_pr)
    g.add_node("open_pr", nodes.open_pr)
    g.add_node("summary", nodes.summary)

    g.add_edge(START, "plan")
    g.add_edge("plan", "approve_plan")
    g.add_conditional_edges("approve_plan", after_plan_approval)
    g.add_edge("write_tests", "implement")
    g.add_edge("implement", "review")
    g.add_conditional_edges("review", after_review)
    g.add_conditional_edges("fix", after_fix)
    g.add_conditional_edges("gate", after_gate)
    g.add_conditional_edges("approve_pr", after_pr_review)
    g.add_edge("open_pr", "summary")
    g.add_edge("summary", END)
    return g
