"""Running a workflow package: LangGraph + checkpoints + one git commit per node + events.

`WorkflowRun` drives the compiled graph until it ends or stops at an `interrupt`, and
implements the runtime the package's nodes call (`steps/runtime.py` in the package):
agent calls with the release's models, human interrupts, git snapshots, PR opening.

Everything the run knows is in its event log (`EventSink`) and its LangGraph checkpoint;
`Ledger` is rebuilt from the log, so a new process can resume a run (T06).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from . import __version__ as RUNNER_VERSION
from . import git
from .adapters.base import Agent, AgentOptions, AgentResult
from .events import EventSink, NodeContext
from .ledger import Ledger
from .package import WorkflowPackage

PrOpener = Callable[["WorkflowRun", str, str], str]

# Deny rules beat allow rules, including allow rules in the target repo's own project settings
# (`--setting-sources project` loads them). The runner owns git history, pushes and the PR.
DENIED_TOOLS = (
    "Bash(git push:*)", "Bash(git commit:*)", "Bash(git reset:*)", "Bash(git checkout:*)",
    "Bash(gh:*)", "Bash(vercel:*)", "Bash(curl:*)", "WebFetch", "WebSearch",
)


class UsageLimitPaused(Exception):
    """Raised inside a node when the agent hit the subscription limit; the run pauses."""

    def __init__(self, result: AgentResult) -> None:
        super().__init__("usage limit reached")
        self.result = result


class RunStateError(RuntimeError):
    pass


@dataclass
class Outcome:
    status: str  # waiting_human | paused_usage_limit | succeeded | failed | rejected
    interrupt: dict[str, Any] | None = None


def default_pr_opener(remote: str = "origin", base: str = "main", gh: bool = True) -> PrOpener:
    """Push `demo/<runId>` and open a PR with `gh` when the remote is on GitHub; for any other
    remote (e.g. a local bare repo in the live proof) the pushed branch is the result."""

    def open_pr(run: WorkflowRun, title: str, body: str) -> str:
        branch = f"demo/{run.run_id}"
        git.git(run.cwd, "push", "-q", remote, f"HEAD:refs/heads/{branch}")
        named = remote in git.git(run.cwd, "remote").split()
        url = git.git(run.cwd, "remote", "get-url", remote).strip() if named else remote
        if gh and "github.com" in url:
            import subprocess

            proc = subprocess.run(
                ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body],
                cwd=run.cwd, capture_output=True, text=True, check=True,
            )
            return proc.stdout.strip().splitlines()[-1]
        return f"{url}#{branch}"

    return open_pr


class RunRuntime:
    """What the package's nodes see as `config["configurable"]["jigworks"]`."""

    def __init__(self, run: WorkflowRun) -> None:
        self.run = run
        self.cwd = run.cwd
        self.base_commit = run.base_commit
        self.options = run.options
        self.resuming_node: str | None = None
        # The release's model per (node, attempt) that called an agent; reported on the node's
        # finish event. modelUsage may list background models first, so usage is not the source.
        self.node_models: dict[tuple[str, int], str] = {}

    # -- node lifecycle ---------------------------------------------------------------------

    def enter(self, node: str) -> None:
        led = self.run.ledger
        if self.resuming_node == node:
            return  # re-entry after an interrupt: same attempt, already reported as running
        attempt = led.attempts.get(node, 0) + 1
        self.run.emit_node(node, attempt, "running")

    def _attempt(self, node: str) -> int:
        return self.run.ledger.attempts.get(node, 1)

    def exit(self, node: str, status: str, *, gate: dict | None = None, update: dict | None = None) -> str:
        attempt = self._attempt(node)
        if self.resuming_node == node:
            self.resuming_node = None
        if gate is not None:
            self.run.sink.emit("gate_result", node=node, attempt=attempt, gateResult=gate)
        sha, files = git.commit_all(self.cwd, f"jigworks: {node} (attempt {attempt}) [{self.run.run_id}]", self.run.author_email)
        snapshot: dict[str, Any] = {"commit": sha}
        if files:
            snapshot["changedFiles"] = files
        # Journal first, then the event: if the process dies after this point, resume applies the
        # journaled update instead of running the node again (design.md §11.1).
        self.run.record_node_result(
            {"node": node, "attempt": attempt, "commit": sha, "update": {**(update or {}), "commits": {node: sha}}}
        )
        self.run.emit_node(node, attempt, status, snapshot=snapshot, model=self.node_models.get((node, attempt)))
        if os.environ.get("JIGWORKS_TEST_CRASH_AFTER_COMMIT") == node:
            os._exit(137)  # test hook: die after the commit, before LangGraph writes its checkpoint
        return sha

    # -- services ---------------------------------------------------------------------------

    def agent(self, node: str, prompt: str, *, tools: Sequence[str], resume: str | None = None) -> AgentResult:
        allowed = list(tools)
        declared = self.run.package.allowed_tools()
        if declared is not None:
            allowed = [t for t in allowed if t in declared]  # never more than the release declares
        options = AgentOptions(
            model=self.run.package.model_for(node),
            effort=self.run.package.effort_for(node),
            plugin_dirs=self.run.package.plugin_dirs(),
            allowed_tools=tuple(allowed),
            disallowed_tools=tuple(self.options.get("disallowed_tools", DENIED_TOOLS)),
            resume_session_id=resume,
            max_turns=int(self.options.get("max_turns", 40)),
        )
        ctx = NodeContext(self.run.sink, node, self._attempt(node))
        self.node_models[(node, ctx.attempt)] = options.model
        result = self.run.agent.run(prompt, self.cwd, options, ctx)
        if result.status == "usage_limit":
            raise UsageLimitPaused(result)
        return result

    def ask_human(self, node: str, stage: str, message: str, **payload: Any) -> dict[str, Any]:
        if self.resuming_node != node:
            attempt = self._attempt(node)
            body: dict[str, Any] = {
                "interruptId": f"int_{self.run.run_id}_{node}_{attempt}",
                "stage": stage,
                "message": message,
            }
            if stage == "plan" and payload.get("plan"):
                body["plan"] = payload["plan"]
            if stage == "pr":
                body["commit"] = git.head(self.cwd)
                body["diffStat"] = git.diffstat(self.cwd, self.base_commit)
            self.run.emit_node(node, attempt, "waiting_human", runStatus="waiting_human")
            self.run.sink.emit("interrupt", node=node, attempt=attempt, interrupt=body)
        return interrupt({"node": node, "stage": stage})

    def open_pr(self, title: str, body: str) -> str:
        return self.run.pr_opener(self.run, title, body)


