"""A small fake of the hub API for LOCAL's tests (T14, T15, e2e without the preview).

Implements the endpoints the runner and the extension use, with the shapes from
packages/contracts/openapi.json, and validates every request body against the frozen contracts:

  GET  /api/health
  POST /api/runs                              RunCreate (idempotent on runId)
  POST /api/runs/{id}/events                  EventBatch → EventBatchResult, dedupe on (runId, seq)
  GET  /api/runs/{id}/events                  EventPage
  GET  /api/workflows/{id}/channels/{name}    ChannelResolution
  PUT  /api/workflows/{id}/channels/{name}    ChannelUpdate {"releaseId": …}
  GET  /api/releases/{id}/bundle              bytes + X-Jigworks-Digest

Test controls (not part of the hub API): POST /_test/release (body: zip bytes, query workflowId,
version, releaseId, channel?) publishes a release; POST /_test/down?on=1|0 switches the hub off
(503) and on; POST /_test/down_after?node=…&status=… goes down once such an event was ingested.

    python -m jigworks_runner.testing.fakehub --key test-key      # prints {"url": …} and serves
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import jigworks_contracts as contracts
from jigworks_contracts import bundle as cbundle


class FakeHub:
    def __init__(self, key: str = "test-key") -> None:
        self.key = key
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: dict[str, dict[int, dict[str, Any]]] = {}
        self.releases: dict[str, dict[str, Any]] = {}
        self.channels: dict[tuple[str, str], str] = {}
        self.down = False
        self.down_after: tuple[str, str] | None = None
        self.requests: list[tuple[str, str, int]] = []
        self.lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None

    # -- lifecycle ---------------------------------------------------------------------------

    def start(self, port: int = 0) -> str:
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # quiet
                pass

            def do_GET(self) -> None:
                hub._handle(self, "GET")

            def do_POST(self) -> None:
                hub._handle(self, "POST")

            def do_PUT(self) -> None:
                hub._handle(self, "PUT")

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.url

    @property
    def url(self) -> str:
        assert self._server
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    # -- test helpers ------------------------------------------------------------------------

    def publish(self, workflow_id: str, version: str, data: bytes, release_id: str | None = None,
                channel: str | None = None) -> dict[str, Any]:
        rid = release_id or f"rel_{workflow_id}_{version}".replace(".", "_").replace("-", "_")
        rel = {"releaseId": rid, "workflowId": workflow_id, "version": version, "digest": cbundle.digest(data), "data": data}
        with self.lock:
            self.releases[rid] = rel
            if channel:
                self.channels[(workflow_id, channel)] = rid
        return {k: v for k, v in rel.items() if k != "data"}

    def seqs(self, run_id: str) -> list[int]:
        return sorted(self.events.get(run_id, {}))

    # -- HTTP ----------------------------------------------------------------------------------

    def _send(self, h: BaseHTTPRequestHandler, status: int, body: Any = None, raw: bytes | None = None,
              headers: dict[str, str] | None = None) -> None:
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        h.send_response(status)
        h.send_header("content-type", "application/zip" if raw is not None else "application/json")
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        h.send_header("content-length", str(len(payload)))
        h.end_headers()
        h.wfile.write(payload)

    def _error(self, h: BaseHTTPRequestHandler, status: int, code: str, message: str) -> None:
        self._send(h, status, {"error": {"code": code, "message": message}})

    def _handle(self, h: BaseHTTPRequestHandler, method: str) -> None:
        url = urlparse(h.path)
        path, query = url.path, parse_qs(url.query)
        length = int(h.headers.get("content-length") or 0)
        raw = h.rfile.read(length) if length else b""
        status_box: list[int] = []

        def send(status: int, *a: Any, **kw: Any) -> None:
            status_box.append(status)
            self._send(h, status, *a, **kw)

        try:
            if path.startswith("/_test/"):
                return self._control(path, query, raw, send)
            if self.down:
                return send(503, {"error": {"code": "hub_unreachable", "message": "fake hub is down"}})
            if path == "/api/health":
                return send(200, {"ok": True})
            if h.headers.get(contracts.HUB_KEY_HEADER) != self.key:
                status_box.append(401)
                return self._error(h, 401, "unauthorized", "missing or wrong X-Jigworks-Key")
            body = json.loads(raw) if raw and h.headers.get("content-type", "").startswith("application/json") else None
            if method == "GET" and path == "/api/workflows":
                ids = sorted({r["workflowId"] for r in self.releases.values()})
                listing = {"workflows": [
                    {"id": wid, "name": wid, "updatedAt": "2026-11-19T00:00:00Z", "source": "hub",
                     "channels": {ch: self.releases[rid]["version"] for (w, ch), rid in self.channels.items() if w == wid}}
                    for wid in ids]}
                contracts.assert_valid("WorkflowList", listing)
                return send(200, listing)
            if method == "POST" and path == "/api/runs":
                errors = contracts.validate("RunCreate", body)
                if errors:
                    status_box.append(422)
                    return self._error(h, 422, "validation_failed", "; ".join(errors))
                with self.lock:
                    new = body["runId"] not in self.runs
                    self.runs.setdefault(body["runId"], body)
                    self.events.setdefault(body["runId"], {})
                return send(201 if new else 200, {"runId": body["runId"]})
            m = re.fullmatch(r"/api/runs/([^/]+)/events", path)
            if m and method == "POST":
                run_id = m.group(1)
                errors = contracts.validate("EventBatch", body)
                errors += [f"runId {e.get('runId')} != {run_id}" for e in (body or {}).get("events", []) if e.get("runId") != run_id]
                if errors:
                    status_box.append(422)
                    return self._error(h, 422, "validation_failed", "; ".join(errors[:5]))
                with self.lock:
                    if run_id not in self.runs:
                        status_box.append(404)
                        return self._error(h, 404, "not_found", f"run {run_id}")
                    accepted = duplicates = 0
                    for e in body["events"]:
                        if e["seq"] in self.events[run_id]:
                            duplicates += 1
                        else:
                            self.events[run_id][e["seq"]] = e
                            accepted += 1
                        if self.down_after and (e.get("node"), e.get("status")) == self.down_after:
                            self.down, self.down_after = True, None
                    result = {"accepted": accepted, "duplicates": duplicates, "lastSeq": max(self.events[run_id])}
                contracts.assert_valid("EventBatchResult", result)
                return send(200, result)
            if m and method == "GET":
                run_id = m.group(1)
                events = [self.events.get(run_id, {})[s] for s in self.seqs(run_id)]
                return send(200, {"events": events})
            m = re.fullmatch(r"/api/workflows/([^/]+)/channels/([^/]+)", path)
            if m and method == "GET":
                rid = self.channels.get((m.group(1), m.group(2)))
                if not rid:
                    status_box.append(404)
                    return self._error(h, 404, "not_found", f"channel {m.group(2)} of {m.group(1)}")
                rel = self.releases[rid]
                res = {"workflowId": rel["workflowId"], "channel": m.group(2), "releaseId": rid, "version": rel["version"],
                       "digest": rel["digest"], "bundleUrl": f"/api/releases/{rid}/bundle"}
                contracts.assert_valid("ChannelResolution", res)
                return send(200, res)
            if m and method == "PUT":
                rid = (body or {}).get("releaseId")
                if rid not in self.releases:
                    status_box.append(404)
                    return self._error(h, 404, "not_found", f"release {rid}")
                self.channels[(m.group(1), m.group(2))] = rid
                return send(200, {"workflowId": m.group(1), "channel": m.group(2), "releaseId": rid})
            m = re.fullmatch(r"/api/releases/([^/]+)/bundle", path)
            if m and method == "GET":
                rel = self.releases.get(m.group(1))
                if not rel:
                    status_box.append(404)
                    return self._error(h, 404, "not_found", f"release {m.group(1)}")
                return send(200, raw=rel["data"], headers={"X-Jigworks-Digest": rel["digest"]})
            status_box.append(404)
            return self._error(h, 404, "not_found", f"{method} {path}")
        finally:
            self.requests.append((method, path, status_box[-1] if status_box else 0))

    def _control(self, path: str, query: dict[str, list[str]], raw: bytes, send: Any) -> None:
        q = {k: v[0] for k, v in query.items()}
        if path == "/_test/down":
            self.down = q.get("on", "1") == "1"
            return send(200, {"down": self.down})
        if path == "/_test/down_after":
            self.down_after = (q["node"], q.get("status", "running"))
            return send(200, {"downAfter": list(self.down_after)})
        if path == "/_test/release":
            return send(200, self.publish(q["workflowId"], q["version"], raw, q.get("releaseId"), q.get("channel")))
        if path == "/_test/events":
            return send(200, {rid: self.seqs(rid) for rid in self.events})
        return send(404, {"error": {"code": "not_found", "message": path}})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--key", default="test-key")
    p.add_argument("--port", type=int, default=0)
    args = p.parse_args()
    hub = FakeHub(args.key)
    print(json.dumps({"url": hub.start(args.port)}), flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
