"""Normalize LangGraph's get_graph().to_json() into the GraphJSON contract."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

START, END = "__start__", "__end__"


def normalize_langgraph_json(
    raw: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
    interrupt_nodes: Iterable[str] = (),
    workflow_id: str | None = None,
    release: str | None = None,
) -> dict[str, Any]:
    weights = weights or {}
    interrupts = set(interrupt_nodes)
    nodes = []
    for n in raw["nodes"]:
        nid = n["id"]
        kind = "start" if nid == START else "end" if nid == END else "interrupt" if nid in interrupts else "step"
        node: dict[str, Any] = {"id": nid, "kind": kind}
        if kind in ("step", "interrupt"):
            node["label"] = nid.replace("_", " ")
            if nid in weights:
                node["weight"] = weights[nid]
        nodes.append(node)
    edges = [
        {"source": e["source"], "target": e["target"], "conditional": bool(e.get("conditional", False))}
        for e in raw["edges"]
    ]
    out: dict[str, Any] = {"nodes": nodes, "edges": edges}
    if workflow_id:
        out["workflowId"] = workflow_id
    if release:
        out["release"] = release
    return out
