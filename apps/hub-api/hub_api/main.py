"""Hub API entry point. Vercel keeps the public /api prefix, so routes include it.

Paths, request and response models follow packages/contracts/openapi.json (frozen after T02).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Body, FastAPI, Header, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse

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

from . import analytics, drafts, releases, runs, sample_data
from . import bundles as bundle_store
from .auth import SESSION_MAX_AGE, HubPasswordMiddleware, password_ok, session_token
from .config import settings
from .db import connect
from .errors import ApiError, install, not_found
from .ratelimit import client_ip, rate_limited, record_failure, retry_after
from .extensions import Overview, SampleDataRemoved

PUBLIC: list[dict] = []
ERRORS = {
    401: {"model": ErrorResponse, "description": "Missing or wrong session cookie / X-Jigworks-Key."},
    404: {"model": ErrorResponse, "description": "Not found."},
    422: {"model": ErrorResponse, "description": "Body does not match the contract."},
}
RATE_LIMITED = {"model": ErrorResponse, "description": "Too many wrong hub passwords from this IP; see Retry-After."}
WorkflowIdPath = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]*$", examples=["feature-development"])]
RunIdPath = Annotated[str, Path(min_length=1, max_length=128, examples=["run_123"])]
Channel = Literal["stable", "beta"]
LIVE = ("running", "waiting_human", "paused_usage_limit")

app = FastAPI(
    title="Jigworks Hub API",
    version="0.1.0",
    description=(
        "Jigworks hub. Every endpoint except `GET /api/health` and `POST /api/session` requires the "
        f"session cookie `{HUB_SESSION_COOKIE}` (set by `POST /api/session`) or the `{HUB_KEY_HEADER}` "
        "header carrying the hub password (HUB_PASSWORD). Engineers never log in: the runner reports "
        "`git config user.email` as author/approver. Costs are API equivalent."
    ),
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(HubPasswordMiddleware)
install(app)


# --- public -------------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse, tags=["public"], openapi_extra={"security": PUBLIC})
def health() -> HealthResponse:
    return HealthResponse(ok=True)


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


@app.post("/api/session", status_code=204, tags=["public"], openapi_extra={"security": PUBLIC},
          responses={401: ERRORS[401], 429: RATE_LIMITED,
                     204: {"description": f"Sets the HTTP-only `{HUB_SESSION_COOKIE}` cookie."}})
def create_session(body: SessionRequest, request: Request) -> Response:
    password = settings().hub_password
    ip = client_ip(request.headers, request.client.host if request.client else None)
    wait = retry_after(ip)
    if wait is not None:
        return rate_limited(wait)
    if not password or not password_ok(body.password, password):
        record_failure(ip)
        raise ApiError(401, "unauthorized", "wrong hub password")
    response = Response(status_code=204)
    response.set_cookie(HUB_SESSION_COOKIE, session_token(password), max_age=SESSION_MAX_AGE, httponly=True,
                        secure=_secure(request), samesite="lax", path="/")
    return response


@app.delete("/api/session", status_code=204, tags=["auth"], responses={204: {"description": "Clears the cookie."}})
def delete_session(request: Request) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(HUB_SESSION_COOKIE, path="/", httponly=True, secure=_secure(request), samesite="lax")
    return response


# --- workflows ----------------------------------------------------------------------------
@app.get("/api/workflows", response_model=WorkflowList, response_model_exclude_none=True, tags=["workflows"],
         responses={401: ERRORS[401]})
def list_workflows():
    week_ago = datetime.now(UTC) - timedelta(days=7)
    with connect() as conn:
        rows = conn.execute(
            """SELECT w.*, d.files_hash AS draft_hash,
                      (SELECT count(*) FROM runs r WHERE r.workflow_id = w.id AND r.started_at >= %s) AS runs7d
               FROM workflows w LEFT JOIN drafts d ON d.workflow_id = w.id ORDER BY w.id""",
            (week_ago,),
        ).fetchall()
        out = []
        for w in rows:
            rel = conn.execute(
                "SELECT version, files_hash FROM releases WHERE workflow_id = %s ORDER BY published_at DESC LIMIT 1", (w["id"],)
            ).fetchone()
            chans = conn.execute(
                "SELECT c.channel, r.version FROM channels c JOIN releases r ON r.id = c.release_id WHERE c.workflow_id = %s",
                (w["id"],),
            ).fetchall()
            item = {"id": w["id"], "name": w["name"], "description": w["description"], "ownerEmail": w["owner_email"],
                    "updatedAt": w["updated_at"], "channels": {c["channel"]: c["version"] for c in chans},
                    "hasUnpublishedDraft": rel is None or w["draft_hash"] != rel["files_hash"],
                    "runs7d": w["runs7d"], "source": w["source"]}
            if rel:
                item["latestVersion"] = rel["version"]
            out.append(item)
    return {"workflows": out}


@app.get("/api/workflows/{workflowId}/draft", response_model=Draft, response_model_exclude_none=True,
         tags=["workflows"], responses=ERRORS)
def get_draft(workflowId: WorkflowIdPath):
    with connect() as conn:
        return drafts.to_api(drafts.get(conn, workflowId), workflowId)


@app.put("/api/workflows/{workflowId}/draft", response_model=Draft, response_model_exclude_none=True,
         tags=["workflows"], responses=ERRORS,
         description="Full replacement of the draft's files (create, rename and delete files and folders). "
                     "An unknown workflow id creates the workflow; an empty file list fills it from the template.")
def put_draft(workflowId: WorkflowIdPath, body: DraftUpdate):
    files = [f.model_dump() for f in body.files]
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM workflows WHERE id = %s", (workflowId,)).fetchone()
        if not files and not exists:
            files = drafts.template_files(workflowId)
        return drafts.to_api(drafts.save(conn, workflowId, files), workflowId)


@app.post("/api/workflows/{workflowId}/validate", response_model=ValidationResult, response_model_exclude_none=True,
          tags=["workflows"], responses=ERRORS,
          description="Validate the current draft in isolation (Vercel Sandbox): manifest, syntax, imports, compile, "
                      "get_graph(). The published code never runs in the API process.")
def validate_draft(workflowId: WorkflowIdPath, request: Request):
    from .validation import validate_draft as run_validation  # noqa: PLC0415

    with connect() as conn:
        draft = drafts.get(conn, workflowId)
        cached = releases.cached_validation(conn, workflowId, draft["files_hash"])
    if cached is not None:
        return cached
    files = {f["path"]: f["content"] for f in draft["files"]}
    try:
        result = run_validation(workflowId, files, dict(request.headers))
    except Exception as exc:  # Sandbox unavailable: report it as a failed check, not a 500
        result = {"ok": False, "checks": [{"name": "imports", "ok": False,
                                           "message": f"Vercel Sandbox failed: {type(exc).__name__}: {exc}"[:500]}]}
        return result
    with connect() as conn:
        releases.store_validation(conn, workflowId, draft["files_hash"], result)
    return result


@app.post("/api/workflows/{workflowId}/publish", response_model=Release, response_model_exclude_none=True,
          status_code=201, tags=["workflows"],
          responses={**ERRORS, 409: {"model": ErrorResponse, "description": "Version already exists or the draft does not validate."}},
          description="Bundle the draft as a deterministic .zip, store it in Blob, compute the digest, create an "
                      "immutable release; optionally point a channel to it.")
def publish(workflowId: WorkflowIdPath, body: PublishRequest, request: Request):
    with connect() as conn:
        return releases.publish(conn, workflowId, body.model_dump(exclude_none=True), dict(request.headers))


@app.get("/api/workflows/{workflowId}/releases", response_model=ReleaseList, response_model_exclude_none=True,
         tags=["releases"], responses=ERRORS)
def list_releases(workflowId: WorkflowIdPath):
    with connect() as conn:
        return {"releases": releases.list_releases(conn, workflowId)}


@app.get("/api/workflows/{workflowId}/channels/{channel}", response_model=ChannelResolution,
         response_model_exclude_none=True, tags=["releases"], responses=ERRORS)
def resolve_channel(workflowId: WorkflowIdPath, channel: Channel):
    with connect() as conn:
        return releases.resolve_channel(conn, workflowId, channel)


@app.put("/api/workflows/{workflowId}/channels/{channel}", response_model=ChannelResolution,
         response_model_exclude_none=True, tags=["releases"], responses=ERRORS,
         description="Point a channel to a release (publish to a channel or roll back).")
def update_channel(workflowId: WorkflowIdPath, channel: Channel, body: ChannelUpdate):
    with connect() as conn:
        return releases.point_channel(conn, workflowId, channel, body.releaseId)


@app.get("/api/releases/{releaseId}/bundle", tags=["releases"], responses={
    **ERRORS,
    200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
          "description": "The release .zip. Header X-Jigworks-Digest: sha256:<hex> of these bytes; the client verifies it.",
          "headers": {"X-Jigworks-Digest": {"schema": {"type": "string"}}}},
})
def download_bundle(releaseId: Annotated[str, Path(min_length=1)]) -> Response:
    with connect() as conn:
        release = releases.get_release(conn, releaseId)
        data = bundle_store.get(conn, release)
    name = f"{release['workflow_id']}-{release['version']}.zip"
    return Response(data, media_type="application/zip", headers={
        "X-Jigworks-Digest": release["digest"], "Content-Disposition": f'attachment; filename="{name}"',
        "Cache-Control": "private, max-age=31536000, immutable"})


# --- runs ---------------------------------------------------------------------------------
def _with_cost(conn, summary: dict) -> dict:
    cost = analytics.run_costs(conn, [summary["runId"]]).get(summary["runId"], 0.0)
    return {**summary, "costUsd": cost}


@app.post("/api/runs", response_model=RunSummary, response_model_exclude_none=True, status_code=201, tags=["runs"],
          responses=ERRORS,
          description="Register a run with its pinned release. Idempotent on runId (a repeat returns the existing run).")
def create_run(body: RunCreate, response: Response):
    created = body.model_dump(mode="json", exclude_none=True)
    with connect() as conn:
        row, new = runs.register_run(conn, created)
        if not new:
            response.status_code = 200
        return _with_cost(conn, row["summary"])


def _encode_cursor(started_at: datetime, run_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([started_at.isoformat(), run_id]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        started, run_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return started, run_id
    except Exception as exc:
        raise ApiError(422, "validation_failed", "invalid cursor") from exc


@app.get("/api/runs", response_model=RunList, response_model_exclude_none=True, tags=["runs"], responses={401: ERRORS[401]})
def list_runs(
    workflowId: Annotated[str | None, Query()] = None,
    release: Annotated[str | None, Query(examples=["feature-development@1.3.0"])] = None,
    status: Annotated[str | None, Query(description="One status or a comma-separated list; `live` = running, waiting_human, paused_usage_limit.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
):
    clauses, params = [], []
    if workflowId:
        clauses.append("workflow_id = %s")
        params.append(workflowId)
    if release:
        clauses.append("release = %s")
        params.append(release)
    if status:
        wanted = [s for part in status.split(",") for s in (LIVE if part == "live" else (part,))]
        clauses.append("status = ANY(%s)")
        params.append(wanted)
    if cursor:
        started, run_id = _decode_cursor(cursor)
        clauses.append("(started_at, run_id) < (%s::timestamptz, %s)")
        params += [started, run_id]
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as conn:
        rows = conn.execute(f"SELECT run_id, started_at, summary FROM runs{where} ORDER BY started_at DESC, run_id DESC LIMIT %s",
                            [*params, limit + 1]).fetchall()
        page = rows[:limit]
        costs = analytics.run_costs(conn, [r["run_id"] for r in page])
    out: dict = {"runs": [{**r["summary"], "costUsd": costs.get(r["run_id"], 0.0)} for r in page]}
    if len(rows) > limit:
        out["nextCursor"] = _encode_cursor(page[-1]["started_at"], page[-1]["run_id"])
    return out


@app.get("/api/runs/{runId}", response_model=RunDetail, response_model_exclude_none=True, tags=["runs"], responses=ERRORS)
def get_run(runId: RunIdPath):
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = %s", (runId,)).fetchone()
        if row is None:
            raise not_found(f"run {runId}")
        wf, _, version = row["release"].partition("@")
        rel = conn.execute("SELECT graph FROM releases WHERE workflow_id = %s AND version = %s", (wf, version)).fetchone()
        out = {"summary": _with_cost(conn, row["summary"]), "audit": row["audit"]}
    if rel and rel["graph"]:
        out["graph"] = rel["graph"]
    return out


@app.post("/api/runs/{runId}/events", response_model=EventBatchResult, response_model_exclude_none=True, tags=["runs"],
          responses=ERRORS,
          description="Event ingest (batch). Each event needs runId == path runId and a seq; (runId, seq) is stored once, "
                      "re-sent events count as duplicates. Events for an unregistered run are rejected with 404.")
async def ingest_events(runId: RunIdPath, request: Request, body: Annotated[EventBatch, Body()]):
    # Validate the raw JSON against the schema (kind → payload rules), not the pydantic dump.
    raw = await request.json()

    def work():
        with connect() as conn:
            return runs.ingest(conn, runId, raw["events"])

    return await run_in_threadpool(work)


@app.get("/api/runs/{runId}/events", response_model=EventPage, response_model_exclude_none=True, tags=["runs"],
         responses=ERRORS, description="Polling fallback for the stream: events with seq > after, in seq order.")
def list_events(runId: RunIdPath, after: Annotated[int, Query(ge=-1)] = -1,
                limit: Annotated[int, Query(ge=1, le=1000)] = 500):
    with connect() as conn:
        return runs.events_after(conn, runId, after, limit)


SSE_SECONDS = float(os.getenv("JIGWORKS_SSE_SECONDS", "25"))
SSE_POLL = float(os.getenv("JIGWORKS_SSE_POLL", "1"))


@app.get("/api/runs/{runId}/events/stream", tags=["runs"], responses={
    **ERRORS,
    200: {"content": {"text/event-stream": {"schema": {"type": "string"}}},
          "description": "SSE. Each message: `id: <seq>`, `event: <kind>`, `data: <RunEvent JSON>`. Vercel functions time "
                         "out, so clients reconnect with Last-Event-ID (or ?after=) or fall back to polling."},
})
async def stream_events(runId: RunIdPath, after: Annotated[int, Query(ge=-1)] = -1,
                        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None) -> Response:
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    def page(cursor: int) -> dict:
        with connect() as conn:
            return runs.events_after(conn, runId, cursor, 500)

    first = await run_in_threadpool(page, start)  # 404 before the stream starts

    async def gen():
        cursor, batch = start, first
        loop = asyncio.get_running_loop()
        deadline = loop.time() + SSE_SECONDS
        yield "retry: 2000\n\n"
        while True:
            for ev in batch["events"]:
                cursor = ev["seq"]
                yield f"id: {ev['seq']}\nevent: {ev.get('kind') or 'node_status'}\ndata: {json.dumps(ev)}\n\n"
            if loop.time() >= deadline:
                return  # the client reconnects with Last-Event-ID
            await asyncio.sleep(SSE_POLL)
            yield ": keepalive\n\n"
            batch = await run_in_threadpool(page, cursor)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- analytics ----------------------------------------------------------------------------
@app.get("/api/analytics/usage", response_model=UsageReport, response_model_exclude_none=True, tags=["analytics"],
         responses={401: ERRORS[401]},
         description="Raw tokens grouped by release, model, node or day; cost computed at read time from the price table (API equivalent).")
def usage_report(
    groupBy: Annotated[Literal["release", "model", "node", "day"], Query()] = "release",
    workflowId: Annotated[str | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
):
    with connect() as conn:
        return analytics.usage_report(conn, groupBy, workflowId, _aware(from_), _aware(to))


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


@app.get("/api/analytics/releases", response_model=ReleaseComparison, response_model_exclude_none=True,
         tags=["analytics"], responses={401: ERRORS[401]},
         description="Version comparison per release: runs, success rate, fix loops, follow-up prompts, cost.")
def release_comparison(workflowId: Annotated[str, Query()]):
    with connect() as conn:
        return analytics.release_comparison(conn, workflowId)


@app.get("/api/analytics/outcomes", response_model=OutcomeReport, response_model_exclude_none=True,
         tags=["analytics"], responses={401: ERRORS[401]},
         description="PLANNED human-delta outcomes; returns sample data (sample=true) until capture is built.")
def outcomes(workflowId: Annotated[str | None, Query()] = None):
    with connect() as conn:
        return analytics.outcomes(conn, workflowId)


@app.get("/api/analytics/overview", response_model=Overview, response_model_by_alias=True, tags=["analytics"],
         responses={401: ERRORS[401]},
         description="Hub-only (not in the frozen contract): key numbers for the Workflows and Runs & analytics tabs. "
                     "Default period: the last 7 days.")
def overview(
    workflowId: Annotated[str | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
):
    with connect() as conn:
        return analytics.overview(conn, workflowId, _aware(from_), _aware(to))


@app.post("/api/admin/remove-sample-data", response_model=SampleDataRemoved, tags=["admin"],
          responses={401: ERRORS[401]},
          description="Hub-only (not in the frozen contract): delete the sample workflow releases and runs the hub "
                      "seeded from the contract fixtures. Real releases and runs stay; the hub does not seed again. "
                      "Idempotent.")
def remove_sample_data():
    with connect() as conn:
        counts, urls = sample_data.remove(conn)
    # After the commit: a failed Blob delete leaves orphaned files, never a release without its bytes.
    bundle_store.delete_blobs(urls)
    return counts


# --- OpenAPI ------------------------------------------------------------------------------
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
