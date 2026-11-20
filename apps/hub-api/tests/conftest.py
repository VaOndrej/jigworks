"""API tests run against the local Docker Postgres (docker compose -p jigworks up -d --wait db),
in a separate database `jigworks_test` that is reset before every test."""

from __future__ import annotations

import os

import psycopg
import pytest

from hub_api.config import LOCAL_DATABASE_URL

TEST_DB = "jigworks_test"
TEST_URL = LOCAL_DATABASE_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"
PASSWORD = "test-hub-password"


def pytest_configure(config):
    os.environ.update({
        "DATABASE_URL": TEST_URL,
        "HUB_PASSWORD": PASSWORD,
        "JIGWORKS_SANDBOX": "fixture",
        "JIGWORKS_BUNDLE_STORE": "db",
        "JIGWORKS_SSE_SECONDS": "1",
        "JIGWORKS_SSE_POLL": "0.2",
    })
    os.environ.pop("VERCEL", None)
    os.environ.pop("BLOB_READ_WRITE_TOKEN", None)


def _admin_url() -> str:
    return os.getenv("JIGWORKS_TEST_ADMIN_URL", LOCAL_DATABASE_URL)


@pytest.fixture(scope="session")
def database():
    try:
        with psycopg.connect(_admin_url(), autocommit=True, connect_timeout=3) as conn:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone():
                conn.execute(f"CREATE DATABASE {TEST_DB}")
    except psycopg.OperationalError as exc:
        pytest.fail(f"local Postgres is not running (docker compose -p jigworks up -d --wait db): {exc}")
    return TEST_URL


@pytest.fixture()
def fresh_db(database):
    from hub_api.db import forget_ready

    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    forget_ready()
    return database


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient

    from hub_api.main import app

    return TestClient(app, headers={"X-Jigworks-Key": PASSWORD})


@pytest.fixture()
def anon(fresh_db):
    from fastapi.testclient import TestClient

    from hub_api.main import app

    return TestClient(app)
