"""Immutable releases, channels and publishing (design.md §6)."""

from __future__ import annotations

import tomllib
import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg

from jigworks_contracts.bundle import build_bundle, digest

from . import bundles, drafts
from .db import Jsonb
from .errors import ApiError, not_found
from .validation import validate_draft

CHANNELS = ("stable", "beta")


def channels_of(conn: psycopg.Connection, workflow_id: str) -> dict[str, str]:
    rows = conn.execute("SELECT channel, release_id FROM channels WHERE workflow_id = %s", (workflow_id,)).fetchall()
    return {r["channel"]: r["release_id"] for r in rows}


def to_api(row: dict[str, Any], channels: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row["id"], "workflowId": row["workflow_id"], "version": row["version"],
        "release": f"{row['workflow_id']}@{row['version']}", "digest": row["digest"],
        "publishedAt": row["published_at"], "bundleBytes": row["bundle_bytes"],
        "channels": [ch for ch in CHANNELS if channels.get(ch) == row["id"]],
    }
    for key, api in (("published_by", "publishedBy"), ("notes", "notes"), ("manifest", "manifest")):
        if row.get(key) is not None:
            out[api] = row[key]
    return out


def list_releases(conn: psycopg.Connection, workflow_id: str) -> list[dict[str, Any]]:
    if conn.execute("SELECT 1 FROM workflows WHERE id = %s", (workflow_id,)).fetchone() is None:
        raise not_found(f"workflow {workflow_id}")
    chans = channels_of(conn, workflow_id)
    rows = conn.execute(
        "SELECT * FROM releases WHERE workflow_id = %s ORDER BY published_at DESC, id DESC", (workflow_id,)
    ).fetchall()
    return [to_api(r, chans) for r in rows]


def get_release(conn: psycopg.Connection, release_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM releases WHERE id = %s", (release_id,)).fetchone()
    if row is None:
        raise not_found(f"release {release_id}")
    return row


def resolution(row: dict[str, Any], channel: str) -> dict[str, Any]:
    return {"workflowId": row["workflow_id"], "channel": channel, "releaseId": row["id"], "version": row["version"],
            "digest": row["digest"], "bundleUrl": f"/api/releases/{row['id']}/bundle"}


def resolve_channel(conn: psycopg.Connection, workflow_id: str, channel: str) -> dict[str, Any]:
    release_id = channels_of(conn, workflow_id).get(channel)
    if release_id is None:
        raise not_found(f"channel {channel} of workflow {workflow_id}")
    return resolution(get_release(conn, release_id), channel)


def point_channel(conn: psycopg.Connection, workflow_id: str, channel: str, release_id: str) -> dict[str, Any]:
    row = get_release(conn, release_id)
    if row["workflow_id"] != workflow_id:
        raise ApiError(422, "validation_failed", f"release {release_id} belongs to {row['workflow_id']}, not {workflow_id}")
    conn.execute(
        """INSERT INTO channels (workflow_id, channel, release_id, updated_at) VALUES (%s, %s, %s, %s)
           ON CONFLICT (workflow_id, channel) DO UPDATE SET release_id = EXCLUDED.release_id, updated_at = EXCLUDED.updated_at""",
        (workflow_id, channel, release_id, datetime.now(UTC)),
    )
    conn.execute("UPDATE workflows SET updated_at = %s WHERE id = %s", (datetime.now(UTC), workflow_id))
    return resolution(row, channel)


def cached_validation(conn: psycopg.Connection, workflow_id: str, fhash: str) -> dict | None:
    row = conn.execute(
        "SELECT result FROM validations WHERE workflow_id = %s AND files_hash = %s", (workflow_id, fhash)
    ).fetchone()
    return row["result"] if row else None


def store_validation(conn: psycopg.Connection, workflow_id: str, fhash: str, result: dict) -> None:
    conn.execute(
        """INSERT INTO validations (workflow_id, files_hash, result) VALUES (%s, %s, %s)
           ON CONFLICT (workflow_id, files_hash) DO UPDATE SET result = EXCLUDED.result, created_at = now()""",
        (workflow_id, fhash, Jsonb(result)),
    )


def insert_release(conn: psycopg.Connection, *, release_id: str, workflow_id: str, version: str, data: bytes,
                   published_at: datetime | str, published_by: str | None, notes: str | None,
                   manifest: dict | None, graph: dict | None, fhash: str | None) -> dict[str, Any]:
    bundle_digest = digest(data)
    conn.execute(
        """INSERT INTO releases (id, workflow_id, version, digest, published_at, published_by, notes, manifest,
                                 graph, bundle_bytes, files_hash)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (release_id, workflow_id, version, bundle_digest, published_at, published_by, notes,
         Jsonb(manifest) if manifest is not None else None, Jsonb(graph) if graph is not None else None,
         len(data), fhash),
    )
    url = bundles.put(conn, release_id, bundles.blob_pathname(workflow_id, version, bundle_digest), data)
    if url:
        conn.execute("UPDATE releases SET bundle_url = %s WHERE id = %s", (url, release_id))
    return get_release(conn, release_id)


def publish(conn: psycopg.Connection, workflow_id: str, body: dict[str, Any], request_headers: dict[str, str]) -> dict[str, Any]:
    draft = drafts.get(conn, workflow_id)
    files = {f["path"]: f["content"] for f in draft["files"]}
    version = body["version"]
    if conn.execute("SELECT 1 FROM releases WHERE workflow_id = %s AND version = %s", (workflow_id, version)).fetchone():
        raise ApiError(409, "conflict", f"{workflow_id}@{version} already exists; releases are immutable")
    try:
        manifest_version = tomllib.loads(files.get("workflow.toml", "")).get("version")
    except tomllib.TOMLDecodeError:
        manifest_version = None
    if manifest_version != version:
        raise ApiError(409, "conflict", f"workflow.toml says version {manifest_version!r}; set it to {version!r} before publishing")

    result = cached_validation(conn, workflow_id, draft["files_hash"])
    if result is None:
        result = validate_draft(workflow_id, files, request_headers)
        store_validation(conn, workflow_id, draft["files_hash"], result)
    if not result["ok"]:
        failed = next((ch for ch in result["checks"] if not ch["ok"]), {"name": "graph", "message": "no graph"})
        raise ApiError(409, "conflict", f"the draft does not validate: {failed['name']}: {failed.get('message', 'failed')}")

    manifest = tomllib.loads(files["workflow.toml"])
    data = build_bundle({p: c.encode() for p, c in files.items()})
    release_id = f"rel_{uuid.uuid4().hex[:16]}"
    row = insert_release(conn, release_id=release_id, workflow_id=workflow_id, version=version, data=data,
                         published_at=datetime.now(UTC), published_by=body.get("publishedBy"), notes=body.get("notes"),
                         manifest=manifest, graph=result.get("graph"), fhash=draft["files_hash"])
    conn.execute("UPDATE drafts SET base_release_id = %s WHERE workflow_id = %s", (release_id, workflow_id))
    if body.get("channel"):
        point_channel(conn, workflow_id, body["channel"], release_id)
    conn.execute("UPDATE workflows SET updated_at = %s WHERE id = %s", (datetime.now(UTC), workflow_id))
    return to_api(row, channels_of(conn, workflow_id))
