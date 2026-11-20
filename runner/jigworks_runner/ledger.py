"""The run ledger: everything the runner knows about a run, derived **only** from its events.

Because it is a pure fold over the event log, a killed runner rebuilds it by replaying the
log (T06 resume), and the audit record and run summary are views of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import jigworks_contracts as contracts

TOKEN_FIELDS = ("input", "output", "cache_write", "cache_read")


@dataclass
class Ledger:
    weights: dict[str, float] = field(default_factory=dict)
    run_id: str | None = None
    started: dict[str, Any] | None = None
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    status: str = "running"
    planned_path: list[str] = field(default_factory=list)
    attempts: dict[str, int] = field(default_factory=dict)
    finished_planned: list[str] = field(default_factory=list)
    current: tuple[str, int] | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    open_steps: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)
    pending: dict[str, Any] | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    follow_ups: int = 0
    fix_loops: int = 0
    first_result_commit: str | None = None
    last_commit: str | None = None
    approver_email: str | None = None
    approved_at: str | None = None
    usage: list[dict[str, Any]] = field(default_factory=list)
    pr_url: str | None = None
    branch: str | None = None
    changed_files: list[str] = field(default_factory=list)
    last_seq: int = -1

    # -- progress -------------------------------------------------------------------------

    def _total_weight(self) -> float:
        return sum(self.weights.get(n, 1.0) for n in self.planned_path) or 1.0

    def progress(self, extra: str | None = None) -> float:
        done = set(self.finished_planned)
        if extra and extra in self.planned_path:
            done.add(extra)
        value = sum(self.weights.get(n, 1.0) for n in done) / self._total_weight() * 100
        return round(min(value, 100.0), 1)

    def step_count(self, extra: str | None = None) -> int:
        done = set(self.finished_planned)
        if extra and extra in self.planned_path:
            done.add(extra)
        return len(done)

    # -- fold -------------------------------------------------------------------------------

    def apply(self, e: dict[str, Any]) -> None:
        self.last_seq = e.get("seq", self.last_seq)
        self.run_id = e["runId"]
        self.updated_at = e["at"]
        kind = e.get("kind", "node_status")
        if kind == "run_started":
            self.started = e["runStarted"]
            self.started_at = e["at"]
            self.planned_path = list(self.started.get("plannedPath", []))
            self.branch = self.started.get("branch")
        elif kind == "node_status":
            self._node_status(e)
        elif kind == "interrupt":
            p = e["interrupt"]
            self.pending = {"node": e["node"], "attempt": e.get("attempt", 1), **p}
            if p["stage"] == "pr" and p.get("commit") and self.first_result_commit is None:
                self.first_result_commit = p["commit"]
        elif kind == "review_decision":
            d = e["reviewDecision"]
            self.decisions.append(
                {k: v for k, v in {"stage": d["stage"], "decision": d["decision"], "approverEmail": d["approverEmail"],
                                   "comment": d.get("comment"), "at": e["at"]}.items() if v is not None}
            )
            if d["decision"] == "request_changes" and d["stage"] == "pr":
                # A follow-up prompt corrects a result; agreeing on the plan comes before the first one.
                self.follow_ups += 1
            if d["decision"] == "approve" and d["stage"] == "pr":
                self.approver_email, self.approved_at = d["approverEmail"], e["at"]
            self.pending = None
        elif kind == "gate_result":
            step = self.open_steps.get((e["node"], e.get("attempt", 1)))
            if step is not None:
                step["gate"] = e["gateResult"]
        elif kind == "usage":
            self.usage.append(e["usage"])
            step = self.open_steps.get((e["node"], e.get("attempt", 1))) if e.get("node") else None
            if step is not None:
                step.setdefault("model", e["usage"]["model"])
        elif kind == "run_finished":
            s = e["summary"]
            self.finished_at = s.get("finishedAt", e["at"])
            self.pr_url = s.get("prUrl", self.pr_url)
        if e.get("runStatus"):
            self.status = e["runStatus"]

    def _node_status(self, e: dict[str, Any]) -> None:
        node, attempt, status = e["node"], e.get("attempt", 1), e["status"]
        self.attempts[node] = max(self.attempts.get(node, 0), attempt)
        key = (node, attempt)
        if status == "running":
            self.current = key
            if key not in self.open_steps:
                self.open_steps[key] = {"node": node, "attempt": attempt, "status": "running", "startedAt": e["at"]}
            return
        if status == "waiting_human":
            self.current = key
            self.open_steps.setdefault(key, {"node": node, "attempt": attempt, "startedAt": e["at"]})["status"] = status
            return
        step = self.open_steps.pop(key, {"node": node, "attempt": attempt, "startedAt": e["at"]})
        step["status"] = status
        step["finishedAt"] = e["at"]
        if e.get("model"):
            step["model"] = e["model"]  # the release's model, set by the runner (beats usage order)
        snap = e.get("snapshot")
        if snap:
            step["commit"] = snap["commit"]
            self.last_commit = snap["commit"]
            if snap.get("changedFiles"):
                step["changedFiles"] = snap["changedFiles"]
                for f in snap["changedFiles"]:
                    if f not in self.changed_files:
                        self.changed_files.append(f)
        self.steps.append(step)
        if status == "succeeded" and node in self.planned_path and node not in self.finished_planned:
            self.finished_planned.append(node)
        if node == "fix" and status == "succeeded":
            self.fix_loops += 1
        if self.current == key:
            self.current = None

    @classmethod
    def replay(cls, events: list[dict[str, Any]], weights: dict[str, float]) -> Ledger:
        ledger = cls(weights=weights)
        for e in events:
            ledger.apply(e)
        return ledger

    # -- views ------------------------------------------------------------------------------

    def usage_totals(self) -> dict[str, Any]:
        totals: dict[str, Any] = {t: sum(u[t] for u in self.usage) for t in TOKEN_FIELDS}
        cli = [u["cliCostUsd"] for u in self.usage if "cliCostUsd" in u]
        if cli:
            totals["cliCostUsd"] = round(sum(cli), 6)
        return totals

    def summary(self, final_commit: str | None = None) -> dict[str, Any]:
        s = self.started or {}
        out: dict[str, Any] = {
            "runId": self.run_id,
            "workflowId": s.get("workflowId"),
            "release": s.get("release"),
            "digest": s.get("digest"),
            "status": self.status,
            "authorEmail": s.get("authorEmail"),
            "startedAt": self.started_at,
            "models": s.get("models"),
            "followUpPrompts": self.follow_ups,
            "fixLoops": self.fix_loops,
            "adapter": s.get("adapter"),
            "title": s.get("title"),
            "updatedAt": self.updated_at,
            "finishedAt": self.finished_at,
            "progress": self.progress(),
            "step": self.step_count(),
            "stepsPlanned": max(len(self.planned_path), 1),
            "currentNode": self.current[0] if self.current else None,
            "approverEmail": self.approver_email,
            "approvedAt": self.approved_at,
            "firstResultCommit": self.first_result_commit,
            "finalCommit": final_commit or self.last_commit,
            "prUrl": self.pr_url,
            "branch": self.branch,
            "changedFiles": self.changed_files or None,
            "usage": self.usage_totals(),
        }
        out = {k: v for k, v in out.items() if v is not None}
        contracts.assert_valid("RunSummary", out)
        return out

    def audit(self) -> dict[str, Any]:
        s = self.started or {}
        steps = self.steps + [dict(v) for v in self.open_steps.values()]
        record: dict[str, Any] = {
            "runId": self.run_id,
            "workflowId": s.get("workflowId"),
            "release": s.get("release"),
            "digest": s.get("digest"),
            "authorEmail": s.get("authorEmail"),
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "status": self.status,
            "models": s.get("models"),
            "adapter": s.get("adapter"),
            "steps": steps,
            "decisions": self.decisions,
            "changedFiles": self.changed_files,
            "firstResultCommit": self.first_result_commit,
            "finalCommit": self.last_commit,
            "approverEmail": self.approver_email,
            "approvedAt": self.approved_at,
            "prUrl": self.pr_url,
            "usage": self.usage,
        }
        cli = self.usage_totals().get("cliCostUsd")
        if cli is not None:
            record["cliCostUsd"] = cli
        record = {k: v for k, v in record.items() if v is not None}
        contracts.assert_valid("AuditRecord", record)
        return record
