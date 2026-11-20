"""On-disk state of local runs.

```
<home>/                      default: <repo root>/.jigworks (ignored by its own .gitignore)
  runs/<runId>/
    run.json                 what the run is: package copy, digest, worktree, adapter, author, weights
    events.jsonl             every RunEvent, in seq order (the source of truth; the ledger is replayed from it)
    nodes.jsonl              journal of finished nodes (commit + state update), for resume
    checkpoints.sqlite       LangGraph checkpoints (SqliteSaver)
    audit.jsonl              AuditRecord after every command (last line = current)
    package/                 the pinned workflow package (a running task never changes version)
    lock                     held while a command works on the run
  worktrees/<runId>/         the run's git worktree, branch jigworks/<runId>
```
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from .events import Event


def new_run_id() -> str:
    return f"run_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"


def default_home(repo_root: Path) -> Path:
    env = os.environ.get("JIGWORKS_HOME")
    return Path(env).resolve() if env else repo_root / ".jigworks"


def ensure_home(home: Path) -> Path:
    (home / "runs").mkdir(parents=True, exist_ok=True)
    (home / "worktrees").mkdir(parents=True, exist_ok=True)
    ignore = home / ".gitignore"
    if not ignore.exists():
        ignore.write_text("# Jigworks local run state; never committed.\n*\n")
    return home


@dataclass
class RunDir:
    path: Path

    @property
    def run_id(self) -> str:
        return self.path.name

    @property
    def meta_file(self) -> Path:
        return self.path / "run.json"

    @property
    def events_file(self) -> Path:
        return self.path / "events.jsonl"

    @property
    def nodes_file(self) -> Path:
        return self.path / "nodes.jsonl"

    @property
    def audit_file(self) -> Path:
        return self.path / "audit.jsonl"

    @property
    def package_dir(self) -> Path:
        return self.path / "package"

    def meta(self) -> dict[str, Any]:
        return json.loads(self.meta_file.read_text())

    def write_meta(self, meta: dict[str, Any]) -> None:
        tmp = self.meta_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2))
        tmp.replace(self.meta_file)

    def events(self) -> list[Event]:
        return _read_jsonl(self.events_file)

    def node_results(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.nodes_file)

    def append_event(self, event: Event) -> None:
        _append_jsonl(self.events_file, event)

    def append_node_result(self, entry: dict[str, Any]) -> None:
        _append_jsonl(self.nodes_file, entry)

    def append_audit(self, record: dict[str, Any]) -> None:
        _append_jsonl(self.audit_file, record)

    def last_audit(self) -> dict[str, Any] | None:
        records = _read_jsonl(self.audit_file)
        return records[-1] if records else None

    @contextmanager
    def checkpointer(self) -> Iterator[SqliteSaver]:
        conn = sqlite3.connect(self.path / "checkpoints.sqlite", check_same_thread=False)
        try:
            yield SqliteSaver(conn)
        finally:
            conn.close()

    @contextmanager
    def lock(self) -> Iterator[None]:
        with open(self.path / "lock", "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RunBusy(f"run {self.run_id} is being worked on by another runner process") from None
            fh.write(str(os.getpid()))
            fh.flush()
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def is_busy(self) -> bool:
        try:
            with open(self.path / "lock", "a") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True


class RunBusy(RuntimeError):
    pass


class UnknownRun(LookupError):
    pass


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            break  # a torn last line from a killed process; everything before it is intact
    return out


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with open(path, "a") as fh:
        fh.write(json.dumps(value, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


class Store:
    def __init__(self, home: Path) -> None:
        self.home = ensure_home(home)

    def create(self, run_id: str) -> RunDir:
        path = self.home / "runs" / run_id
        path.mkdir(parents=True, exist_ok=False)
        return RunDir(path)

    def get(self, run_id: str) -> RunDir:
        path = self.home / "runs" / run_id
        if not (path / "run.json").exists():
            raise UnknownRun(f"no run {run_id} in {self.home}")
        return RunDir(path)

    def all(self) -> list[RunDir]:
        runs = [RunDir(p) for p in (self.home / "runs").iterdir() if (p / "run.json").exists()]
        return sorted(runs, key=lambda r: r.run_id)

    def worktree_path(self, run_id: str) -> Path:
        return self.home / "worktrees" / run_id

    def copy_package(self, run: RunDir, files: dict[str, bytes]) -> Path:
        dest = run.package_dir
        if dest.exists():
            shutil.rmtree(dest)
        for rel, data in files.items():
            p = dest / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return dest
