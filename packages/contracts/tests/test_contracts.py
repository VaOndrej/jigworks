"""Contract tests (T02). Run: uv run pytest packages/contracts"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import jigworks_contracts as c
from jigworks_contracts import models
from jigworks_contracts.bundle import build_bundle, digest, files_from_dir, read_bundle
from jigworks_contracts.graph import normalize_langgraph_json

PKG = Path(__file__).resolve().parent.parent
REPO = PKG.parent.parent
FIX = PKG / "fixtures"
INDEX = json.loads((FIX / "index.json").read_text())
STREAM_JSON = REPO / "runner" / "tests" / "fixtures" / "stream-json"

DESIGN_EXAMPLE = {  # design.md §8, verbatim
    "runId": "run_123",
    "release": "feature-development@1.3.0",
    "node": "review",
    "status": "running",
    "attempt": 2,
    "at": "2026-11-19T15:00:00Z",
}


def load(rel: str) -> list[dict]:
    meta = INDEX["fixtures"][rel]
    text = (FIX / rel).read_text()
    if meta.get("jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    return data if meta.get("list") else [data]


# --- the design example -------------------------------------------------------
def test_design_example_event_validates_as_is():
    assert c.validate("RunEvent", DESIGN_EXAMPLE) == []
    event = c.parse_event(DESIGN_EXAMPLE)
    assert event.kind == "node_status"  # default
    assert event.status == "running" and event.attempt == 2


def test_node_status_needs_node_and_status():
    bad = {k: v for k, v in DESIGN_EXAMPLE.items() if k != "status"}
    assert c.validate("RunEvent", bad)


@pytest.mark.parametrize(
    "kind,payload",
    [("run_started", "runStarted"), ("interrupt", "interrupt"), ("review_decision", "reviewDecision"),
     ("agent_output", "agentOutput"), ("gate_result", "gateResult"), ("usage", "usage"),
     ("usage_limit", "usageLimit"), ("error", "error"), ("run_finished", "summary")],
)
def test_every_kind_requires_its_payload(kind, payload):
    errors = c.validate("RunEvent", {"runId": "r1", "kind": kind, "node": "n", "at": "2026-11-19T15:00:00Z"})
    assert any(payload in e for e in errors), errors


def test_unknown_fields_are_rejected():
    assert c.validate("RunEvent", DESIGN_EXAMPLE | {"stauts": "running"})


# --- the fields the ticket requires ------------------------------------------
def test_run_event_covers_every_decision_after_the_plan():
    d = c.schema()["$defs"]
    ev = d["RunEvent"]["properties"]
    assert {"progress", "step", "stepsPlanned", "kind", "model"} <= ev.keys()
    assert ev["progress"]["minimum"] == 0 and ev["progress"]["maximum"] == 100
    assert {"node_status", "interrupt", "review_decision", "agent_output", "usage", "usage_limit", "error"} <= set(d["EventKind"]["enum"])
    assert d["InterruptStage"]["enum"] == ["plan", "pr"]
    assert d["ReviewDecisionValue"]["enum"] == ["approve", "request_changes", "reject"]
    assert "comment" in d["ReviewDecisionPayload"]["properties"]
    assert {"text", "tool"} <= d["AgentOutputPayload"]["properties"].keys()
    summary = d["RunSummary"]["properties"]
    assert {"firstResultCommit", "followUpPrompts", "authorEmail", "approverEmail", "models"} <= summary.keys()
    assert "authorEmail" in d["RunStartedPayload"]["required"]
    assert "approverEmail" in d["ReviewDecisionPayload"]["required"]
    assert "nodes" in d["ModelAssignment"]["properties"]  # models per node


def test_usage_record_uses_the_design_names():
    required = c.schema()["$defs"]["UsageRecord"]["required"]
    assert required == ["runId", "node", "attempt", "model", "adapter", "input", "output", "cache_write", "cache_read"]


def test_human_delta_outcomes():
    assert c.schema()["$defs"]["HumanDeltaOutcome"]["enum"] == [
        "worked_first_time", "corrected_by_prompt", "edited_by_hand", "rejected"]


# --- T00 mapping: real stream-json → UsageRecord, priced from prices.json ----
def test_usage_mapping_from_real_stream_json_matches_cli_cost():
    prices = {(p["model"], p["tokenType"]): p["pricePerMtok"] for p in load("prices.json")}
    checked = 0
    for path in sorted(STREAM_JSON.glob("*.jsonl")):
        result = [json.loads(line) for line in path.read_text().splitlines() if '"type": "result"' in line][-1]
        for model, u in (result.get("modelUsage") or {}).items():
            rec = {"runId": "run_t00", "node": "spike", "attempt": 1, "model": model, "adapter": "claude",
                   "input": u["inputTokens"], "output": u["outputTokens"],
                   "cache_write": u["cacheCreationInputTokens"], "cache_read": u["cacheReadInputTokens"],
                   "sessionId": result["session_id"], "cliCostUsd": u["costUSD"]}
            assert c.validate("UsageRecord", rec) == []
            if u["costUSD"] == 0:
                continue  # not-logged-in run
            cost = sum(rec[t] * prices[(model, t)] for t in ("input", "output", "cache_write", "cache_read")) / 1e6
            assert cost == pytest.approx(u["costUSD"], rel=1e-9), (path.name, model)
            checked += 1
    assert checked >= 5


# --- fixtures -------------------------------------------------------------------
@pytest.mark.parametrize("rel", sorted(INDEX["fixtures"]))
def test_fixture_validates(rel):
    def_name = INDEX["fixtures"][rel]["def"]
    for item in load(rel):
        assert c.validate(def_name, item) == [], rel
        getattr(models, def_name).model_validate(item)


@pytest.mark.parametrize("rel", sorted(r for r in INDEX["fixtures"] if r.startswith("runs/")))
def test_recorded_run_is_a_consistent_stream(rel):
    events = load(rel)
    run_ids = {e["runId"] for e in events}
    assert len(run_ids) == 1
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert [e["at"] for e in events] == sorted(e["at"] for e in events)
    assert events[0]["kind"] == "run_started"
    progress = [e["progress"] for e in events if "progress" in e]
    assert progress == sorted(progress), "progress must never move backwards"
    for e in events:
        if e["kind"] == "usage":
            assert e["usage"]["runId"] == e["runId"]
        if e["kind"] == "run_finished":
            assert e["summary"]["status"] == e["runStatus"]


def test_pydantic_round_trip_keeps_the_wire_format():
    for rel in (r for r in INDEX["fixtures"] if r.startswith("runs/")):
        for e in load(rel):
            dumped = c.parse_event(e).model_dump(mode="json", exclude_none=True)
            assert json.loads(json.dumps(dumped)) == e, (rel, e["seq"])


def test_fix_loop_run_counts_follow_ups_and_first_result():
    events = load("runs/run_fd_0002-fix-loops-request-changes.jsonl")
    decisions = [e["reviewDecision"]["decision"] for e in events if e["kind"] == "review_decision"]
    assert decisions == ["approve", "request_changes", "approve"]
    summary = events[-1]["summary"]
    assert summary["followUpPrompts"] == 1 and summary["fixLoops"] == 3
    first_pr = next(e for e in events if e["kind"] == "interrupt" and e["interrupt"]["stage"] == "pr")
    assert summary["firstResultCommit"] == first_pr["interrupt"]["commit"] != summary["finalCommit"]


# --- bundles and graph ----------------------------------------------------------
def test_bundle_digests_and_tampering():
    for rel, expected in INDEX["bundles"].items():
        data = (FIX / rel).read_bytes()
        assert digest(data) == expected == (FIX / (rel + ".sha256")).read_text().strip()
        files = read_bundle(data, expected)
        assert {"graph.py", "workflow.toml", "steps/nodes.py", "requirements.lock"} <= files.keys()
    for rel, claimed in INDEX["tampered"].items():
        with pytest.raises(ValueError, match="digest_mismatch"):
            read_bundle((FIX / rel).read_bytes(), claimed)


def test_bundle_build_is_deterministic():
    files = files_from_dir(FIX / "bundles" / "src" / "feature-development")
    assert build_bundle(files) == build_bundle(dict(reversed(list(files.items()))))
    with pytest.raises(ValueError):
        build_bundle({"../evil.py": b""})


def test_graph_fixture_is_normalized_from_real_get_graph():
    raw = json.loads((FIX / "graph" / "feature-development.langgraph.json").read_text())
    graph = json.loads((FIX / "graph" / "feature-development-1.3.0.graph.json").read_text())
    manifest = load("api/release-list.json")[0]["releases"][0]["manifest"]
    assert normalize_langgraph_json(raw, weights=manifest["weights"], interrupt_nodes=manifest["interruptNodes"],
                                    workflow_id="feature-development", release="feature-development@1.3.0") == graph
    kinds = {n["id"]: n["kind"] for n in graph["nodes"]}
    assert kinds["__start__"] == "start" and kinds["approve_pr"] == "interrupt" and kinds["implement"] == "step"
    assert {"source": "review", "target": "fix", "conditional": True} in graph["edges"]


# --- API description ------------------------------------------------------------
def test_models_are_generated_from_the_schema():
    out = subprocess.run([sys.executable, str(PKG / "scripts" / "generate.py"), "--check"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_openapi_stays_compatible_with_the_contract_stub():
    """HUB may regenerate openapi.json from the real app; it must keep every stub operation and schema."""
    sys.path.insert(0, str(PKG / "scripts"))
    from openapi_stub import build_app

    stub = build_app().openapi()
    spec = json.loads((PKG / "openapi.json").read_text())
    ops = lambda s: {f"{m.upper()} {p}" for p, o in s["paths"].items() for m in o}  # noqa: E731
    assert ops(stub) <= ops(spec), ops(stub) - ops(spec)
    missing = set(stub["components"]["schemas"]) - set(spec["components"]["schemas"]) - {"HTTPValidationError", "ValidationError"}
    assert not missing, missing
    for name, schema in stub["components"]["schemas"].items():
        if name in spec["components"]["schemas"] and name not in ("HTTPValidationError", "ValidationError"):
            assert set(schema.get("properties", {})) <= set(spec["components"]["schemas"][name].get("properties", {})), name


def test_openapi_states_the_auth_rule():
    spec = json.loads((PKG / "openapi.json").read_text())
    assert spec["security"] == [{"hubKey": []}, {"hubSession": []}]
    assert spec["components"]["securitySchemes"]["hubKey"] == {"type": "apiKey", "in": "header", "name": "X-Jigworks-Key"}
    assert spec["components"]["securitySchemes"]["hubSession"]["in"] == "cookie"
    public = sorted(f"{m.upper()} {p}" for p, ops in spec["paths"].items() for m, o in ops.items() if o.get("security") == [])
    assert public == ["GET /api/health", "POST /api/session"] == sorted(c.PUBLIC_ENDPOINTS)


def test_openapi_covers_the_design_endpoints():
    spec = json.loads((PKG / "openapi.json").read_text())
    ops = {f"{m.upper()} {p}" for p, o in spec["paths"].items() for m in o}
    design = {  # design.md §8 table
        "GET /api/workflows", "GET /api/workflows/{workflowId}/draft", "PUT /api/workflows/{workflowId}/draft",
        "POST /api/workflows/{workflowId}/validate", "POST /api/workflows/{workflowId}/publish",
        "GET /api/workflows/{workflowId}/releases", "GET /api/workflows/{workflowId}/channels/{channel}",
        "GET /api/releases/{releaseId}/bundle", "POST /api/runs", "POST /api/runs/{runId}/events",
        "GET /api/runs/{runId}/events/stream", "GET /api/analytics/usage",
    }
    assert design <= ops, design - ops
