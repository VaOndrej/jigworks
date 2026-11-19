"""The agent interface (design.md §7): `run(prompt, cwd, options) → result + events`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from ..events import NodeContext

AgentStatus = Literal["succeeded", "failed", "usage_limit"]


@dataclass(frozen=True)
class AgentOptions:
    """Options of one agent call.

    `model` has no default on purpose: it always comes from the workflow release
    (`[models]` in workflow.toml), never from the user or the adapter.
    """

    model: str
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    permission_mode: str | None = None
    max_turns: int | None = None
    resume_session_id: str | None = None
    setting_sources: str | None = "project"
    include_thinking: bool = False
    timeout_s: float | None = None

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError("AgentOptions.model is required and comes from the workflow release")
        if self.permission_mode == "plan":
            # docs/spikes/claude-stream-json.md §6: non-deterministic and expensive.
            raise ValueError("plan mode is not used by the runner; restrict tools with allowed_tools")


@dataclass
class AgentResult:
    status: AgentStatus
    session_id: str | None = None
    text: str = ""
    usage: list[dict[str, Any]] = field(default_factory=list)
    usage_limit: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    denials: list[dict[str, Any]] = field(default_factory=list)
    exit_code: int | None = None
    num_turns: int | None = None
    cli_cost_usd: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"


class Agent(Protocol):
    name: str

    def run(self, prompt: str, cwd: Path, options: AgentOptions, ctx: NodeContext) -> AgentResult: ...