class WorkflowRun:
    def __init__(
        self,
        package: WorkflowPackage,
        *,
        run_id: str,
        cwd: Path,
        agent: Agent,
        author_email: str,
        sink: EventSink | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
        base_commit: str | None = None,
        options: dict[str, Any] | None = None,
        pr_opener: PrOpener | None = None,
        branch: str | None = None,
        repo: str | None = None,
        node_results: list[dict[str, Any]] | None = None,
        on_node_result: Callable[[dict[str, Any]], None] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.node_results = list(node_results or [])
        self.on_node_result = on_node_result
        self.package = package
        self.run_id = run_id
        self.cwd = Path(cwd)
        self.agent = agent
        self.author_email = author_email
        self.options = options or {}
        self.pr_opener = pr_opener or default_pr_opener()
        self.branch = branch
        self.repo = repo
        self.sink = sink or EventSink(run_id=run_id)
        self.sink.release = package.release
        self.sink.digest = package.digest
        self.weights = weights or package.weights
        self.ledger = Ledger.replay(self.sink.events, self.weights)
        self.sink.next_seq = max(self.sink.next_seq, self.ledger.last_seq + 1)
        self.sink.subscribe(self.ledger.apply)
        self.base_commit = base_commit or git.head(self.cwd)
        self.runtime = RunRuntime(self)
        self.graph = package.build_graph().compile(checkpointer=checkpointer or InMemorySaver())
        self.config = {"configurable": {"thread_id": run_id, "jigworks": self.runtime}}

    # -- events -----------------------------------------------------------------------------

    def record_node_result(self, entry: dict[str, Any]) -> None:
        self.node_results.append(entry)
        if self.on_node_result:
            self.on_node_result(entry)

    def emit_node(self, node: str, attempt: int, status: str, **fields: Any) -> None:
        extra = node if status == "succeeded" else None
        if status == "running" and getattr(self, "_retrying", False):
            fields.setdefault("runStatus", "running")  # a retried failed run is running again
            self._retrying = False
        self.sink.emit(
            "node_status",
            node=node,
            attempt=attempt,
            status=status,
            progress=self.ledger.progress(extra),
            step=self.ledger.step_count(extra),
            stepsPlanned=max(len(self.package.planned_path), 1),
            **fields,
        )

    # -- lifecycle --------------------------------------------------------------------------

    def start(self, prompt: str, title: str | None = None) -> Outcome:
        if self.ledger.started is not None:
            raise RunStateError(f"run {self.run_id} already started")
        started = {
            "workflowId": self.package.name,
            "release": self.package.release,
            "digest": self.package.digest,
            "authorEmail": self.author_email,
            "models": self.package.manifest["models"],
            "adapter": self.agent.name,
            "title": (title or prompt.strip().splitlines()[0])[:200],
            "plannedPath": self.package.planned_path,
            "runnerVersion": RUNNER_VERSION,
        }
        if self.repo:
            started["repo"] = self.repo
        if self.branch:
            started["branch"] = self.branch
        self.sink.emit(
            "run_started", runStatus="running", progress=0, step=0,
            stepsPlanned=max(len(self.package.planned_path), 1), runStarted=started,
        )
        return self._drive({"prompt": prompt})

    def pending_interrupt(self) -> dict[str, Any] | None:
        return self.ledger.pending

    def decide(self, decision: str, approver_email: str, comment: str | None = None) -> Outcome:
        pending = self.ledger.pending
        if pending is None:
            raise RunStateError(f"run {self.run_id} is not waiting for a decision")
        if decision == "request_changes" and not (comment and comment.strip()):
            raise RunStateError("request changes needs a comment (it is sent to the agent)")
        payload: dict[str, Any] = {
            "interruptId": pending["interruptId"],
            "stage": pending["stage"],
            "decision": decision,
            "approverEmail": approver_email,
        }
        if comment:
            payload["comment"] = comment
        self.sink.emit(
            "review_decision", node=pending["node"], attempt=pending["attempt"], reviewDecision=payload,
            runStatus="rejected" if decision == "reject" else "running",
        )
        self.runtime.resuming_node = pending["node"]
        return self._drive(Command(resume={"decision": decision, "comment": comment or ""}))

    def resume(self) -> Outcome:
        """Continue after a usage-limit pause or a crash, from the last LangGraph checkpoint.

        - A node that already committed and journaled its result (the process died after its
          git snapshot but before the checkpoint) is not run again: its journaled update is
          applied with `update_state(..., as_node=node)`.
        - A node that was cut off mid-way is reported `cancelled`, the worktree is reset to the
          last snapshot, and the node runs again as a new attempt.
        """
        if self.ledger.pending is not None:
            self.runtime.resuming_node = None
            return Outcome("waiting_human", self.ledger.pending)
        state = self.graph.get_state(self.config)
        # A run that failed because a node crashed (e.g. the PR push failed) still has a next node
        # in its checkpoint and can be retried; a run that ended (graph at END) cannot.
        retry = self.ledger.status == "failed" and bool(state.next)
        if self.ledger.status in ("succeeded", "failed", "rejected", "cancelled") and not retry:
            raise RunStateError(f"run {self.run_id} already {self.ledger.status}")
        self._retrying = retry
        if not state.next and state.values:
            return self._finish(state.values)
        if state.next:
            node = state.next[0]
            done = self._journaled(node)
            if done is not None:
                self.graph.update_state(self.config, done["update"], as_node=node)
            elif self.ledger.current is not None:
                cut_node, cut_attempt = self.ledger.current
                self.emit_node(cut_node, cut_attempt, "cancelled", runStatus="running")
                git.git(self.cwd, "reset", "-q", "--hard", self.ledger.last_commit or self.base_commit)
                git.git(self.cwd, "clean", "-q", "-fd")
        elif self.ledger.started is not None and not state.values:
            raise RunStateError(f"run {self.run_id} has no checkpoint to resume from")
        return self._drive(None)

    def _journaled(self, node: str) -> dict[str, Any] | None:
        """The journal entry of `node`'s latest attempt if that attempt finished and committed."""
        attempt = self.ledger.attempts.get(node)
        for entry in reversed(self.node_results):
            if entry["node"] == node and entry["attempt"] == attempt:
                finished = any(s["node"] == node and s["attempt"] == attempt for s in self.ledger.steps)
                head = git.head(self.cwd)
                return entry if finished and head == entry["commit"] else None
        return None

    def _drive(self, inp: Any) -> Outcome:
        try:
            for _ in self.graph.stream(inp, self.config, stream_mode="updates"):
                pass
        except UsageLimitPaused:
            return Outcome("paused_usage_limit")
        except Exception as exc:  # node crashed or the agent failed
            current = self.ledger.current
            if current is not None:
                self.emit_node(current[0], current[1], "failed")
            code = "agent_failed" if type(exc).__name__ == "AgentFailed" else "node_failed"
            self.sink.emit("error", node=current[0] if current else None, attempt=current[1] if current else None,
                           error={"code": code, "message": str(exc)[:2000], "retryable": False})
            return self._finish({"outcome": "failed"})
        state = self.graph.get_state(self.config)
        if state.interrupts:
            return Outcome("waiting_human", self.ledger.pending)
        return self._finish(state.values)

    def _finish(self, values: dict[str, Any]) -> Outcome:
        outcome = values.get("outcome") or "failed"
        status = {"succeeded": "succeeded", "rejected": "rejected"}.get(outcome, "failed")
        if status == "failed" and values.get("failure"):
            self.sink.emit("error", error={"code": "node_failed", "message": values["failure"], "retryable": False})
        if values.get("pr_url"):
            self.ledger.pr_url = values["pr_url"]
        finished_at = self.sink.now()
        self.ledger.status = status
        self.ledger.finished_at = finished_at
        summary = self.ledger.summary()
        self.sink.emit(
            "run_finished", runStatus=status, progress=self.ledger.progress(), step=self.ledger.step_count(),
            stepsPlanned=max(len(self.package.planned_path), 1), summary=summary,
        )
        return Outcome(status)

    def audit(self) -> dict[str, Any]:
        return self.ledger.audit()
