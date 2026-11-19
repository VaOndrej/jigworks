"""Settings read from the environment (never from the repo). See .env.example."""

from __future__ import annotations

import os
from dataclasses import dataclass

LOCAL_DATABASE_URL = "postgresql://jigworks:jigworks@localhost:54329/jigworks"


@dataclass(frozen=True)
class Settings:
    database_url: str
    hub_password: str | None
    blob_token: str | None
    bundle_store: str  # "blob" | "db"
    sandbox: str  # "vercel" | "fixture"
    on_vercel: bool


def settings() -> Settings:
    on_vercel = bool(os.getenv("VERCEL"))
    blob_token = os.getenv("BLOB_READ_WRITE_TOKEN") or None
    store = os.getenv("JIGWORKS_BUNDLE_STORE") or ("blob" if blob_token else "db")
    # Real Sandbox needs an OIDC token: on Vercel it arrives per request; locally `vercel env pull`
    # writes VERCEL_OIDC_TOKEN. Without one, validation uses the contract fixture graph.
    sandbox = os.getenv("JIGWORKS_SANDBOX") or ("vercel" if on_vercel or os.getenv("VERCEL_OIDC_TOKEN") else "fixture")
    return Settings(
        database_url=os.getenv("DATABASE_URL") or LOCAL_DATABASE_URL,
        hub_password=os.getenv("HUB_PASSWORD") or None,
        blob_token=blob_token,
        bundle_store=store,
        sandbox=sandbox,
        on_vercel=on_vercel,
    )
