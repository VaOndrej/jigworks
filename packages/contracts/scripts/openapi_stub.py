"""FastAPI stub that declares the hub API with the generated models, only to emit openapi.json.

The routes have no implementation. HUB builds the real app in apps/hub-api (T12) with the
same paths and models and then regenerates openapi.json from it.

Auth rule (design.md §8 Access, docs/two-agent-build.md §10): every endpoint except
GET /api/health and POST /api/session needs either the session cookie set by
POST /api/session or the X-Jigworks-Key header carrying the hub password.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Body, FastAPI, Path, Query, Response
from fastapi.openapi.utils import get_openapi

from jigworks_contracts import HUB_KEY_HEADER, HUB_SESSION_COOKIE
from jigworks_contracts.models import (
    ChannelResolution,
    ChannelUpdate,
    Draft,
    DraftUpdate,
    ErrorResponse,
    EventBatch,
    EventBatchResult,
    EventPage,
    HealthResponse,
    OutcomeReport,
    PublishRequest,
    Release,
    ReleaseComparison,
    ReleaseList,
    RunCreate,
    RunDetail,
    RunList,
    RunSummary,
    SessionRequest,
    UsageReport,
    ValidationResult,
    WorkflowList,
)

PUBLIC: list[dict] = []  # openapi `security: []` = no auth
ERRORS = {
    401: {"model": ErrorResponse, "description": "Missing or wrong session cookie / X-Jigworks-Key."},
    404: {"model": ErrorResponse, "description": "Not found."},
    422: {"model": ErrorResponse, "description": "Body does not match the contract."},
}

WorkflowIdPath = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]*$", examples=["feature-development"])]
RunIdPath = Annotated[str, Path(min_length=1, max_length=128, examples=["run_123"])]


def build_app() -> FastAPI:
    app = FastAPI(
        title="Jigworks Hub API",
        version="0.1.0",
        description=(
            "Contract for the Jigworks hub (frozen after T02). Every endpoint except "
            "`GET /api/health` and `POST /api/session` requires the session cookie "
            f"`{HUB_SESSION_COOKIE}` (set by `POST /api/session`) or the `{HUB_KEY_HEADER}` "
            "header carrying the hub password (HUB_PASSWORD). Engineers never log in: the "
            "runner reports `git config user.email` as author/approver. Costs are API equivalent."
        ),
    )

    # --- public ---------------------------------------------------------------
    @app.get("/api/health", response_model=HealthResponse, tags=["public"], openapi_extra={"security": PUBLIC})
    def health(): ...

    @app.post(
        "/api/session",
        status_code=204,
        tags=["public"],
        openapi_extra={"security": PUBLIC},
        responses={401: ERRORS[401], 204: {"description": f"Sets the HTTP-only `{HUB_SESSION_COOKIE}` cookie."}},
    )
    def create_session(body: SessionRequest) -> Response: ...

    @app.delete("/api/session", status_code=204, tags=["auth"], responses={204: {"description": "Clears the cookie."}})
    def delete_session() -> Response: ...

    # --- workflows ------------------------------------------------------------
    @app.get("/api/workflows", response_model=WorkflowList, tags=["workflows"], responses={401: ERRORS[401]})
    def list_workflows(): ...

    @app.get("/api/workflows/{workflowId}/draft", response_model=Draft, tags=["workflows"], responses=ERRORS)
    def get_draft(workflowId: WorkflowIdPath): ...

    @app.put("/api/workflows/{workflowId}/draft", response_model=Draft, tags=["workflows"], responses=ERRORS)
    def put_draft(workflowId: WorkflowIdPath, body: DraftUpdate): ...

    @app.post(
        "/api/workflows/{workflowId}/validate",
        response_model=ValidationResult,
        tags=["workflows"],
        responses=ERRORS,
        description="Validate the current draft in isolation (Vercel Sandbox): manifest, syntax, imports, compile, get_graph(). The published code never runs in the API process.",
    )
    def validate_draft(workflowId: WorkflowIdPath): ...

    @app.post(
        "/api/workflows/{workflowId}/publish",
        response_model=Release,
        status_code=201,
        tags=["workflows"],
        responses={**ERRORS, 409: {"model": ErrorResponse, "description": "Version already exists or the draft does not validate."}},
        description="Bundle the draft as a deterministic .zip, store it in Blob, compute the digest, create an immutable release; optionally point a channel to it.",
    )
    def publish(workflowId: WorkflowIdPath, body: PublishRequest): ...

    @app.get("/api/workflows/{workflowId}/releases", response_model=ReleaseList, tags=["releases"], responses=ERRORS)
    def list_releases(workflowId: WorkflowIdPath): ...

    @app.get("/api/workflows/{workflowId}/channels/{channel}", response_model=ChannelResolution, tags=["releases"], responses=ERRORS)
    def resolve_channel(workflowId: WorkflowIdPath, channel: Literal["stable", "beta"]): ...

    @app.put(
        "/api/workflows/{workflowId}/channels/{channel}",
        response_model=ChannelResolution,
        tags=["releases"],
        responses=ERRORS,
        description="Point a channel to a release (publish to a channel or roll back).",
    )
    def update_channel(workflowId: WorkflowIdPath, channel: Literal["stable", "beta"], body: ChannelUpdate): ...

    @app.get(
        "/api/releases/{releaseId}/bundle",
        tags=["releases"],
        responses={
            **ERRORS,
            200: {
                "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
                "description": "The release .zip. Header X-Jigworks-Digest: sha256:<hex> of these bytes; the client verifies it.",
                "headers": {"X-Jigworks-Digest": {"schema": {"type": "string"}}},
            },
        },
    )
    def download_bundle(releaseId: Annotated[str, Path(min_length=1)]) -> Response: ...

    # --- runs -----------------------------------------------------------------
    @app.post(
        "/api/runs",
        response_model=RunSummary,
        status_code=201,
        tags=["runs"],
        responses=ERRORS,
        description="Register a run with its pinned release. Idempotent on runId (a repeat returns the existing run).",
    )
    def create_run(body: RunCreate): ...

    @app.get("/api/runs", response_model=RunList, tags=["runs"], responses={401: ERRORS[401]})
    def list_runs(
        workflowId: Annotated[str | None, Query()] = None,
        release: Annotated[str | None, Query(examples=["feature-development@1.3.0"])] = None,
        status: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query()] = None,
    ): ...

    @app.get("/api/runs/{runId}", response_model=RunDetail, tags=["runs"], responses=ERRORS)
    def get_run(runId: RunIdPath): ...

    @app.post(
        "/api/runs/{runId}/events",
        response_model=EventBatchResult,
        tags=["runs"],
        responses=ERRORS,
        description="Event ingest (batch). Each event needs runId == path runId and a seq; (runId, seq) is stored once, re-sent events count as duplicates. Events for an unregistered run are rejected with 404.",
    )
    def ingest_events(runId: RunIdPath, body: Annotated[EventBatch, Body()]): ...

    @app.get(
        "/api/runs/{runId}/events",
        response_model=EventPage,
        tags=["runs"],
        responses=ERRORS,
        description="Polling fallback for the stream: events with seq > after, in seq order.",
    )
    def list_events(runId: RunIdPath, after: Annotated[int, Query(ge=-1)] = -1, limit: Annotated[int, Query(ge=1, le=1000)] = 500): ...

    @app.get(
        "/api/runs/{runId}/events/stream",
        tags=["runs"],
        responses={
            **ERRORS,
            200: {
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
                "description": "SSE. Each message: `id: <seq>`, `event: <kind>`, `data: <RunEvent JSON>`. Vercel functions time out, so clients reconnect with Last-Event-ID (or ?after=) or fall back to polling.",
            },
        },
    )
    def stream_events(runId: RunIdPath, after: Annotated[int, Query(ge=-1)] = -1) -> Response: ...

    # --- analytics ------------------------------------------------------------
    @app.get(
        "/api/analytics/usage",
        response_model=UsageReport,
        tags=["analytics"],
        responses={401: ERRORS[401]},
        description="Raw tokens grouped by release, model, node or day; cost computed at read time from the price table (API equivalent).",
    )
    def usage_report(
        groupBy: Annotated[Literal["release", "model", "node", "day"], Query()] = "release",
        workflowId: Annotated[str | None, Query()] = None,
        from_: Annotated[str | None, Query(alias="from")] = None,
        to: Annotated[str | None, Query()] = None,
    ): ...

    @app.get(
        "/api/analytics/releases",
        response_model=ReleaseComparison,
        tags=["analytics"],
        responses={401: ERRORS[401]},
        description="Version comparison per release: runs, success rate, fix loops, follow-up prompts, cost.",
    )
    def release_comparison(workflowId: Annotated[str, Query()]): ...

    @app.get(
        "/api/analytics/outcomes",
        response_model=OutcomeReport,
        tags=["analytics"],
        responses={401: ERRORS[401]},
        description="PLANNED human-delta outcomes; returns sample data (sample=true) until capture is built.",
    )
    def outcomes(workflowId: Annotated[str | None, Query()] = None): ...

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        spec = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        spec.setdefault("components", {})["securitySchemes"] = {
            "hubKey": {"type": "apiKey", "in": "header", "name": HUB_KEY_HEADER},
            "hubSession": {"type": "apiKey", "in": "cookie", "name": HUB_SESSION_COOKIE},
        }
        spec["security"] = [{"hubKey": []}, {"hubSession": []}]
        app.openapi_schema = spec
        return spec

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app
