"""Runner → hub sync (T14): register the run, post its events, queue while offline.

The run's `events.jsonl` *is* the offline queue: the hub stores each (runId, seq) once and counts
re-sent events as duplicates (contracts README), so the runner only remembers the last seq the hub
acknowledged (`hub.json` next to the events) and re-sends everything after it. A background thread
syncs while a command runs; when the hub is unreachable it backs off and the events stay queued
until the next command or `jigworks sync`.

Configuration (never stored in run.json): `JIGWORKS_HUB_URL`, `HUB_PASSWORD` (sent as
`X-Jigworks-Key`), optional `VERCEL_AUTOMATION_BYPASS_SECRET` for a protected preview.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jigworks_contracts as contracts

BATCH = 200


@dataclass(frozen=True)
class HubConfig:
    url: str
    key: str
    bypass: str | None = None
    timeout_s: float = 10.0

    @classmethod
    def from_env(cls, url: str | None = None) -> HubConfig | None:
        base = (url or os.environ.get("JIGWORKS_HUB_URL") or "").rstrip("/")
        key = os.environ.get("HUB_PASSWORD") or os.environ.get("JIGWORKS_HUB_KEY")
        if not base or not key:
            return None
        return cls(base, key, os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET") or None)


class HubError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status

    @property
    def offline(self) -> bool:
        """Network problems and 5xx are worth retrying; 4xx needs a human (wrong key, bad data)."""
        return self.status is None or self.status >= 500 or self.status == 429


class HubClient:
    def __init__(self, cfg: HubConfig) -> None:
        self.cfg = cfg

    def request(self, method: str, path: str, body: Any = None, raw: bool = False) -> Any:
        headers = {contracts.HUB_KEY_HEADER: self.cfg.key, "accept": "application/json"}
        if self.cfg.bypass:
            headers["x-vercel-protection-bypass"] = self.cfg.bypass
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["content-type"] = "application/json"
        req = urllib.request.Request(self.cfg.url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
                payload = resp.read()
                if raw:
                    return payload, dict(resp.headers)
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:500].decode(errors="replace")
            try:
                detail = json.loads(detail)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            if exc.code == 401:
                detail = "the hub refused the key (X-Jigworks-Key); check HUB_PASSWORD"
            raise HubError(exc.code, f"{method} {path} → {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise HubError(None, f"{method} {path}: hub unreachable ({exc})") from None


def run_create(started: dict[str, Any], run_id: str, at: str, steps_planned: int | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "runId": run_id,
        "workflowId": started["workflowId"],
        "release": started["release"],
        "digest": started["digest"],
        "authorEmail": started["authorEmail"],
        "models": started["models"],
        "adapter": started.get("adapter"),
        "title": started.get("title"),
        "releaseId": started.get("releaseId"),
        "stepsPlanned": steps_planned,
        "startedAt": at,
    }
    body = {k: v for k, v in body.items() if v is not None}
    contracts.assert_valid("RunCreate", body)
    return body


class HubSync:
    """Sync one run's event log to the hub. State lives in `<run dir>/hub.json`."""

    def __init__(self, run_dir: Path, run_id: str, cfg: HubConfig) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.client = HubClient(cfg)
        self.state_file = run_dir / "hub.json"
        self.state = self._load()
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except ValueError:
                pass
        return {"registered": False, "ackedSeq": -1}

    def _save(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2))
        tmp.replace(self.state_file)

    def _events(self) -> list[dict[str, Any]]:
        from .store import _read_jsonl

        return _read_jsonl(self.run_dir / "events.jsonl")

    def pending(self) -> int:
        return sum(1 for e in self._events() if e["seq"] > self.state["ackedSeq"])

    def sync(self) -> dict[str, Any]:
        """Send everything not acknowledged yet. Never raises; returns a small report."""
        with self._lock:
            events = self._events()
            todo = [e for e in events if e["seq"] > self.state["ackedSeq"]]
            report = {"sent": 0, "duplicates": 0, "pending": len(todo), "error": None}
            if not todo:
                return report
            try:
                if not self.state["registered"]:
                    first = events[0]
                    if first.get("kind") != "run_started":
                        raise HubError(422, "event log does not start with run_started")
                    self.client.request("POST", "/api/runs", run_create(first["runStarted"], self.run_id, first["at"],
                                                                        first.get("stepsPlanned")))
                    self.state["registered"] = True
                for i in range(0, len(todo), BATCH):
                    chunk = todo[i : i + BATCH]
                    result = self.client.request("POST", f"/api/runs/{self.run_id}/events", {"events": chunk})
                    self.state["ackedSeq"] = max(self.state["ackedSeq"], chunk[-1]["seq"])
                    report["sent"] += (result or {}).get("accepted", 0)
                    report["duplicates"] += (result or {}).get("duplicates", 0)
                self.state.pop("lastError", None)
            except HubError as exc:
                self.state["lastError"] = str(exc)
                self.state["lastErrorStatus"] = exc.status
                report["error"] = str(exc)
                report["offline"] = exc.offline
            finally:
                self.state["lastAttemptAt"] = time.time()
                self._save()
            report["pending"] = sum(1 for e in todo if e["seq"] > self.state["ackedSeq"])
            return report


class BackgroundSync:
    """Syncs while a command runs: woken by new events, backs off while the hub is down."""

    def __init__(self, sync: HubSync, min_interval_s: float = 0.5, max_backoff_s: float = 30.0) -> None:
        self.sync = sync
        self.min_interval_s = min_interval_s
        self.max_backoff_s = max_backoff_s
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._backoff = 0.0
        self.last: dict[str, Any] | None = None
        self._thread = threading.Thread(target=self._loop, name="jigworks-hub-sync", daemon=True)

    def start(self) -> BackgroundSync:
        self._thread.start()
        return self

    def notify(self, _event: Any = None) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=5.0)
            self._wake.clear()
            if self._stop.is_set():
                break
            self.last = self.sync.sync()
            if self.last.get("error"):
                self._backoff = min(max(self._backoff * 2, 1.0), self.max_backoff_s)
                self._stop.wait(self._backoff)
            else:
                self._backoff = 0.0
                self._stop.wait(self.min_interval_s)

    def close(self, final_timeout_s: float = 15.0) -> dict[str, Any]:
        """Stop the thread and make one last attempt (unless the hub was just found offline)."""
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=final_timeout_s)
        if self.last and self.last.get("error") and self.last.get("offline") and self._backoff >= 2:
            return {**self.last, "pending": self.sync.pending()}
        self.last = self.sync.sync()
        return self.last
