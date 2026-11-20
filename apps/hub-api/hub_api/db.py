"""Postgres access (psycopg 3). One short connection per request: Vercel functions are
short-lived and Neon's pooled endpoint does the pooling."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import settings

SCHEMA_VERSION = "1"
# Timestamps leave the API as UTC ("…Z") whatever the server's TimeZone is. SET LOCAL (not a startup
# option) because Neon's pooled endpoint rejects startup options and pools per transaction.
UTC = "SET LOCAL TIME ZONE 'UTC'"
_ready: set[str] = set()
_ready_lock = threading.Lock()


def schema_sql() -> str:
    return (resources.files(__package__) / "schema.sql").read_text()


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """A transaction: commits on success, rolls back on error."""
    url = settings().database_url
    ensure_ready(url)
    with psycopg.connect(url, row_factory=dict_row) as conn:
        conn.execute(UTC)
        yield conn


def ensure_ready(url: str) -> None:
    """Apply the schema and seed the fixtures once per process (idempotent across processes)."""
    if url in _ready:
        return
    with _ready_lock:
        if url in _ready:
            return
        from .seed import seed_if_empty, sync_prices  # noqa: PLC0415 (import cycle)

        with psycopg.connect(url, row_factory=dict_row) as conn:
            conn.execute(UTC)
            conn.execute("SELECT pg_advisory_xact_lock(4242001)")
            conn.execute(schema_sql())
            seed_if_empty(conn)
            sync_prices(conn)
        _ready.add(url)


def forget_ready() -> None:
    """Tests: force ensure_ready to run again after the schema was dropped."""
    _ready.clear()


__all__ = ["Jsonb", "connect", "ensure_ready", "forget_ready"]
