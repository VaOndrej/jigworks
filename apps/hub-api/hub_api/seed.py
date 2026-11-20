"""Seed an empty hub database from the contract fixtures (copied into seed_data/).

Runs go through the same register + ingest path as real runner traffic, so the seeded
Runs & analytics tab exercises the projection, not a separate import.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

import psycopg

from jigworks_contracts.bundle import read_bundle

from . import drafts, releases, runs
from .db import SCHEMA_VERSION, Jsonb

SEED = resources.files(__package__) / "seed_data"
BUNDLES = {"1.2.0": "bundles/feature-development-1.2.0.zip", "1.3.0": "bundles/feature-development-1.3.0.zip"}


def _json(rel: str) -> Any:
    return json.loads((SEED / rel).read_text())


def run_create_from_started(ev: dict[str, Any]) -> dict[str, Any]:
    """The RunCreate a runner sends before its first event, derived from run_started."""
    rs = ev["runStarted"]
    created = {"runId": ev["runId"], "workflowId": rs["workflowId"], "release": rs["release"], "digest": rs["digest"],
               "authorEmail": rs["authorEmail"], "models": rs["models"], "startedAt": ev["at"]}
    for key in ("releaseId", "adapter", "title"):
        if rs.get(key) is not None:
            created[key] = rs[key]
    if ev.get("stepsPlanned"):
        created["stepsPlanned"] = ev["stepsPlanned"]
    return created


def seed_if_empty(conn: psycopg.Connection) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key = 'seeded'").fetchone()
    if row:
        return False
    seed(conn)
    conn.execute("INSERT INTO meta (key, value) VALUES ('seeded', %s)", (SCHEMA_VERSION,))
    return True


def sync_prices(conn: psycopg.Connection) -> None:
    """Add price rows the database does not have yet. Runs on every start, not only on the first
    seed: the price list grows with new models, and a run on an unpriced model costs $0."""
    for p in _json("prices.json"):
        conn.execute(
            "INSERT INTO prices (model, token_type, price_per_mtok, valid_from) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (p["model"], p["tokenType"], p["pricePerMtok"], p["validFrom"]),
        )


def seed(conn: psycopg.Connection) -> None:
    sync_prices(conn)

    for wf in _json("api/workflow-list.json")["workflows"]:
        conn.execute(
            "INSERT INTO workflows (id, name, description, owner_email, source, updated_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (wf["id"], wf["name"], wf.get("description"), wf.get("ownerEmail"), wf.get("source", "hub"), wf["updatedAt"]),
        )

    graph_130 = _json("graph/feature-development-1.3.0.graph.json")
    latest_files: dict[str, str] = {}
    latest_id = None
    for rel in sorted(_json("api/release-list.json")["releases"], key=lambda r: r["publishedAt"]):
        data = (SEED / BUNDLES[rel["version"]]).read_bytes()
        files = {p: b.decode() for p, b in read_bundle(data, rel["digest"]).items()}
        fhash = drafts.files_hash([{"path": p, "content": c} for p, c in files.items()])
        releases.insert_release(
            conn, release_id=rel["id"], workflow_id=rel["workflowId"], version=rel["version"], data=data,
            published_at=rel["publishedAt"], published_by=rel.get("publishedBy"), notes=rel.get("notes"),
            manifest=rel.get("manifest"), graph=graph_130 if rel["version"] == "1.3.0" else None, fhash=fhash,
        )
        # Decision (build log): channels come from release-list.json (1.3.0 → stable only);
        # workflow-list.json also claims beta 1.3.0, the two fixtures disagree.
        for channel in rel.get("channels") or []:
            releases.point_channel(conn, rel["workflowId"], channel, rel["id"])
        latest_files, latest_id = files, rel["id"]

    # The draft starts as the latest release (no unpublished changes).
    saved = drafts.save(conn, "feature-development", [{"path": p, "content": c} for p, c in latest_files.items()])
    conn.execute("UPDATE drafts SET base_release_id = %s, updated_at = %s WHERE workflow_id = %s",
                 (latest_id, "2026-11-18T09:00:00Z", saved["workflow_id"]))
    conn.execute("UPDATE workflows SET updated_at = %s WHERE id = 'feature-development'", ("2026-11-18T09:00:00Z",))

    for path in sorted((SEED / "runs").iterdir(), key=lambda p: p.name):
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        runs.register_run(conn, run_create_from_started(events[0]))
        runs.ingest(conn, events[0]["runId"], events)

    for d in _json("human-deltas.json"):
        conn.execute("INSERT INTO human_deltas (run_id, release, body) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (d["runId"], d["release"], Jsonb(d)))
