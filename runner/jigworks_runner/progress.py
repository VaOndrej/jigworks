"""Progress weights for "% of plan" (design.md §7).

Weights come from the durations of past local runs of the **same release digest** (their audit
logs); with no usable history they fall back to `[weights]` in workflow.toml. Interrupt nodes
measure human waiting time, not work, so they always keep their manifest weight, scaled to the
same unit as the measured nodes.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any, Iterable


def _seconds(step: dict[str, Any]) -> float | None:
    if not step.get("finishedAt"):
        return None
    start = datetime.fromisoformat(step["startedAt"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(step["finishedAt"].replace("Z", "+00:00"))
    return max((end - start).total_seconds(), 0.0)


def weights_from_history(
    manifest: dict[str, Any], digest: str, audits: Iterable[dict[str, Any]]
) -> tuple[dict[str, float], str]:
    """Return (weights, source) where source is "history (n runs)" or "workflow.toml"."""
    fallback = {k: float(v) for k, v in manifest.get("weights", {}).items()}
    planned = list(manifest.get("plannedPath", []))
    interrupts = set(manifest.get("interruptNodes", []))
    measured_nodes = [n for n in planned if n not in interrupts]

    durations: dict[str, list[float]] = {n: [] for n in measured_nodes}
    runs = 0
    for audit in audits:
        if audit.get("digest") != digest or audit.get("status") != "succeeded":
            continue
        runs += 1
        for step in audit.get("steps", []):
            if step["node"] in durations and step.get("status") == "succeeded":
                secs = _seconds(step)
                if secs is not None:
                    durations[step["node"]].append(secs)
    if not runs or any(not durations[n] for n in measured_nodes):
        return fallback, "workflow.toml"

    measured = {n: max(mean(durations[n]), 0.1) for n in measured_nodes}
    manifest_measured = sum(fallback.get(n, 1.0) for n in measured_nodes) or 1.0
    scale = sum(measured.values()) / manifest_measured
    weights = dict(fallback)
    weights.update(measured)
    for n in interrupts:
        weights[n] = fallback.get(n, 1.0) * scale
    return {k: round(v, 3) for k, v in weights.items()}, f"history ({runs} runs)"
