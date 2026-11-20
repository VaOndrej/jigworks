"""tiny: work → [review] → finish. Request changes loops back to work; reject ends the run.
Used by the extension's integration test with the fake adapter (no tokens, no gate)."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


def merge(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class State(TypedDict, total=False):
    commits: Annotated[dict[str, str], merge]
    prompt: str
    comment: str
    decision: str
    outcome: str


def rt(config):
    return config["configurable"]["jigworks"]


def work(state: State, config) -> State:
    r = rt(config)
    r.enter("work")
    extra = f"\nReviewer: {state['comment']}" if state.get("comment") else ""
    reply = r.agent("work", f"Do this: {state['prompt']}{extra}", tools=("Read", "Edit", "Write"))
    if reply.status != "succeeded":
        raise RuntimeError("agent failed")
    sha = r.exit("work", "succeeded", update={})
    return {"commits": {"work": sha}}


def review(state: State, config) -> State:
    r = rt(config)
    r.enter("review")
    answer = r.ask_human("review", "pr", "Review the change.")
    decision = answer["decision"]
    status = {"approve": "succeeded", "request_changes": "cancelled"}.get(decision, "failed")
    update: State = {"decision": decision, "comment": answer.get("comment", "")}
    if decision == "reject":
        update["outcome"] = "rejected"
    sha = r.exit("review", status, update=dict(update))
    return {**update, "commits": {"review": sha}}


def finish(state: State, config) -> State:
    r = rt(config)
    r.enter("finish")
    sha = r.exit("finish", "succeeded", update={"outcome": "succeeded"})
    return {"outcome": "succeeded", "commits": {"finish": sha}}


def after_review(state: State) -> str:
    return {"approve": "finish", "request_changes": "work"}.get(state.get("decision", ""), END)


def build_graph() -> StateGraph:
    g = StateGraph(State)
    g.add_node("work", work)
    g.add_node("review", review)
    g.add_node("finish", finish)
    g.add_edge(START, "work")
    g.add_edge("work", "review")
    g.add_conditional_edges("review", after_review, ["finish", "work", END])
    g.add_edge("finish", END)
    return g
