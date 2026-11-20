"""Workflow drafts: the editable package files of a workflow (full replacement on save)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import psycopg

from .db import Jsonb
from .errors import ApiError, not_found

NEW_WORKFLOW_TEMPLATE = {
    "workflow.toml": """name = "{id}"
version = "0.1.0"
description = "Describe what this workflow does."
entrypoint = "graph:build_graph"
minRunnerVersion = "0.1.0"
plannedPath = ["plan", "approve_plan", "implement"]
interruptNodes = ["approve_plan"]

[models]
default = "claude-sonnet-5"

[weights]
plan = 20
approve_plan = 5
implement = 75
""",
    "graph.py": '''"""{id}: a minimal LangGraph workflow. Edit the steps and the edges."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from steps import nodes


class State(TypedDict, total=False):
    prompt: str
    plan: str


def build_graph() -> StateGraph:
    g = StateGraph(State)
    g.add_node("plan", nodes.plan)
    g.add_node("approve_plan", nodes.approve_plan)
    g.add_node("implement", nodes.implement)
    g.add_edge(START, "plan")
    g.add_edge("plan", "approve_plan")
    g.add_edge("approve_plan", "implement")
    g.add_edge("implement", END)
    return g
''',
    "steps/__init__.py": "",
    "steps/nodes.py": '''from langgraph.types import interrupt


def plan(state):
    return {"plan": f"Plan for: {state.get('prompt', '')}"}


def approve_plan(state):
    return {"decision": interrupt({"stage": "plan", "plan": state.get("plan", "")})["decision"]}


def implement(state):
    return {}
''',
    "prompts/plan.md": "Write a short plan for: {{prompt}}\n",
    "requirements.lock": "langgraph==1.2.23\n",
    "README.md": "# {id}\n",
}


def files_hash(files: list[dict[str, str]]) -> str:
    canon = json.dumps(sorted((f["path"], f["content"]) for f in files), separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()


def normalize(files: list[dict[str, str]]) -> list[dict[str, str]]:
    paths = [f["path"] for f in files]
    dupes = sorted({p for p in paths if paths.count(p) > 1})
    if dupes:
        raise ApiError(422, "validation_failed", f"duplicate paths: {', '.join(dupes)}")
    for p in paths:
        if p.endswith("/") or "//" in p or any(part in ("", ".", "..") for part in p.split("/")):
            raise ApiError(422, "validation_failed", f"unsafe path: {p}")
        if any(other.startswith(p + "/") for other in paths):
            raise ApiError(422, "validation_failed", f"{p} is both a file and a folder")
    return sorted(({"path": f["path"], "content": f["content"]} for f in files), key=lambda f: f["path"])


def to_api(row: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    out = {"workflowId": workflow_id, "files": row["files"], "updatedAt": row["updated_at"]}
    if row.get("base_release_id"):
        out["baseReleaseId"] = row["base_release_id"]
    return out


def get(conn: psycopg.Connection, workflow_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM drafts WHERE workflow_id = %s", (workflow_id,)).fetchone()
    if row is None:
        raise not_found(f"workflow {workflow_id}")
    return row


def save(conn: psycopg.Connection, workflow_id: str, files: list[dict[str, str]]) -> dict[str, Any]:
    """Replace the draft. A PUT to an unknown workflow id creates the workflow ("New workflow")."""
    files = normalize(files)
    now = datetime.now(UTC)
    if conn.execute("SELECT 1 FROM workflows WHERE id = %s", (workflow_id,)).fetchone() is None:
        conn.execute(
            "INSERT INTO workflows (id, name, description, source, updated_at) VALUES (%s, %s, %s, 'hub', %s)",
            (workflow_id, workflow_id, None, now),
        )
    else:
        conn.execute("UPDATE workflows SET updated_at = %s WHERE id = %s", (now, workflow_id))
    return conn.execute(
        """INSERT INTO drafts (workflow_id, files, files_hash, updated_at) VALUES (%s, %s, %s, %s)
           ON CONFLICT (workflow_id) DO UPDATE SET files = EXCLUDED.files, files_hash = EXCLUDED.files_hash,
                                                   updated_at = EXCLUDED.updated_at
           RETURNING *""",
        (workflow_id, Jsonb(files), files_hash(files), now),
    ).fetchone()


def template_files(workflow_id: str) -> list[dict[str, str]]:
    return [{"path": p, "content": t.replace("{id}", workflow_id)} for p, t in NEW_WORKFLOW_TEMPLATE.items()]
