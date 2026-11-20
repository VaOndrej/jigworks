"""Guessing the hub password is rate limited per client IP (morning review §5.1).

The password can be tried two ways: POST /api/session and the X-Jigworks-Key header on any
endpoint. Both count, and both are blocked once an IP is over the limit, even with the
right password, until the window has passed.
"""

from __future__ import annotations

import jigworks_contracts as c
import pytest
from .conftest import PASSWORD

from hub_api.ratelimit import MAX_FAILURES


@pytest.fixture()
def proxied(anon, monkeypatch):
    monkeypatch.setenv("JIGWORKS_TRUST_PROXY", "1")
    return anon


def login(client, password, ip="203.0.113.7"):
    return client.post("/api/session", json={"password": password}, headers={"x-real-ip": ip})


def test_wrong_passwords_are_blocked_after_the_limit_even_the_right_one(proxied):
    for _ in range(MAX_FAILURES):
        assert login(proxied, "guess").status_code == 401
    r = login(proxied, PASSWORD)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert c.validate("ErrorResponse", r.json()) == []
    assert 0 < int(r.headers["retry-after"]) <= 15 * 60


def test_the_limit_is_per_client_ip(proxied):
    for _ in range(MAX_FAILURES):
        login(proxied, "guess", ip="203.0.113.7")
    assert login(proxied, PASSWORD, ip="198.51.100.9").status_code == 204


def test_a_wrong_key_header_counts_and_is_blocked_too(proxied):
    for _ in range(MAX_FAILURES):
        r = proxied.get("/api/workflows", headers={"X-Jigworks-Key": "guess", "x-real-ip": "203.0.113.7"})
        assert r.status_code == 401
    r = proxied.get("/api/workflows", headers={"X-Jigworks-Key": PASSWORD, "x-real-ip": "203.0.113.7"})
    assert r.status_code == 429
    assert login(proxied, PASSWORD).status_code == 429  # same counter for both ways in


def test_failures_below_the_limit_do_not_block(proxied):
    for _ in range(MAX_FAILURES - 1):
        login(proxied, "guess")
    assert login(proxied, PASSWORD).status_code == 204
    assert proxied.get("/api/workflows").status_code == 200


def test_requests_without_a_password_do_not_count(proxied):
    for _ in range(MAX_FAILURES + 5):
        assert proxied.get("/api/workflows", headers={"x-real-ip": "203.0.113.7"}).status_code == 401
    assert login(proxied, PASSWORD).status_code == 204


def test_forwarded_headers_are_ignored_off_vercel_unless_trusted(anon):
    # Without a trusted proxy a client could rotate x-real-ip to dodge the limit.
    for i in range(MAX_FAILURES):
        login(anon, "guess", ip=f"203.0.113.{i}")
    assert login(anon, PASSWORD, ip="198.51.100.9").status_code == 429
