"""The projection rebuilds exactly the RunSummary / AuditRecord the contract fixtures expect."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import jigworks_contracts as c
from hub_api.projection import gate_passed_first_try, project
from hub_api.seed import run_create_from_started

FIX = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures"
RUNS = sorted((FIX / "runs").glob("*.jsonl"))
EXPECTED = {r["runId"]: r for r in json.loads((FIX / "api" / "run-list.json").read_text())["runs"]}


def events_of(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("path", RUNS, ids=lambda p: p.stem)
def test_summary_matches_the_fixture(path):
    events = events_of(path)
    summary, audit = project(run_create_from_started(events[0]), events)
    expected = {k: v for k, v in EXPECTED[events[0]["runId"]].items() if k != "costUsd"}
    assert summary == expected
    assert c.validate("RunSummary", summary) == []
    assert c.validate("AuditRecord", audit) == []


def test_live_runs_are_projected_from_events_only():
    """Runs without run_finished: no runner summary to copy, every field comes from the replay."""
    for path in RUNS:
        events = events_of(path)
        if any(e["kind"] == "run_finished" for e in events):
            continue
        summary, _ = project(run_create_from_started(events[0]), events)
        assert summary["status"] in ("waiting_human", "paused_usage_limit", "running")
        assert summary["currentNode"]


def test_audit_matches_the_fixture():
    events = events_of(FIX / "runs" / "run_fd_0002-fix-loops-request-changes.jsonl")
    _, audit = project(run_create_from_started(events[0]), events)
    assert audit == json.loads((FIX / "audit" / "run_fd_0002.audit.json").read_text())


def test_replay_order_and_duplicates_do_not_matter():
    events = events_of(FIX / "runs" / "run_fd_0002-fix-loops-request-changes.jsonl")
    created = run_create_from_started(events[0])
    assert project(created, list(reversed(events))) == project(created, events)


def test_gate_first_try():
    by_id = {}
    for path in RUNS:
        events = events_of(path)
        by_id[events[0]["runId"]] = gate_passed_first_try(project(run_create_from_started(events[0]), events)[1])
    assert by_id["run_fd_0001"] is True
    assert by_id["run_fd_0004"] is False
    assert by_id["run_fd_0003"] is None  # rejected at the plan, never reached the gate


def test_a_resumed_run_is_live_again():
    """A run that ended `failed` and was resumed (`jigworks resume`) is running again: the old
    run_finished summary must not override the later status (run_20261120122836_6ab988)."""
    events = events_of(FIX / "runs" / "run_fd_0003-rejected-at-plan.jsonl")
    last = events[-1]
    assert last["kind"] == "run_finished"
    base = {k: last[k] for k in ("runId", "release")}
    events += [
        {**base, "seq": last["seq"] + 1, "kind": "node_status", "at": "2026-11-20T15:21:10Z",
         "node": "review", "attempt": 11, "status": "running", "runStatus": "running"},
    ]
    summary, audit = project(run_create_from_started(events[0]), events)
    assert summary["status"] == "running"
    assert summary["currentNode"] == "review"
    assert "finishedAt" not in summary
    assert c.validate("RunSummary", summary) == []
    assert c.validate("AuditRecord", audit) == []
