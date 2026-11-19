"""Usage and cost analytics. Raw tokens are stored per call; cost = tokens × the price entry
valid at the call time, computed at read time and labelled "API equivalent" (design.md §8)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from .projection import gate_passed_first_try, human_wait_seconds

TOKENS = ("input", "output", "cache_write", "cache_read")
COST_LABEL = "API equivalent"


def _dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


class Prices:
    def __init__(self, conn: psycopg.Connection):
        rows = conn.execute("SELECT * FROM prices ORDER BY valid_from").fetchall()
        self.rows = rows
        self.by_key: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)
        for r in rows:
            self.by_key[(r["model"], r["token_type"])].append((r["valid_from"], r["price_per_mtok"]))

    def price(self, model: str, token_type: str, at: datetime) -> float:
        valid = [p for since, p in self.by_key.get((model, token_type), []) if since <= at]
        return valid[-1] if valid else 0.0  # unknown model: no price, counted as 0 (shown in the price list)

    def cost_parts(self, u: dict[str, Any]) -> dict[str, float]:
        return {t: u[t] * self.price(u["model"], t, _dt(u["at"])) / 1e6 for t in TOKENS}

    def cost(self, u: dict[str, Any]) -> float:
        return sum(self.cost_parts(u).values())

    def as_api(self) -> list[dict[str, Any]]:
        return [{"model": r["model"], "tokenType": r["token_type"], "pricePerMtok": r["price_per_mtok"],
                 "validFrom": r["valid_from"]} for r in self.rows]


def run_costs(conn: psycopg.Connection, run_ids: list[str] | None = None) -> dict[str, float]:
    prices = Prices(conn)
    q = "SELECT * FROM usage" + (" WHERE run_id = ANY(%s)" if run_ids is not None else "")
    out: dict[str, float] = defaultdict(float)
    for u in conn.execute(q, (run_ids,) if run_ids is not None else ()).fetchall():
        out[u["run_id"]] += prices.cost(u)
    return {k: round(v, 6) for k, v in out.items()}


def _period(from_: datetime | None, to: datetime | None, default_days: int = 7) -> tuple[datetime, datetime]:
    to = to or datetime.now(UTC)
    return from_ or (to - timedelta(days=default_days)), to


def usage_report(conn: psycopg.Connection, group_by: str, workflow_id: str | None,
                 from_: datetime | None, to: datetime | None) -> dict[str, Any]:
    prices = Prices(conn)
    clauses, params = [], []
    if workflow_id:
        clauses.append("r.workflow_id = %s")
        params.append(workflow_id)
    if from_:
        clauses.append("u.at >= %s")
        params.append(from_)
    if to:
        clauses.append("u.at < %s")
        params.append(to)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT u.*, r.release FROM usage u JOIN runs r USING (run_id){where} ORDER BY u.at", params
    ).fetchall()

    def key_of(u: dict) -> str:
        if group_by == "day":
            return _dt(u["at"]).astimezone(UTC).date().isoformat()
        return u[group_by]

    groups: dict[str, dict[str, Any]] = {}
    for u in rows:
        g = groups.setdefault(key_of(u), {"runs": set(), **{t: 0 for t in TOKENS}, "costUsd": 0.0, "cli": 0.0, "hasCli": False})
        g["runs"].add(u["run_id"])
        for t in TOKENS:
            g[t] += u[t]
        g["costUsd"] += prices.cost(u)
        if u["cli_cost_usd"] is not None:
            g["cli"] += u["cli_cost_usd"]
            g["hasCli"] = True

    def row(key: str, g: dict) -> dict[str, Any]:
        out = {"key": key, "runs": len(g["runs"]), **{t: g[t] for t in TOKENS}, "costUsd": round(g["costUsd"], 6)}
        if g["hasCli"]:
            out["cliCostUsd"] = round(g["cli"], 6)
        return out

    total = {"runs": set(), **{t: 0 for t in TOKENS}, "costUsd": 0.0, "cli": 0.0, "hasCli": False}
    for g in groups.values():
        total["runs"] |= g["runs"]
        for t in (*TOKENS, "costUsd", "cli"):
            total[t] += g[t]
        total["hasCli"] |= g["hasCli"]
    report: dict[str, Any] = {"groupBy": group_by, "costLabel": COST_LABEL,
                              "rows": [row(k, g) for k, g in sorted(groups.items())],
                              "totals": row("total", total), "prices": prices.as_api()}
    if workflow_id:
        report["workflowId"] = workflow_id
    if from_:
        report["from"] = from_
    if to:
        report["to"] = to
    return report


def _semver_key(version: str) -> tuple:
    core = version.split("-", 1)[0].split("+", 1)[0]
    return tuple(int(x) for x in core.split("."))


def release_comparison(conn: psycopg.Connection, workflow_id: str) -> dict[str, Any]:
    runs = conn.execute("SELECT run_id, release, summary FROM runs WHERE workflow_id = %s", (workflow_id,)).fetchall()
    costs = run_costs(conn, [r["run_id"] for r in runs])
    versions = {r["version"] for r in conn.execute("SELECT version FROM releases WHERE workflow_id = %s", (workflow_id,)).fetchall()}
    by_release: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        by_release[r["release"]].append(r["summary"])
    for v in versions:
        by_release.setdefault(f"{workflow_id}@{v}", [])
    rows = []
    for release, summaries in by_release.items():
        version = release.split("@", 1)[1]
        n = len(summaries)
        count = lambda st: sum(1 for s in summaries if s["status"] == st)  # noqa: E731
        succeeded, failed, rejected = count("succeeded"), count("failed"), count("rejected")
        finished = succeeded + failed + rejected
        durations = [(_dt(s["finishedAt"]) - _dt(s["startedAt"])).total_seconds() for s in summaries if s.get("finishedAt")]
        row: dict[str, Any] = {
            "release": release, "version": version, "runs": n, "succeeded": succeeded, "failed": failed,
            "rejected": rejected,
            "avgFixLoops": round(statistics.fmean(s.get("fixLoops") or 0 for s in summaries), 3) if n else 0.0,
            "avgCostUsd": round(statistics.fmean(costs.get(s["runId"], 0.0) for s in summaries), 6) if n else 0.0,
        }
        if finished:
            row["successRate"] = round(succeeded / finished, 4)
        if n:
            row["avgFollowUpPrompts"] = round(statistics.fmean(s["followUpPrompts"] for s in summaries), 3)
        if durations:
            row["avgDurationSec"] = round(statistics.fmean(durations), 1)
        rows.append(row)
    rows.sort(key=lambda r: _semver_key(r["version"]))
    return {"workflowId": workflow_id, "rows": rows}


def outcomes(conn: psycopg.Connection, workflow_id: str | None) -> dict[str, Any]:
    deltas = [r["body"] for r in conn.execute("SELECT body FROM human_deltas ORDER BY run_id").fetchall()]
    if workflow_id:
        deltas = [d for d in deltas if d["release"].split("@", 1)[0] == workflow_id]
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for d in deltas:
        counts[(d["release"], d["outcome"])] += 1
    rows = [{"release": rel, "outcome": out, "sessions": n} for (rel, out), n in sorted(counts.items())]
    return {"planned": True, "sample": all(d.get("sample") for d in deltas), "rows": rows, "deltas": deltas}


def _interrupt_nodes(conn: psycopg.Connection) -> dict[str, set[str]]:
    out = {}
    for r in conn.execute("SELECT workflow_id, version, manifest FROM releases").fetchall():
        nodes = set((r["manifest"] or {}).get("interruptNodes") or [])
        out[f"{r['workflow_id']}@{r['version']}"] = nodes
    return out


def overview(conn: psycopg.Connection, workflow_id: str | None, from_: datetime | None, to: datetime | None) -> dict[str, Any]:
    """Key numbers for the Workflows and Runs & analytics tabs (hub-only extension of the contract)."""
    start, end = _period(from_, to)
    rows = conn.execute(
        "SELECT run_id, workflow_id, release, status, started_at, summary, audit FROM runs"
        + (" WHERE workflow_id = %s" if workflow_id else ""),
        (workflow_id,) if workflow_id else (),
    ).fetchall()
    costs = run_costs(conn, [r["run_id"] for r in rows])
    interrupts = _interrupt_nodes(conn)
    in_period = [r for r in rows if start <= r["started_at"] < end]
    span = end - start
    previous = [r for r in rows if start - span <= r["started_at"] < start]
    live = [r for r in rows if r["status"] in ("running", "waiting_human", "paused_usage_limit")]
    waiting = [r for r in live if r["status"] == "waiting_human"]

    def stats(group: list[dict]) -> dict[str, Any]:
        gates = [g for g in (gate_passed_first_try(r["audit"]) for r in group) if g is not None]
        to_pr = [(_dt(r["summary"]["approvedAt"]) - _dt(r["summary"]["startedAt"])).total_seconds()
                 for r in group if r["summary"].get("approvedAt")]
        waits = [human_wait_seconds(r["audit"], interrupts.get(r["release"]) or {"approve_plan", "approve_pr"})
                 for r in group if r["summary"].get("approvedAt")]
        cost = sum(costs.get(r["run_id"], 0.0) for r in group)
        out: dict[str, Any] = {"runs": len(group), "costUsd": round(cost, 6),
                               "gateRuns": len(gates)}
        out["costPerRunUsd"] = round(cost / len(group), 6) if group else None
        out["gatePassFirstTry"] = round(sum(gates) / len(gates), 4) if gates else None
        out["medianTimeToPrSec"] = statistics.median(to_pr) if to_pr else None
        out["medianHumanWaitSec"] = statistics.median(waits) if waits else None
        return out

    cost_by_day: dict[str, dict[str, float]] = {}
    prices = Prices(conn)
    ids = [r["run_id"] for r in rows]
    for u in conn.execute("SELECT * FROM usage WHERE run_id = ANY(%s) AND at >= %s AND at < %s", (ids, start, end)).fetchall():
        day = _dt(u["at"]).astimezone(UTC).date().isoformat()
        parts = prices.cost_parts(u)
        d = cost_by_day.setdefault(day, {t: 0.0 for t in TOKENS})
        for t in TOKENS:
            d[t] += parts[t]
    days = []
    cursor = start.astimezone(UTC).date()
    while cursor <= (end - timedelta(microseconds=1)).astimezone(UTC).date():
        d = cost_by_day.get(cursor.isoformat(), {t: 0.0 for t in TOKENS})
        days.append({"day": cursor.isoformat(), **{t: round(d[t], 6) for t in TOKENS}})
        cursor += timedelta(days=1)

    per_workflow = defaultdict(list)
    for r in in_period:
        per_workflow[r["workflow_id"]].append(r)
    per_release = defaultdict(list)
    for r in rows:
        per_release[r["release"]].append(r)
    out = {
        "from": start, "to": end, "costLabel": COST_LABEL,
        **stats(in_period),
        "previousRuns": len(previous),
        "running": sum(1 for r in live if r["status"] == "running"),
        "waitingHuman": len(waiting),
        "pausedUsageLimit": sum(1 for r in live if r["status"] == "paused_usage_limit"),
        "oldestWaitingSince": min((_dt(r["summary"].get("updatedAt") or r["started_at"]) for r in waiting), default=None),
        "costByDay": days,
        "workflows": [{"workflowId": wf, **stats(group),
                       "running": sum(1 for r in live if r["workflow_id"] == wf)} for wf, group in sorted(per_workflow.items())],
        "releases": [{"release": rel, **stats(group)} for rel, group in sorted(per_release.items())],
    }
    return out
