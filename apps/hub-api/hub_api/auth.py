"""Hub password (docs/two-agent-build.md §10.2).

Every endpoint except the public ones needs the HTTP-only session cookie set by
POST /api/session, or X-Jigworks-Key equal to HUB_PASSWORD. The cookie holds an HMAC of the
password, never the password itself; changing HUB_PASSWORD logs every browser out.
"""

from __future__ import annotations

import hashlib
import hmac

from jigworks_contracts import HUB_KEY_HEADER, HUB_SESSION_COOKIE, PUBLIC_ENDPOINTS
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import settings
from .errors import error_response

SESSION_MAX_AGE = 30 * 24 * 3600
PUBLIC = {tuple(e.split(" ", 1)) for e in PUBLIC_ENDPOINTS}


def session_token(password: str) -> str:
    return hmac.new(password.encode(), b"jigworks-session-v1", hashlib.sha256).hexdigest()


def password_ok(candidate: str | None, password: str) -> bool:
    return candidate is not None and hmac.compare_digest(candidate.encode(), password.encode())


def is_authorized(headers: dict[str, str], cookies: dict[str, str]) -> bool:
    password = settings().hub_password
    if not password:
        return False  # fail closed when the env var is missing
    if password_ok(headers.get(HUB_KEY_HEADER.lower()), password):
        return True
    cookie = cookies.get(HUB_SESSION_COOKIE)
    return cookie is not None and hmac.compare_digest(cookie, session_token(password))


def _cookies(raw: str) -> dict[str, str]:
    out = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


class HubPasswordMiddleware:
    """Pure ASGI middleware, so streaming responses (SSE) pass through untouched."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method, path = scope["method"], scope["path"]
        if (method, path) in PUBLIC or not path.startswith("/api/"):
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        if is_authorized(headers, _cookies(headers.get("cookie", ""))):
            return await self.app(scope, receive, send)
        message = (
            "hub password is not configured (HUB_PASSWORD)"
            if not settings().hub_password
            else f"missing or wrong session cookie / {HUB_KEY_HEADER}"
        )
        response = error_response(401, "unauthorized", message)
        await response(scope, receive, send)
