"""Hub API against local Postgres, seeded from the contract fixtures."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

import jigworks_contracts as c
from jigworks_contracts.bundle import digest, read_bundle

from .conftest import PASSWORD

FIX = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures"
API = FIX / "api"
DIGEST_130 = "sha256:e941f267e18b97560bcb4292047781b0844c70f6fea282c8c2a1c14733854c30"


def fixture(name: str):
    return json.loads((API / name).read_text())


def assert_contract(def_name: str, body) -> None:
    assert c.validate(def_name, body) == [], body


# --- auth ---------------------------------------------------------------------------------
PROTECTED = [
    ("GET", "/api/workflows"), ("GET", "/api/workflows/feature-development/draft"),
    ("PUT", "/api/workflows/feature-development/draft"), ("POST", "/api/workflows/feature-development/validate"),
    ("POST", "/api/workflows/feature-development/publish"), ("GET", "/api/workflows/feature-development/releases"),
    ("GET", "/api/workflows/feature-development/channels/stable"),
    ("PUT", "/api/workflows/feature-development/channels/stable"), ("GET", "/api/releases/rel_fd_1_3_0/bundle"),
    ("POST", "/api/runs"), ("GET", "/api/runs"), ("GET", "/api/runs/run_fd_0001"),
    ("POST", "/api/runs/run_fd_0001/events"), ("GET", "/api/runs/run_fd_0001/events"),
    ("GET", "/api/runs/run_fd_0001/events/stream"), ("GET", "/api/analytics/usage"),
    ("GET", "/api/analytics/releases?workflowId=feature-development"), ("GET", "/api/analytics/outcomes"),
    ("GET", "/api/analytics/overview"), ("DELETE", "/api/session"), ("GET", "/api/openapi.json"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_endpoint_needs_the_hub_password(anon, method, path):
    r = anon.request(method, path)
    assert r.status_code == 401
    assert r.json() == fixture("error-unauthorized.json") | {"error": r.json()["error"]}
    assert r.json()["error"]["code"] == "unauthorized"
    assert_contract("ErrorResponse", r.json())
    r = anon.request(method, path, headers={"X-Jigworks-Key": "wrong"})
    assert r.status_code == 401


def test_health_is_public(anon):
    assert anon.get("/api/health").json() == {"ok": True}


def test_login_sets_an_http_only_cookie_and_logout_clears_it(anon):
    assert anon.post("/api/session", json={"password": "nope"}).status_code == 401
    r = anon.post("/api/session", json={"password": PASSWORD})
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert "jigworks_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert PASSWORD not in cookie
    assert anon.get("/api/workflows").status_code == 200  # cookie jar sends it back
    out = anon.delete("/api/session")
    assert out.status_code == 204 and 'jigworks_session=""' in out.headers["set-cookie"]
    assert anon.get("/api/workflows").status_code == 401


def test_missing_password_env_fails_closed(anon, monkeypatch):
    monkeypatch.delenv("HUB_PASSWORD")
    assert anon.get("/api/workflows", headers={"X-Jigworks-Key": ""}).status_code == 401
    assert anon.post("/api/session", json={"password": PASSWORD}).status_code == 401


def test_validation_errors_use_the_contract_error_shape(client):
    r = client.post("/api/runs", json={"runId": "x"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"
    assert_contract("ErrorResponse", r.json())


# --- seed + workflows ---------------------------------------------------------------------
def test_seeded_workflow_list(client):
    body = client.get("/api/workflows").json()
    assert_contract("WorkflowList", body)
    (wf,) = body["workflows"]
    expected = fixture("workflow-list.json")["workflows"][0]
    assert {k: wf[k] for k in ("id", "name", "description", "ownerEmail", "latestVersion", "source")} == \
           {k: expected[k] for k in ("id", "name", "description", "ownerEmail", "latestVersion", "source")}
    assert wf["channels"] == {"stable": "1.3.0"}  # release-list.json: 1.3.0 is on stable only
    assert wf["hasUnpublishedDraft"] is False


def test_releases_match_the_fixture(client):
    body = client.get("/api/workflows/feature-development/releases").json()
    assert_contract("ReleaseList", body)
    assert body == fixture("release-list.json")


def test_channel_resolution_and_bundle_download(client):
    res = client.get("/api/workflows/feature-development/channels/stable").json()
    assert res == fixture("channel-stable.json")
    r = client.get(res["bundleUrl"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["x-jigworks-digest"] == res["digest"] == digest(r.content)
    assert r.content == (FIX / "bundles" / "feature-development-1.3.0.zip").read_bytes()
    assert client.get("/api/workflows/feature-development/channels/beta").status_code == 404
    assert client.get("/api/releases/nope/bundle").status_code == 404


def test_rollback_points_the_channel_to_an_older_release(client):
    r = client.put("/api/workflows/feature-development/channels/stable", json={"releaseId": "rel_fd_1_2_0"})
    assert r.status_code == 200 and r.json()["version"] == "1.2.0"
    assert client.get("/api/workflows/feature-development/channels/stable").json()["releaseId"] == "rel_fd_1_2_0"


# --- draft files --------------------------------------------------------------------------
def _draft(client):
    return client.get("/api/workflows/feature-development/draft").json()


def _put(client, files, wf="feature-development"):
    return client.put(f"/api/workflows/{wf}/draft", json={"files": files})


def test_draft_is_the_latest_release(client):
    d = _draft(client)
    assert_contract("Draft", d)
    assert d["baseReleaseId"] == "rel_fd_1_3_0"
    bundle = read_bundle((FIX / "bundles" / "feature-development-1.3.0.zip").read_bytes(), DIGEST_130)
    assert {f["path"]: f["content"].encode() for f in d["files"]} == bundle


def test_draft_files_create_rename_delete(client):
    files = _draft(client)["files"]
    # create a file and a folder (a folder exists through the files in it)
    files += [{"path": "steps/security_scan.py", "content": "def security_scan(state):\n    return {}\n"},
              {"path": "checks/.gitkeep", "content": ""}]
    d = _put(client, files).json()
    paths = [f["path"] for f in d["files"]]
    assert "steps/security_scan.py" in paths and "checks/.gitkeep" in paths and paths == sorted(paths)
    # rename a file and a folder
    files = [{**f, "path": f["path"].replace("prompts/", "phase_prompts/")} for f in d["files"]]
    files = [{**f, "path": "steps/scan.py"} if f["path"] == "steps/security_scan.py" else f for f in files]
    d = _put(client, files).json()
    paths = [f["path"] for f in d["files"]]
    assert "steps/scan.py" in paths and not any(p.startswith("prompts/") for p in paths)
    assert any(p.startswith("phase_prompts/") for p in paths)
    # delete a folder
    d = _put(client, [f for f in d["files"] if not f["path"].startswith("checks/")]).json()
    assert not any(f["path"].startswith("checks/") for f in d["files"])
    wf = client.get("/api/workflows").json()["workflows"][0]
    assert wf["hasUnpublishedDraft"] is True


@pytest.mark.parametrize("files", [
    [{"path": "a.py", "content": ""}, {"path": "a.py", "content": "x"}],  # duplicate
    [{"path": "../evil.py", "content": ""}],  # traversal
    [{"path": "/abs.py", "content": ""}],
    [{"path": "a", "content": ""}, {"path": "a/b.py", "content": ""}],  # file and folder
])
def test_bad_draft_paths_are_rejected(client, files):
    r = _put(client, files)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"


def test_new_workflow_from_template(client):
    r = _put(client, [], wf="docs-update")
    assert r.status_code == 200
    paths = {f["path"] for f in r.json()["files"]}
    assert {"workflow.toml", "graph.py", "steps/nodes.py", "requirements.lock"} <= paths
    ids = [w["id"] for w in client.get("/api/workflows").json()["workflows"]]
    assert ids == ["docs-update", "feature-development"]
    assert client.get("/api/workflows/nope/draft").status_code == 404


# --- validate + publish -------------------------------------------------------------------
def test_validate_returns_the_graph(client):
    r = client.post("/api/workflows/feature-development/validate")
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True, body
    assert_contract("ValidationResult", body)
    assert [ch["name"] for ch in body["checks"]] == ["manifest", "syntax", "imports", "compile", "graph"]
    expected = json.loads((FIX / "graph" / "feature-development-1.3.0.graph.json").read_text())
    assert body["graph"] == expected


def test_validate_reports_a_syntax_error_with_file_and_line(client):
    files = _draft(client)["files"]
    for f in files:
        if f["path"] == "steps/nodes.py":
            f["content"] = f["content"].replace("def plan(state):", "def plan(state)")
    _put(client, files)
    body = client.post("/api/workflows/feature-development/validate").json()
    assert body["ok"] is False and "graph" not in body
    bad = body["checks"][-1]
    assert bad["name"] == "syntax" and bad["file"] == "steps/nodes.py" and bad["line"] == 6
    assert_contract("ValidationResult", body)


def test_validate_checks_the_manifest(client):
    files = [f for f in _draft(client)["files"] if f["path"] != "workflow.toml"]
    _put(client, files + [{"path": "workflow.toml", "content": 'name = "other"\n'}])
    body = client.post("/api/workflows/feature-development/validate").json()
    assert body["ok"] is False and body["checks"][0]["name"] == "manifest"


def test_validation_never_imports_workflow_code(client, monkeypatch):
    """The API process only parses: a draft that would run code on import must not run it here."""
    files = _draft(client)["files"]
    for f in files:
        if f["path"] == "graph.py":
            f["content"] = "raise SystemExit('workflow code ran in the API process')\n" + f["content"]
    _put(client, files)
    import builtins

    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        assert name not in ("graph", "steps", "steps.nodes"), f"API process imported {name}"
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    assert client.post("/api/workflows/feature-development/validate").status_code == 200


def _bump(client, version: str) -> None:
    files = _draft(client)["files"]
    for f in files:
        if f["path"] == "workflow.toml":
            f["content"] = f["content"].replace('version = "1.3.0"', f'version = "{version}"')
    _put(client, files)


def test_publish_resolve_download_round_trip(client):
    _bump(client, "1.4.0")
    r = client.post("/api/workflows/feature-development/publish", json={"version": "1.4.0", "channel": "beta",
                                                                         "notes": "adds nothing yet"})
    assert r.status_code == 201, r.json()
    rel = r.json()
    assert_contract("Release", rel)
    assert rel["release"] == "feature-development@1.4.0" and rel["channels"] == ["beta"]
    res = client.get("/api/workflows/feature-development/channels/beta").json()
    assert res["releaseId"] == rel["id"] and res["digest"] == rel["digest"]
    data = client.get(res["bundleUrl"]).content
    files = read_bundle(data, rel["digest"])  # raises on a digest mismatch
    assert b'version = "1.4.0"' in files["workflow.toml"]
    assert zipfile.ZipFile(io.BytesIO(data)).testzip() is None
    # same draft → same bytes (deterministic bundle)
    from jigworks_contracts.bundle import build_bundle

    assert build_bundle(files) == data
    # immutability
    again = client.post("/api/workflows/feature-development/publish", json={"version": "1.4.0"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "conflict"
    wf = client.get("/api/workflows").json()["workflows"][0]
    assert wf["latestVersion"] == "1.4.0" and wf["channels"] == {"stable": "1.3.0", "beta": "1.4.0"}
    assert wf["hasUnpublishedDraft"] is False
    detail = client.get("/api/workflows/feature-development/releases").json()["releases"][0]
    assert detail["id"] == rel["id"] and detail["manifest"]["version"] == "1.4.0"


def test_publish_rejects_a_version_mismatch_and_an_invalid_draft(client):
    r = client.post("/api/workflows/feature-development/publish", json={"version": "9.9.9"})
    assert r.status_code == 409 and "workflow.toml says version" in r.json()["error"]["message"]
    _bump(client, "1.5.0")
    files = _draft(client)["files"]
    for f in files:
        if f["path"] == "graph.py":
            f["content"] += "\ndef broken(:\n"
    _put(client, files)
    r = client.post("/api/workflows/feature-development/publish", json={"version": "1.5.0"})
    assert r.status_code == 409 and "does not validate" in r.json()["error"]["message"]


# --- runs + events ------------------------------------------------------------------------
def test_seeded_runs_match_the_fixture_list(client):
    body = client.get("/api/runs").json()
    assert_contract("RunList", body)
    expected = {r["runId"]: r for r in fixture("run-list.json")["runs"]}
    got = {r["runId"]: r for r in body["runs"]}
    assert got.keys() == expected.keys()
    for run_id, run in got.items():
        assert run["costUsd"] == pytest.approx(run["usage"]["cliCostUsd"], abs=1e-6), run_id
        assert {k: v for k, v in run.items() if k != "costUsd"} == expected[run_id]
    starts = [r["startedAt"] for r in body["runs"]]
    assert starts == sorted(starts, reverse=True)


def test_run_list_filters_and_cursor(client):
    page1 = client.get("/api/runs?limit=3").json()
    page2 = client.get(f"/api/runs?limit=3&cursor={page1['nextCursor']}").json()
    page3 = client.get(f"/api/runs?limit=3&cursor={page2['nextCursor']}").json()
    ids = [r["runId"] for p in (page1, page2, page3) for r in p["runs"]]
    assert len(ids) == len(set(ids)) == 7 and "nextCursor" not in page3
    live = client.get("/api/runs?status=live").json()["runs"]
    assert sorted(r["status"] for r in live) == ["paused_usage_limit", "running", "waiting_human"]
    old = client.get("/api/runs?release=feature-development@1.2.0").json()["runs"]
    assert {r["runId"] for r in old} == {"run_fd_0003", "run_fd_0004"}


def test_run_detail_has_the_audit_trail_and_graph(client):
    body = client.get("/api/runs/run_fd_0002").json()
    assert_contract("RunDetail", body)
    expected = fixture("run-detail.json")
    assert body["audit"] == expected["audit"]
    assert body["graph"] == expected["graph"]
    assert {k: v for k, v in body["summary"].items() if k != "costUsd"} == expected["summary"]
    assert client.get("/api/runs/nope").status_code == 404


def _new_run(client, run_id="run_t12_live"):
    create = fixture("run-create.json") | {"runId": run_id, "startedAt": "2026-11-19T15:00:00Z"}
    return create


def test_register_is_idempotent_and_ingest_dedupes(client):
    create = _new_run(client)
    r1 = client.post("/api/runs", json=create)
    assert r1.status_code == 201 and r1.json()["status"] == "running"
    assert_contract("RunSummary", r1.json())
    assert client.post("/api/runs", json=create).status_code == 200

    batch = fixture("event-batch.json")
    events = [e | {"runId": "run_t12_live"} for e in batch["events"]]
    for e in events:
        if e.get("kind") == "usage":
            e["usage"] = e["usage"] | {"runId": "run_t12_live"}
    r = client.post("/api/runs/run_t12_live/events", json={"events": events})
    assert r.status_code == 200, r.json()
    assert r.json() == fixture("event-batch-result.json")
    replay = client.post("/api/runs/run_t12_live/events", json={"events": events})
    assert replay.json() == {"accepted": 0, "duplicates": len(events), "lastSeq": events[-1]["seq"]}
    page = client.get("/api/runs/run_t12_live/events?after=1").json()
    assert [e["seq"] for e in page["events"]] == [e["seq"] for e in events if e["seq"] > 1]
    assert page["events"] == [e for e in events if e["seq"] > 1]
    summary = client.get("/api/runs/run_t12_live").json()["summary"]
    assert summary["updatedAt"] == events[-1]["at"]


def test_ingest_rejects_bad_events(client):
    client.post("/api/runs", json=_new_run(client))
    ok = {"runId": "run_t12_live", "seq": 0, "at": "2026-11-19T15:00:00Z", "node": "plan", "status": "running"}
    assert client.post("/api/runs/other/events", json={"events": [ok | {"runId": "other"}]}).status_code == 404
    r = client.post("/api/runs/run_t12_live/events", json={"events": [ok | {"runId": "elsewhere"}]})
    assert r.status_code == 422 and "does not match" in r.json()["error"]["message"]
    no_seq = {k: v for k, v in ok.items() if k != "seq"}
    assert client.post("/api/runs/run_t12_live/events", json={"events": [no_seq]}).status_code == 422
    # kind → payload rule: a usage event without its usage payload
    r = client.post("/api/runs/run_t12_live/events", json={"events": [ok | {"kind": "usage"}]})
    assert r.status_code == 422 and "usage" in r.json()["error"]["message"]


def test_stream_replays_events_as_sse(client):
    r = client.get("/api/runs/run_fd_0003/events/stream?after=7")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    messages = [m for m in r.text.split("\n\n") if m.startswith("id:")]
    assert [m.splitlines()[0] for m in messages] == ["id: 8", "id: 9", "id: 10"]
    assert json.loads(messages[-1].splitlines()[2][len("data: "):])["kind"] == "run_finished"
    resumed = client.get("/api/runs/run_fd_0003/events/stream", headers={"Last-Event-ID": "9"})
    assert [m.splitlines()[0] for m in resumed.text.split("\n\n") if m.startswith("id:")] == ["id: 10"]
    assert client.get("/api/runs/nope/events/stream").status_code == 404


# --- analytics ----------------------------------------------------------------------------
def test_usage_by_release_prices_tokens_at_read_time(client):
    body = client.get("/api/analytics/usage?groupBy=release").json()
    assert_contract("UsageReport", body)
    assert body["costLabel"] == "API equivalent"
    runs = client.get("/api/runs").json()["runs"]
    for row in body["rows"]:
        mine = [r for r in runs if r["release"] == row["key"]]
        assert row["runs"] == len([r for r in mine if r["usage"]["output"] > 0])
        assert row["costUsd"] == pytest.approx(sum(r["costUsd"] for r in mine), abs=1e-5)
        # the price table reproduces the CLI's own cost
        assert row["costUsd"] == pytest.approx(row["cliCostUsd"], abs=1e-5)
    assert body["totals"]["costUsd"] == pytest.approx(sum(r["costUsd"] for r in body["rows"]), abs=1e-5)


@pytest.mark.parametrize("group", ["model", "node", "day"])
def test_usage_groupings(client, group):
    body = client.get(f"/api/analytics/usage?groupBy={group}&workflowId=feature-development").json()
    assert_contract("UsageReport", body)
    assert body["groupBy"] == group and body["rows"]
    total = client.get("/api/analytics/usage").json()["totals"]
    assert sum(r["input"] for r in body["rows"]) == total["input"]


def test_usage_period_filter(client):
    body = client.get("/api/analytics/usage?groupBy=day&from=2026-11-18T00:00:00Z&to=2026-11-19T00:00:00Z").json()
    assert [r["key"] for r in body["rows"]] == ["2026-11-18"]


def test_release_comparison(client):
    body = client.get("/api/analytics/releases?workflowId=feature-development").json()
    assert_contract("ReleaseComparison", body)
    rows = {r["version"]: r for r in body["rows"]}
    assert rows["1.2.0"]["runs"] == 2 and rows["1.2.0"]["rejected"] == 1 and rows["1.2.0"]["successRate"] == 0.5
    assert rows["1.3.0"]["runs"] == 5 and rows["1.3.0"]["succeeded"] == 2
    assert rows["1.3.0"]["avgFixLoops"] == pytest.approx(3 / 5)


def test_outcomes_are_planned_sample_data(client):
    body = client.get("/api/analytics/outcomes").json()
    assert_contract("OutcomeReport", body)
    assert body["planned"] is True and body["sample"] is True
    assert all(d["sample"] for d in body["deltas"])


def test_overview_key_numbers(client):
    body = client.get("/api/analytics/overview?from=2026-11-13T00:00:00Z&to=2026-11-20T00:00:00Z").json()
    assert body["runs"] == 7
    assert (body["running"], body["waitingHuman"], body["pausedUsageLimit"]) == (1, 1, 1)
    assert body["gateRuns"] == 4 and body["gatePassFirstTry"] == pytest.approx(2 / 4)
    assert body["medianTimeToPrSec"] > 0 and body["costLabel"] == "API equivalent"
    assert [d["day"] for d in body["costByDay"]][:1] == ["2026-11-13"] and len(body["costByDay"]) == 7
    day_total = sum(sum(v for k, v in d.items() if k != "day") for d in body["costByDay"])
    assert day_total == pytest.approx(body["costUsd"], abs=1e-4)
    assert body["workflows"][0]["workflowId"] == "feature-development"


# --- OpenAPI ------------------------------------------------------------------------------
def test_committed_openapi_is_generated_from_this_app(client):
    spec = client.get("/api/openapi.json").json()
    committed = json.loads((FIX.parent / "openapi.json").read_text())
    assert spec == committed, "regenerate: uv run python apps/hub-api/scripts/export_openapi.py"


def test_prices_added_after_the_first_seed_reach_an_existing_hub(fresh_db):
    """The seed runs once per database, but the price list grows (Opus/Sonnet/Haiku 5.5 came after
    the production hub was seeded): every start adds missing price rows, so runs are not $0."""
    from hub_api.db import connect, forget_ready

    with connect() as conn:
        conn.execute("DELETE FROM prices WHERE model LIKE %s", ("%-5-5",))
    forget_ready()  # a new process (cold start after a deploy)
    with connect() as conn:
        models = {r["model"] for r in conn.execute("SELECT DISTINCT model FROM prices").fetchall()}
    assert {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"} <= models
