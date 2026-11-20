"""Remove the sample data the hub seeded from the contract fixtures (seed.py).

Only rows whose ids come from the seed files are touched: real releases and runs stay, even
under the same workflow id. A workflow goes only when no release is left. The `seeded` flag
stays, so the hub does not seed itself again on the next cold start.
"""

from __future__ import annotations

import json

import psycopg

from .seed import SEED, _json


def seed_ids() -> tuple[list[str], list[str], list[str]]:
    release_ids = [r["id"] for r in _json("api/release-list.json")["releases"]]
    workflow_ids = [w["id"] for w in _json("api/workflow-list.json")["workflows"]]
    run_ids = []
    for path in sorted((SEED / "runs").iterdir(), key=lambda p: p.name):
        first = next(line for line in path.read_text().splitlines() if line.strip())
        run_ids.append(json.loads(first)["runId"])
    return release_ids, workflow_ids, run_ids


def remove(conn: psycopg.Connection) -> tuple[dict[str, int], list[str]]:
    """Delete the sample rows; returns the counts and the Blob URLs to delete after the commit."""
    release_ids, workflow_ids, run_ids = seed_ids()
    conn.execute("DELETE FROM human_deltas WHERE run_id = ANY(%s)", (run_ids,))
    runs = conn.execute("DELETE FROM runs WHERE run_id = ANY(%s)", (run_ids,)).rowcount  # events, usage cascade
    urls = [r["bundle_url"] for r in conn.execute(
        "SELECT bundle_url FROM releases WHERE id = ANY(%s) AND bundle_url IS NOT NULL", (release_ids,)).fetchall()]
    conn.execute("DELETE FROM channels WHERE release_id = ANY(%s)", (release_ids,))
    conn.execute("UPDATE drafts SET base_release_id = NULL WHERE base_release_id = ANY(%s)", (release_ids,))
    releases = conn.execute("DELETE FROM releases WHERE id = ANY(%s)", (release_ids,)).rowcount  # bundles cascade
    workflows = conn.execute(
        "DELETE FROM workflows w WHERE w.id = ANY(%s) AND NOT EXISTS (SELECT 1 FROM releases r WHERE r.workflow_id = w.id)",
        (workflow_ids,),
    ).rowcount  # drafts cascade
    conn.execute("DELETE FROM validations v WHERE NOT EXISTS (SELECT 1 FROM workflows w WHERE w.id = v.workflow_id)")
    return {"runs": runs, "releases": releases, "workflows": workflows, "blobBundles": len(urls)}, urls
