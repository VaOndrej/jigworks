"""Node functions of the sample package. Fixture only: they do not call an agent."""

from langgraph.types import interrupt


def plan(state):
    return {"plan": f"Plan for: {state.get('prompt', '')}"}


def approve_plan(state):
    return {"decision": interrupt({"stage": "plan", "plan": state.get("plan", "")})["decision"]}


def write_tests(state):
    return {}


def implement(state):
    return {}


def review(state):
    return {"review_passed": True, "fix_target": "review"}


def fix(state):
    return {"fix_loops": state.get("fix_loops", 0) + 1}


def gate(state):
    return {"gate_passed": True, "fix_target": "gate"}


def approve_pr(state):
    return {"decision": interrupt({"stage": "pr"})["decision"], "fix_target": "gate"}


def open_pr(state):
    return {"pr_url": "https://github.com/example/sample-repo/pull/1"}


def summary(state):
    return {}
