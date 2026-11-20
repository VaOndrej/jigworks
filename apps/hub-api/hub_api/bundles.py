"""Release bundle storage: Vercel Blob (private store) when BLOB_READ_WRITE_TOKEN is set,
otherwise a bytea table (local development and tests). The digest is checked on every read."""

from __future__ import annotations

import psycopg

from jigworks_contracts.bundle import digest

from .config import settings
from .errors import ApiError


def blob_pathname(workflow_id: str, version: str, bundle_digest: str) -> str:
    return f"bundles/{workflow_id}/{workflow_id}-{version}-{bundle_digest.removeprefix('sha256:')[:16]}.zip"


def put(conn: psycopg.Connection, release_id: str, pathname: str, data: bytes) -> str | None:
    """Store the bytes; returns the Blob URL, or None when stored in Postgres.
    Call after the releases row exists (the bundles table references it)."""
    if settings().bundle_store == "blob":
        from vercel.blob.sync import put_blob  # noqa: PLC0415

        # Same pathname always means the same bytes (the digest is in the name), so overwrite is safe.
        result = put_blob(pathname, data, access="private", content_type="application/zip", allow_overwrite=True)
        return result.url
    conn.execute(
        "INSERT INTO bundles (release_id, data) VALUES (%s, %s) ON CONFLICT (release_id) DO UPDATE SET data = EXCLUDED.data",
        (release_id, data),
    )
    return None


def get(conn: psycopg.Connection, release: dict) -> bytes:
    if release["bundle_url"]:
        from vercel.blob.sync import get_blob  # noqa: PLC0415

        data = bytes(get_blob(release["bundle_url"], access="private").body)
    else:
        row = conn.execute("SELECT data FROM bundles WHERE release_id = %s", (release["id"],)).fetchone()
        if row is None:
            raise ApiError(404, "not_found", f"bundle of release {release['id']} not found")
        data = bytes(row["data"])
    if digest(data) != release["digest"]:
        raise ApiError(500, "digest_mismatch", f"stored bundle of {release['id']} does not match its digest")
    return data
