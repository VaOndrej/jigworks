"""POST /api/admin/remove-sample-data: remove what the hub seeded from the contract fixtures,
with the hub password only, and never touch real releases or runs."""

from __future__ import annotations

from hub_api.db import forget_ready
from .test_api import _bump, _new_run

URL = "/api/admin/remove-sample-data"


def test_needs_the_hub_password(anon):
    assert anon.post(URL).status_code == 401


def test_removes_only_the_sample_data_and_keeps_real_work(client):
    # real work next to the seed: release 1.4.0 on stable and one run
    _bump(client, "1.4.0")
    assert client.post("/api/workflows/feature-development/publish", json={"version": "1.4.0", "channel": "stable"}).status_code == 201
    assert client.post("/api/runs", json=_new_run(client, "run_real_1")).status_code == 201

    r = client.post(URL)
    assert r.status_code == 200, r.json()
    assert r.json() == {"runs": 7, "releases": 2, "workflows": 0, "blobBundles": 0}

    releases = client.get("/api/workflows/feature-development/releases").json()["releases"]
    assert [x["version"] for x in releases] == ["1.4.0"]
    assert client.get("/api/workflows/feature-development/channels/stable").json()["version"] == "1.4.0"
    assert [x["runId"] for x in client.get("/api/runs").json()["runs"]] == ["run_real_1"]
    assert client.get("/api/analytics/overview").status_code == 200

    # idempotent
    assert client.post(URL).json() == {"runs": 0, "releases": 0, "workflows": 0, "blobBundles": 0}


def test_a_hub_with_only_sample_data_ends_empty_and_does_not_seed_again(client):
    r = client.post(URL)
    assert r.json() == {"runs": 7, "releases": 2, "workflows": 1, "blobBundles": 0}
    forget_ready()  # a cold start
    assert client.get("/api/workflows").json()["workflows"] == []
    assert client.get("/api/runs").json()["runs"] == []
    # publishing into the emptied hub works (PUT draft creates the workflow again)
    files = [{"path": "workflow.toml", "content": 'name = "x"\n'}]
    assert client.put("/api/workflows/feature-development/draft", json={"files": files}).status_code == 200
