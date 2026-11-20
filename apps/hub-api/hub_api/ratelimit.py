"""Rate limit on guessing the hub password, per client IP.

Counts failed password attempts (POST /api/session and a wrong X-Jigworks-Key) in Postgres,
because Vercel runs many short-lived function instances that share no memory. Once an IP has
MAX_FAILURES failures inside WINDOW, every password attempt from it gets 429, even the right
password, until its oldest failure leaves the window.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from .config import settings
from .db import connect
from .errors import error_response

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60


def client_ip(headers: Mapping[str, str], peer: str | None) -> str:
    """The caller's IP. Vercel's edge overwrites x-real-ip / x-forwarded-for with the real client
    address, so they are trusted only there (or with JIGWORKS_TRUST_PROXY=1 behind another proxy);
    anywhere else a client could rotate them to dodge the limit."""
    if settings().on_vercel or os.getenv("JIGWORKS_TRUST_PROXY") == "1":
        real = headers.get("x-real-ip") or headers.get("x-forwarded-for", "").split(",")[0]
        if real.strip():
            return real.strip()
    return peer or "unknown"


def retry_after(ip: str) -> int | None:
    """Seconds until `ip` may try a password again, or None when it is not blocked."""
    with connect() as conn:
        row = conn.execute(
            """SELECT count(*) AS n,
                      ceil(extract(epoch FROM min(at) + make_interval(secs => %s) - now()))::int AS wait
                 FROM auth_failures WHERE ip = %s AND at > now() - make_interval(secs => %s)""",
            (WINDOW_SECONDS, ip, WINDOW_SECONDS),
        ).fetchone()
    if row["n"] < MAX_FAILURES:
        return None
    return max(int(row["wait"] or 1), 1)


def record_failure(ip: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM auth_failures WHERE at <= now() - make_interval(secs => %s)", (WINDOW_SECONDS,))
        conn.execute("INSERT INTO auth_failures (ip) VALUES (%s)", (ip,))


def rate_limited(wait: int):
    return error_response(429, "rate_limited", f"too many wrong hub passwords; try again in {wait} s",
                          headers={"Retry-After": str(wait)})
