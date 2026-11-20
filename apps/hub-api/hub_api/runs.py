"""Run registration and event ingest (the hub side of T14)."""

from __future__ import annotations

from typing import Any

import psycopg

import jigworks_contracts as c

from .db import Jsonb
from .errors import ApiError, not_found
from .projection import project


def _iso(value: Any) -> str:
    return value.isoformat().replace("+00:00", "Z") if hasattr(value, "isoformat") else value


def register_run(conn: psycopg.Connection, created: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Insert a run (RunCreate dict). Idempotent on runId: returns (row, created_now)."""
    row = conn.execute("SELECT * FROM runs WHERE run_id = %s", (created["runId"],)).fetchone()
    if row:
        return row, False
    summary, audit = project(created, [])
    row = conn.execute(
        """INSERT INTO runs (run_id, workflow_id, release, status, started_at, updated_at, created, summary, audit)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (run_id) DO NOTHING RETURNING *""",
        (created["runId"], created["workflowId"], created["release"], summary["status"], created["startedAt"],
         created["startedAt"], Jsonb(created), Jsonb(summary), Jsonb(audit)),
    ).fetchone()
    if row is None:  # lost a race with a concurrent registration
        return conn.execute("SELECT * FROM runs WHERE run_id = %s", (created["runId"],)).fetchone(), False
    return row, True


def ingest(conn: psycopg.Connection, run_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Store each (runId, seq) once, then re-project the run. Returns an EventBatchResult dict."""
    problems = []
    for i, ev in enumerate(events):
        if ev.get("runId") != run_id:
            problems.append(f"events/{i}: runId {ev.get('runId')!r} does not match the path")
        if ev.get("seq") is None:
            problems.append(f"events/{i}: seq is required")
        problems += [f"events/{i}{err}" for err in c.validate("RunEvent", ev)]
    if problems:
        raise ApiError(422, "validation_failed", "; ".join(problems[:20]))

    run = conn.execute("SELECT created FROM runs WHERE run_id = %s FOR UPDATE", (run_id,)).fetchone()
    if run is None:
        raise not_found(f"run {run_id} (register it with POST /api/runs first)")

    accepted = duplicates = 0
    for ev in events:
        kind = ev.get("kind") or "node_status"
        inserted = conn.execute(
            """INSERT INTO events (run_id, seq, kind, at, body) VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (run_id, seq) DO NOTHING RETURNING seq""",
            (run_id, ev["seq"], kind, ev["at"], Jsonb(ev)),
        ).fetchone()
        if inserted is None:
            duplicates += 1
            continue
        accepted += 1
        if kind == "usage":
            u = ev["usage"]
            conn.execute(
                """INSERT INTO usage (run_id, seq, node, attempt, model, adapter, input, output, cache_write,
                                      cache_read, cli_cost_usd, at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (run_id, ev["seq"], u["node"], u["attempt"], u["model"], u["adapter"], u["input"], u["output"],
                 u["cache_write"], u["cache_read"], u.get("cliCostUsd"), u.get("at") or ev["at"]),
            )

    if accepted:
        reproject(conn, run_id, run["created"])
    last = conn.execute("SELECT max(seq) AS m FROM events WHERE run_id = %s", (run_id,)).fetchone()["m"]
    result: dict[str, Any] = {"accepted": accepted, "duplicates": duplicates}
    if last is not None:
        result["lastSeq"] = last
    return result


def reproject(conn: psycopg.Connection, run_id: str, created: dict[str, Any]) -> None:
    rows = conn.execute("SELECT body FROM events WHERE run_id = %s ORDER BY seq", (run_id,)).fetchall()
    summary, audit = project(created, [r["body"] for r in rows])
    conn.execute(
        "UPDATE runs SET status = %s, updated_at = %s, summary = %s, audit = %s WHERE run_id = %s",
        (summary["status"], summary.get("updatedAt") or summary["startedAt"], Jsonb(summary), Jsonb(audit), run_id),
    )


def events_after(conn: psycopg.Connection, run_id: str, after: int, limit: int) -> dict[str, Any]:
    if conn.execute("SELECT 1 FROM runs WHERE run_id = %s", (run_id,)).fetchone() is None:
        raise not_found(f"run {run_id}")
    rows = conn.execute(
        "SELECT body FROM events WHERE run_id = %s AND seq > %s ORDER BY seq LIMIT %s", (run_id, after, limit)
    ).fetchall()
    events = [r["body"] for r in rows]
    page: dict[str, Any] = {"events": events}
    if events:
        page["lastSeq"] = events[-1]["seq"]
    return page


__all__ = ["events_after", "ingest", "register_run", "reproject", "_iso"]
