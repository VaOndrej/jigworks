"""Deterministic fake agent for tests and token-free demos (`adapter: fake`).

A script maps node → list of `FakeStep`s (or callables returning one), consumed in order per
node; the last one repeats. A step may write or delete files in the worktree, so the real
gate, git snapshots and review loop run against real changes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from ..events import NodeContext
from .base import AgentOptions, AgentResult


@dataclass
class FakeStep:
    text: str = "ok"
    files: dict[str, str | None] = field(default_factory=dict)  # path → content, None = delete
    status: str = "succeeded"  # succeeded | failed | usage_limit
    edit: Callable[[Path], None] | None = None  # arbitrary change to the worktree
    replace: list[tuple[str, str, str]] = field(default_factory=list)  # (path, old, new) text edits
    sleep: float = 0.0  # seconds, to let tests kill the runner mid-node

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FakeStep:
        return cls(
            text=data.get("text", "ok"),
            files=data.get("files", {}),
            status=data.get("status", "succeeded"),
            replace=[tuple(r) for r in data.get("replace", [])],
            sleep=float(data.get("sleep", 0)),
        )


def load_script(path: str | Path) -> dict[str, list[FakeStep]]:
    """A fake script as JSON: {"node": [{"text": …, "files": {…}, "replace": [[p, old, new]], "sleep": s}, …]}."""
    import json

    raw = json.loads(Path(path).read_text())
    return {node: [FakeStep.from_json(s) for s in steps] for node, steps in raw.items()}


StepLike = Union[FakeStep, Callable[[str, Path], FakeStep]]


@dataclass
class FakeCall:
    node: str
    attempt: int
    prompt: str
    options: AgentOptions
    session_id: str


class FakeAdapter:
    name = "fake"

    def __init__(self, script: dict[str, list[StepLike]] | None = None) -> None:
        self.script = script or {}
        self.calls: list[FakeCall] = []
        self._count: dict[str, int] = {}

    def _next(self, node: str, attempt: int, prompt: str, cwd: Path) -> FakeStep:
        # Indexed by the node's attempt number (from the event log), not by an in-process counter,
        # so a resumed run in a new process continues the script where it was.
        steps = self.script.get(node) or [FakeStep()]
        step = steps[min(max(attempt, 1) - 1, len(steps) - 1)]
        return step(prompt, cwd) if callable(step) and not isinstance(step, FakeStep) else step

    def run(self, prompt: str, cwd: Path, options: AgentOptions, ctx: NodeContext) -> AgentResult:
        step = self._next(ctx.node, ctx.attempt, prompt, cwd)
        if step.sleep:
            time.sleep(step.sleep)
        session = options.resume_session_id or f"fake-{ctx.sink.run_id}-{ctx.node}-{len(self.calls)}"
        self.calls.append(FakeCall(ctx.node, ctx.attempt, prompt, options, session))

        if step.status == "usage_limit":
            limit = {"status": "rejected", "rateLimitType": "five_hour", "resetsAt": "2026-11-20T05:00:00Z", "paused": True}
            ctx.emit("usage_limit", usageLimit=limit, runStatus="paused_usage_limit")
            error = {"code": "usage_limit", "message": "Claude usage limit reached; resumes after 2026-11-20T05:00:00Z.", "retryable": True}
            ctx.emit("error", error=error)
            return AgentResult(status="usage_limit", session_id=session, usage_limit=limit, error=error, exit_code=1)

        for rel, content in step.files.items():
            path = cwd / rel
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
        for rel, old, new in step.replace:
            path = cwd / rel
            path.write_text(path.read_text().replace(old, new))
        if step.edit:
            step.edit(cwd)

        ctx.emit("agent_output", agentOutput={"block": "text", "sessionId": session, "text": step.text})
        usage: dict[str, Any] = {
            "runId": ctx.sink.run_id, "node": ctx.node, "attempt": ctx.attempt, "model": options.model,
            "adapter": "fake", "input": 10, "output": 20, "cache_write": 0, "cache_read": 0,
            "sessionId": session, "at": ctx.sink.now(),
        }
        ctx.emit("usage", model=options.model, usage=usage)
        if step.status != "succeeded":
            error = {"code": "agent_failed", "message": f"fake agent failed at {ctx.node}", "retryable": False}
            ctx.emit("error", error=error)
            return AgentResult(status="failed", session_id=session, text=step.text, usage=[usage], error=error, exit_code=1)
        return AgentResult(status="succeeded", session_id=session, text=step.text, usage=[usage], exit_code=0)
