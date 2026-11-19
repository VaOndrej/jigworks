"""The contract between this workflow package and the Jigworks runner.

The runner passes an object implementing `Runtime` as `config["configurable"]["jigworks"]`.
The package only uses the methods below, so it does not import the runner and runs from a
release bundle unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig


class AgentReply(Protocol):
    status: str  # succeeded | failed | usage_limit (usage_limit never reaches a node: the runner pauses)
    text: str
    session_id: str | None


class Runtime(Protocol):
    cwd: Path              # the run's git worktree
    base_commit: str       # commit the run started from (diffs are against it)
    options: dict[str, Any]  # runner-side overrides, e.g. {"gate": {...}, "max_fix_loops": 3}

    def enter(self, node: str) -> None: ...
    def exit(self, node: str, status: str, *, gate: dict | None = None) -> None: ...
    def agent(self, node: str, prompt: str, *, tools: Sequence[str], resume: str | None = None) -> AgentReply: ...
    def ask_human(self, node: str, stage: str, message: str, **payload: Any) -> dict[str, Any]: ...
    def open_pr(self, title: str, body: str) -> str: ...


def runtime(config: RunnableConfig) -> Runtime:
    try:
        return config["configurable"]["jigworks"]
    except (KeyError, TypeError):
        raise RuntimeError("feature-development must be run by the Jigworks runner (no runtime in config)") from None


STATUS_KEY = "_node_status"
GATE_KEY = "_gate"


def step(name: str) -> Callable:
    """Wrap a node: report running / finished to the runner, which also takes the git snapshot.

    A node returns its state update; it may set `_node_status` (default `succeeded`) and `_gate`
    (a GateResultPayload); both are removed before LangGraph sees the update."""

    def deco(fn: Callable[[dict, Runtime], dict]) -> Callable:
        # No functools.wraps: LangGraph inspects the signature for `config`, and wraps would
        # expose the inner (state, rt) signature through __wrapped__.
        def wrapper(state: dict, config: RunnableConfig) -> dict:
            rt = runtime(config)
            rt.enter(name)
            update = dict(fn(state, rt) or {})
            status = update.pop(STATUS_KEY, "succeeded")
            gate = update.pop(GATE_KEY, None)
            rt.exit(name, status, gate=gate)
            return update

        wrapper.__name__ = wrapper.__qualname__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return deco
