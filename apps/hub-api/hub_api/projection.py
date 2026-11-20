"""Rebuild a run's RunSummary and AuditRecord from its RunCreate and its events.

The hub stores every event once per (runId, seq) and re-projects the whole run after each
ingest. Runs have a few hundred events at most, so a full replay is cheap and keeps the
projection a pure function that is tested against the contract fixtures.
"""

from __future__ import annotations

from typing import Any

from jigworks_contracts.usage import per_call

TERMINAL = {"succeeded", "failed", "rejected", "cancelled"}
TOKEN_FIELDS = ("input", "output", "cache_write", "cache_read")


def _find_step(steps: list[dict], node: str, attempt: int | None) -> dict | None:
    for step in reversed(steps):
        if step["node"] == node and (attempt is None or step["attempt"] == attempt):
            return step
    return None


def project(created: dict[str, Any], events: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (summary, audit) as JSON-ready dicts. `created` is a RunCreate dict."""
    s: dict[str, Any] = {
        "runId": created["runId"],
        "workflowId": created["workflowId"],
        "release": created["release"],
        "digest": created["digest"],
        "status": "running",
        "authorEmail": created["authorEmail"],
        "startedAt": created["startedAt"],
        "models": created["models"],
        "followUpPrompts": 0,
        "fixLoops": 0,
        "changedFiles": [],
    }
    for key in ("releaseId", "title", "adapter", "stepsPlanned"):
        if created.get(key) is not None:
            s[key] = created[key]

    steps: list[dict] = []
    decisions: list[dict] = []
    usage: list[dict] = []
    last_commit: str | None = None
    final: dict | None = None

    for e in sorted(events, key=lambda ev: ev["seq"]):
        kind = e.get("kind") or "node_status"
        at = e["at"]
        s["updatedAt"] = at
        for key in ("progress", "step", "stepsPlanned"):
            if e.get(key) is not None:
                s[key] = e[key]
        if e.get("runStatus"):
            s["status"] = e["runStatus"]
            if e["runStatus"] not in TERMINAL:
                final = None  # resumed after run_finished (`jigworks resume`): that summary is stale

        if kind == "run_started":
            rs = e["runStarted"]
            for key in ("releaseId", "title", "adapter", "branch"):
                if rs.get(key) is not None and key not in s:
                    s[key] = rs[key]
            if rs.get("plannedPath") and "stepsPlanned" not in s:
                s["stepsPlanned"] = len(rs["plannedPath"])

        elif kind == "node_status":
            node, attempt, status = e["node"], e.get("attempt") or 1, e["status"]
            step = _find_step(steps, node, attempt)
            if status == "running" and step is None:
                step = {"node": node, "attempt": attempt, "status": "running", "startedAt": at}
                if e.get("model"):
                    step["model"] = e["model"]
                steps.append(step)
                if node == "fix":
                    s["fixLoops"] += 1
            elif step is None:  # terminal status without a running event: record it anyway
                step = {"node": node, "attempt": attempt, "status": status, "startedAt": at}
                steps.append(step)
            step["status"] = status
            if status in ("running", "waiting_human"):
                s["currentNode"] = node
            else:
                step["finishedAt"] = at
            snap = e.get("snapshot")
            if snap:
                last_commit = snap["commit"]
                step["commit"] = snap["commit"]
                if snap.get("changedFiles") is not None:
                    step["changedFiles"] = snap["changedFiles"]
                    for f in snap["changedFiles"]:
                        if f not in s["changedFiles"]:
                            s["changedFiles"].append(f)

        elif kind == "interrupt":
            it = e["interrupt"]
            if e.get("node"):
                s["currentNode"] = e["node"]
            if it["stage"] == "pr" and "firstResultCommit" not in s:
                commit = it.get("commit") or last_commit
                if commit:
                    s["firstResultCommit"] = commit

        elif kind == "review_decision":
            rd = e["reviewDecision"]
            d = {"stage": rd["stage"], "decision": rd["decision"], "approverEmail": rd["approverEmail"], "at": at}
            if rd.get("comment"):
                d["comment"] = rd["comment"]
            decisions.append(d)
            if rd["decision"] == "request_changes":
                s["followUpPrompts"] += 1
            if rd["decision"] == "approve" and rd["stage"] == "pr":
                s["approverEmail"], s["approvedAt"] = rd["approverEmail"], at

        elif kind == "gate_result":
            step = _find_step(steps, e.get("node") or "gate", e.get("attempt"))
            if step is not None:
                step["gate"] = e["gateResult"]

        elif kind == "usage":
            usage.append(e["usage"])

        elif kind == "run_finished":
            final = e["summary"]

    if s["status"] in TERMINAL:
        s.pop("currentNode", None)
        s["finishedAt"] = s.get("updatedAt", s["startedAt"])

    usage = per_call(usage)  # resumed sessions recorded as running totals (jigworks_contracts.usage)
    totals = {t: sum(u[t] for u in usage) for t in TOKEN_FIELDS}
    totals["cliCostUsd"] = round(sum(u.get("cliCostUsd") or 0 for u in usage), 6)
    s["usage"] = totals

    if final:  # the runner's own summary wins for the fields it states (prUrl, finalCommit, …)
        s.update({k: v for k, v in final.items() if k != "costUsd"})
        if s["status"] in TERMINAL:
            s.pop("currentNode", None)

    audit: dict[str, Any] = {
        "runId": s["runId"], "workflowId": s["workflowId"], "release": s["release"], "digest": s["digest"],
        "status": s["status"], "authorEmail": s["authorEmail"], "startedAt": s["startedAt"], "models": s["models"],
        "steps": steps, "decisions": decisions, "changedFiles": s["changedFiles"], "usage": usage,
        "cliCostUsd": totals["cliCostUsd"],
    }
    for key in ("adapter", "finishedAt", "approverEmail", "approvedAt", "firstResultCommit", "finalCommit", "prUrl"):
        if s.get(key) is not None:
            audit[key] = s[key]
    return s, audit


def human_wait_seconds(audit: dict[str, Any], interrupt_nodes: set[str]) -> float:
    """Time spent in interrupt nodes (waiting for a human), finished steps only."""
    from datetime import datetime  # noqa: PLC0415

    total = 0.0
    for step in audit["steps"]:
        if step["node"] in interrupt_nodes and step.get("finishedAt"):
            t0 = datetime.fromisoformat(step["startedAt"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(step["finishedAt"].replace("Z", "+00:00"))
            total += (t1 - t0).total_seconds()
    return total


def gate_passed_first_try(audit: dict[str, Any]) -> bool | None:
    """True/False for runs that reached the gate, None otherwise."""
    for step in audit["steps"]:
        if step["node"] == "gate" and step["attempt"] == 1 and step["status"] in ("succeeded", "failed"):
            return step["status"] == "succeeded"
    return None
