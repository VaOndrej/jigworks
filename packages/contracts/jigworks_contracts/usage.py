"""Usage of resumed agent sessions: per-call records, also for runs that recorded running totals.

A UsageRecord is the usage of one agent call. Claude CLI 2.1.329 (measured 2026-11-20) reports
`result.modelUsage` of a `--resume` call as the running total of the whole session, and runners
before T25 recorded that total per call, so every earlier call was counted again (a run showed
$168 instead of ~$23). Those records cannot be told apart by a field, only by their shape: running
totals of one session and model never decrease. The rule, shared by runner, hub and extension
(`clients/vscode/src/shared/cost.ts` mirrors it):

- the leading run of records of a session and model where no field decreases and the output
  grows are running totals: each one adds its difference to the previous one;
- every record after the first decrease is already per call (runners from T25 on).

The heuristic misreads a per-call series only if a later call is at least as large as the first
one in every field, including cache_write; the first call of a session writes the whole prompt
cache, so this does not happen in practice.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

FIELDS = ("input", "output", "cache_write", "cache_read", "cliCostUsd")


def _v(record: dict[str, Any], field: str) -> float:
    return record.get(field) or 0


def _covers(later: dict[str, Any], earlier: dict[str, Any]) -> bool:
    """`later` can be a running total after `earlier`: no field shrank and the call produced output
    (two equal records are two calls of the same size, not a total that did not grow)."""
    return all(_v(later, f) >= _v(earlier, f) for f in FIELDS) and _v(later, "output") > _v(earlier, "output")


def _minus(a: dict[str, Any], b: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(a)
    for f in FIELDS:
        if f in a and a[f] is not None:
            d = a[f] - (_v(b, f) if b else 0)
            out[f] = round(d, 10) if f == "cliCostUsd" else int(d)
    return out


def per_call(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The records of a run in order, each turned into the usage of its own call."""
    out: list[dict[str, Any]] = []
    last: dict[tuple, dict[str, Any]] = {}  # (session, model) → last running total, while still in the leading run
    done: set[tuple] = set()  # series whose leading run of running totals has ended
    for r in records:
        sid = r.get("sessionId")
        if not sid:
            out.append(dict(r))
            continue
        key = (sid, r["model"])
        if key in done:
            out.append(dict(r))
        elif key not in last:
            last[key] = r
            out.append(dict(r))
        elif _covers(r, last[key]):
            out.append(_minus(r, last[key]))
            last[key] = r
        else:
            done.add(key)
            out.append(dict(r))
    return out


def session_total(earlier: list[dict[str, Any]]) -> dict[str, float]:
    """The session's running total after `earlier` (its records for one model, in order)."""
    calls = per_call(earlier)
    return {f: sum(_v(c, f) for c in calls) for f in FIELDS}


def this_call(reported: dict[str, Any], earlier: list[dict[str, Any]]) -> dict[str, Any]:
    """A runner's record for a resumed call: `reported` is what the CLI said, `earlier` the
    records already in the run for the same session and model. A CLI that reports per call gives
    less than the session total in some field, and is kept as it is."""
    if not earlier:
        return reported
    total = session_total(earlier)
    if not all(_v(reported, f) >= total[f] for f in FIELDS):
        return reported
    return _minus(reported, total)
