"""Generate the contract fixtures deterministically.

    uv run python packages/contracts/scripts/make_fixtures.py

Outputs (all validated against schema/jigworks.schema.json before writing):
  fixtures/bundles/   feature-development-<v>.zip + .sha256, a tampered zip
  fixtures/graph/     raw LangGraph get_graph() JSON + normalized GraphJSON
  fixtures/runs/      synthetic runs as RunEvent JSONL (see fixtures/README.md)
  fixtures/audit/     AuditRecord of one run
  fixtures/api/       example API responses (for LOCAL's mock and HUB's seed)
  fixtures/prices.json, fixtures/human-deltas.json

The runs are SYNTHETIC: generated from a script of node outcomes, not recorded from a
real runner (the runner does not exist before T06). Token counts are in the range seen
in docs/spikes/claude-stream-json.md; prices are the ones the CLI's own costUSD
confirmed for claude-haiku-4-5-20251001 and claude-sonnet-5.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
SRC = FIX / "bundles" / "src" / "feature-development"
sys.path.insert(0, str(ROOT))

from jigworks_contracts import assert_valid  # noqa: E402
from jigworks_contracts.bundle import build_bundle, digest, files_from_dir  # noqa: E402
from jigworks_contracts.graph import normalize_langgraph_json  # noqa: E402

SONNET = "claude-sonnet-5"
HAIKU = "claude-haiku-4-5-20251001"
PRICES = {  # USD per MTok; verified against costUSD in runner/tests/fixtures/stream-json
    SONNET: {"input": 3.0, "output": 15.0, "cache_write": 6.0, "cache_read": 0.30},
    HAIKU: {"input": 1.0, "output": 5.0, "cache_write": 2.0, "cache_read": 0.10},
}
WEIGHTS = {"plan": 10, "approve_plan": 2, "write_tests": 15, "implement": 30, "review": 10,
           "fix": 0, "gate": 10, "approve_pr": 3, "open_pr": 5, "summary": 5}
PLANNED = ["plan", "approve_plan", "write_tests", "implement", "review", "gate", "approve_pr", "open_pr", "summary"]
INTERRUPTS = ["approve_plan", "approve_pr"]
AGENT_NODES = {"plan", "write_tests", "implement", "review", "fix", "summary"}

VERSIONS = {
    "1.2.0": {
        "models": {"default": SONNET},
        "notes": "Gate runs pytest and the invariant property tests.",
        "publishedAt": "2026-11-12T10:00:00Z",
        "allowedTools": ["Read", "Edit", "Write", "Bash(pytest:*)", "Bash(git diff:*)"],
    },
    "1.3.0": {
        "models": {"default": SONNET, "nodes": {"write_tests": HAIKU, "summary": HAIKU}},
        "notes": "Adds the secret scan and static security scan to the gate; cheaper model for tests and summary.",
        "publishedAt": "2026-11-18T09:00:00Z",
        "allowedTools": ["Read", "Edit", "Write", "Bash(pytest:*)", "Bash(git diff:*)", "Bash(gitleaks:*)", "Bash(bandit:*)"],
    },
}


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fake_sha(*parts: object) -> str:
    return hashlib.sha1("/".join(map(str, parts)).encode()).hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def toml_list(items: list[str]) -> str:
    return "[" + ", ".join(json.dumps(i) for i in items) + "]"


def workflow_toml(version: str) -> str:
    v = VERSIONS[version]
    lines = [
        'name = "feature-development"',
        f'version = "{version}"',
        'description = "Plan, tests from the spec, implement, independent review, gate, human approval, PR."',
        'entrypoint = "graph:build_graph"',
        'minRunnerVersion = "0.1.0"',
        f"plannedPath = {toml_list(PLANNED)}",
        f"interruptNodes = {toml_list(INTERRUPTS)}",
        "",
        "[inputs.prompt]",
        'type = "text"',
        'description = "What to build."',
        "required = true",
        "",
        "[models]",
        f'default = "{v["models"]["default"]}"',
    ]
    if v["models"].get("nodes"):
        lines += ["", "[models.nodes]"] + [f'{k} = "{m}"' for k, m in v["models"]["nodes"].items()]
    lines += ["", "[weights]"] + [f"{k} = {w}" for k, w in WEIGHTS.items()]
    lines += ["", "[permissions]", f"allowedTools = {toml_list(v['allowedTools'])}", "network = false", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- bundles
def make_bundles() -> dict[str, dict]:
    out = {}
    (SRC / "workflow.toml").write_text(workflow_toml("1.3.0"))  # keep the source package complete
    bundles = FIX / "bundles"
    for version in VERSIONS:
        files = files_from_dir(SRC)
        files["workflow.toml"] = workflow_toml(version).encode()
        manifest = tomllib.loads(files["workflow.toml"].decode())
        assert_valid("WorkflowManifest", manifest)
        data = build_bundle(files)
        assert build_bundle(files) == data, "bundle build is not deterministic"
        d = digest(data)
        (bundles / f"feature-development-{version}.zip").write_bytes(data)
        (bundles / f"feature-development-{version}.zip.sha256").write_text(d + "\n")
        out[version] = {"digest": d, "manifest": manifest, "bytes": len(data)}
    # Tampered: same claimed digest as 1.3.0, one changed byte in graph.py.
    files = files_from_dir(SRC)
    files["workflow.toml"] = workflow_toml("1.3.0").encode()
    files["graph.py"] = files["graph.py"].replace(b"END, START", b"END,START", 1)
    (bundles / "feature-development-1.3.0.tampered.zip").write_bytes(build_bundle(files))
    return out


# --------------------------------------------------------------------------- graph
def make_graph(release: str) -> dict:
    raw_text = subprocess.run(
        ["uv", "run", "--no-project", "--with", "langgraph==1.2.23", "python", str(ROOT / "scripts" / "dump_graph.py"), str(SRC)],
        check=True, capture_output=True, text=True,
    ).stdout
    raw = json.loads(raw_text)
    write_json(FIX / "graph" / "feature-development.langgraph.json", raw)
    graph = normalize_langgraph_json(raw, weights=WEIGHTS, interrupt_nodes=INTERRUPTS,
                                     workflow_id="feature-development", release=release)
    assert_valid("GraphJSON", graph)
    write_json(FIX / "graph" / "feature-development-1.3.0.graph.json", graph)
    return graph


# --------------------------------------------------------------------------- runs
class Run:
    def __init__(self, run_id: str, version: str, info: dict, author: str, start: str, title: str):
        self.run_id, self.version, self.author, self.title = run_id, version, author, title
        self.release = f"feature-development@{version}"
        self.digest = info["digest"]
        self.models = VERSIONS[version]["models"]
        self.t = datetime.fromisoformat(start.replace("Z", "+00:00"))
        self.started_at = iso(self.t)
        self.events: list[dict] = []
        self.attempts: dict[str, int] = {}
        self.done: set[str] = set()
        self.usage: list[dict] = []
        self.steps: list[dict] = []
        self.decisions: list[dict] = []
        self.changed: list[str] = []
        self.follow_ups = self.fix_loops = 0
        self.first_result_commit: str | None = None
        self.last_commit: str | None = None
        self.approver: str | None = None
        self.approved_at: str | None = None
        self.status = "running"
        self.current: str | None = None
        self.pending_interrupt: tuple[str, str, str] | None = None
        self.emit("run_started", runStatus="running", stepsPlanned=len(PLANNED), progress=0, step=0, runStarted={
            "workflowId": "feature-development", "release": self.release, "releaseId": f"rel_fd_{version.replace('.', '_')}",
            "digest": self.digest, "authorEmail": author, "models": self.models, "adapter": "claude", "title": title,
            "plannedPath": PLANNED, "repo": "jigworks", "branch": f"jigworks/{run_id}", "runnerVersion": "0.1.0",
        })

    # helpers
    def tick(self, minutes: float) -> None:
        self.t += timedelta(minutes=minutes)

    def model_for(self, node: str) -> str:
        return self.models.get("nodes", {}).get(node, self.models["default"])

    def progress(self) -> dict:
        total = sum(WEIGHTS[n] for n in PLANNED)
        done = sum(WEIGHTS[n] for n in PLANNED if n in self.done)
        return {"progress": round(done / total * 100, 1), "step": len(self.done & set(PLANNED)), "stepsPlanned": len(PLANNED)}

    def emit(self, kind: str, **fields) -> dict:
        ev = {"runId": self.run_id, "seq": len(self.events), "kind": kind, "at": iso(self.t), "release": self.release, **fields}
        if kind == "run_started":
            ev["digest"] = self.digest
        assert_valid("RunEvent", ev)
        self.events.append(ev)
        return ev

    def start_node(self, node: str) -> int:
        attempt = self.attempts[node] = self.attempts.get(node, 0) + 1
        self.current = node
        model = self.model_for(node) if node in AGENT_NODES else None
        self.emit("node_status", node=node, attempt=attempt, status="running", **({"model": model} if model else {}), **self.progress())
        self.steps.append({"node": node, "attempt": attempt, "status": "running", "startedAt": iso(self.t), **({"model": model} if model else {})})
        return attempt

    def end_node(self, node: str, status: str, files: list[str] | None = None, gate: dict | None = None) -> None:
        attempt = self.attempts[node]
        snapshot = None
        if files is not None:
            commit = fake_sha(self.run_id, node, attempt)[:12]
            self.last_commit = commit
            snapshot = {"commit": commit, "changedFiles": files}
            for f in files:
                if f not in self.changed:
                    self.changed.append(f)
        if status == "succeeded" and node in PLANNED:
            self.done.add(node)
        self.emit("node_status", node=node, attempt=attempt, status=status, **({"snapshot": snapshot} if snapshot else {}), **self.progress())
        step = self.steps[-1]
        step.update(status=status, finishedAt=iso(self.t))
        if snapshot:
            step.update(commit=snapshot["commit"], changedFiles=snapshot["changedFiles"])
        if gate:
            step["gate"] = gate

    def agent_usage(self, node: str, inp: int, out: int, cw: int, cr: int) -> None:
        model = self.model_for(node)
        p = PRICES[model]
        cost = round((inp * p["input"] + out * p["output"] + cw * p["cache_write"] + cr * p["cache_read"]) / 1e6, 6)
        rec = {"runId": self.run_id, "node": node, "attempt": self.attempts[node], "model": model, "adapter": "claude",
               "input": inp, "output": out, "cache_write": cw, "cache_read": cr,
               "sessionId": fake_sha("session", self.run_id, node)[:8] + "-0000-4000-8000-" + fake_sha(self.run_id, node)[:12],
               "cliCostUsd": cost, "at": iso(self.t)}
        self.usage.append(rec)
        self.emit("usage", node=node, attempt=self.attempts[node], usage=rec)

    def say(self, node: str, text: str | None = None, tool: tuple[str, dict] | None = None, result: str | None = None,
            denied: bool = False) -> None:
        mid = "msg_" + fake_sha(self.run_id, node, len(self.events))[:20]
        if text:
            self.emit("agent_output", node=node, attempt=self.attempts[node], agentOutput={"block": "text", "messageId": mid, "text": text})
        if tool:
            tid = "toolu_" + fake_sha(self.run_id, node, tool[0], len(self.events))[:20]
            self.emit("agent_output", node=node, attempt=self.attempts[node],
                      agentOutput={"block": "tool_use", "messageId": mid, "tool": {"id": tid, "name": tool[0], "input": tool[1]}})
            self.emit("agent_output", node=node, attempt=self.attempts[node],
                      agentOutput={"block": "tool_result", "toolUseId": tid, "isError": denied, "text": result or "", **({"denied": True} if denied else {})})

    # node scripts
    def agent_node(self, node: str, minutes: float, tokens: tuple[int, int, int, int], files: list[str] | None = None,
                   status: str = "succeeded", text: str | None = None, tool: tuple[str, dict] | None = None,
                   result: str | None = None, denied: bool = False) -> None:
        self.start_node(node)
        if node == "fix":
            self.fix_loops += 1
        self.tick(minutes * 0.6)
        if text or tool:
            self.say(node, text, tool, result, denied)
        self.tick(minutes * 0.4)
        self.agent_usage(node, *tokens)
        self.end_node(node, status, files)

    def gate(self, passed_checks: dict[str, bool], minutes: float = 2) -> bool:
        self.start_node("gate")
        self.tick(minutes)
        names = {"tests": "pytest", "property_tests": "hypothesis invariants", "secret_scan": "gitleaks", "security_scan": "bandit"}
        checks = [{"name": names[k], "kind": k, "passed": ok,
                   "summary": ("ok" if ok else {"tests": "2 failed", "property_tests": "invariant total_matches_lines falsified",
                                                "secret_scan": "1 secret found", "security_scan": "1 high finding"}[k]),
                   **({} if ok else {"findings": 1})} for k, ok in passed_checks.items()]
        gate = {"passed": all(passed_checks.values()), "checks": checks}
        self.emit("gate_result", node="gate", attempt=self.attempts["gate"], gateResult=gate)
        self.end_node("gate", "succeeded" if gate["passed"] else "failed", gate=gate)
        return gate["passed"]

    def ask(self, node: str, stage: str, **payload) -> str:
        self.start_node(node)
        iid = f"int_{self.run_id}_{node}_{self.attempts[node]}"
        self.status = "waiting_human"
        if stage == "pr" and self.first_result_commit is None:
            self.first_result_commit = self.last_commit
        self.emit("node_status", node=node, attempt=self.attempts[node], status="waiting_human", runStatus="waiting_human", **self.progress())
        self.emit("interrupt", node=node, attempt=self.attempts[node], interrupt={"interruptId": iid, "stage": stage, **payload})
        self.steps[-1]["status"] = "waiting_human"
        self.pending_interrupt = (node, stage, iid)
        return iid

    def decide(self, decision: str, approver: str, minutes: float, comment: str | None = None) -> None:
        node, stage, iid = self.pending_interrupt
        self.tick(minutes)
        rd = {"interruptId": iid, "stage": stage, "decision": decision, "approverEmail": approver, **({"comment": comment} if comment else {})}
        self.status = "rejected" if decision == "reject" else "running"
        self.emit("review_decision", node=node, attempt=self.attempts[node], reviewDecision=rd, runStatus=self.status)
        self.decisions.append({"stage": stage, "decision": decision, "approverEmail": approver, "at": iso(self.t), **({"comment": comment} if comment else {})})
        if decision == "request_changes":
            self.follow_ups += 1
        if decision == "approve" and stage == "pr":
            self.approver, self.approved_at = approver, iso(self.t)
        self.end_node(node, "succeeded" if decision == "approve" else "failed" if decision == "reject" else "cancelled")
        self.pending_interrupt = None

    def totals(self) -> dict:
        t = {k: sum(u[k] for u in self.usage) for k in ("input", "output", "cache_write", "cache_read")}
        t["cliCostUsd"] = round(sum(u["cliCostUsd"] for u in self.usage), 6)
        return t

    def summary(self) -> dict:
        s = {"runId": self.run_id, "workflowId": "feature-development", "release": self.release,
             "releaseId": f"rel_fd_{self.version.replace('.', '_')}", "digest": self.digest, "status": self.status,
             "title": self.title, "authorEmail": self.author, "startedAt": self.started_at, "updatedAt": iso(self.t),
             "models": self.models, "adapter": "claude", "followUpPrompts": self.follow_ups, "fixLoops": self.fix_loops,
             "changedFiles": self.changed, "usage": self.totals(), "branch": f"jigworks/{self.run_id}", **self.progress()}
        if self.current:
            s["currentNode"] = self.current
        if self.status in ("succeeded", "failed", "rejected", "cancelled"):
            s["finishedAt"] = iso(self.t)
        for k, v in (("approverEmail", self.approver), ("approvedAt", self.approved_at),
                     ("firstResultCommit", self.first_result_commit)):
            if v:
                s[k] = v
        if self.status == "succeeded":
            s["finalCommit"] = self.last_commit
            s["prUrl"] = f"file:///tmp/jigworks-remote.git#jigworks/{self.run_id}"
        assert_valid("RunSummary", s)
        return s

    def finish(self, status: str) -> None:
        self.status = status
        self.current = None
        self.emit("run_finished", runStatus=status, summary=self.summary(), **self.progress())

    def audit(self) -> dict:
        a = {"runId": self.run_id, "workflowId": "feature-development", "release": self.release, "digest": self.digest,
             "status": self.status, "authorEmail": self.author, "startedAt": self.started_at, "models": self.models,
             "adapter": "claude", "steps": self.steps, "decisions": self.decisions, "changedFiles": self.changed,
             "usage": self.usage, "cliCostUsd": self.totals()["cliCostUsd"]}
        if self.status in ("succeeded", "failed", "rejected", "cancelled"):
            a["finishedAt"] = iso(self.t)
        for k, v in (("approverEmail", self.approver), ("approvedAt", self.approved_at), ("firstResultCommit", self.first_result_commit),
                     ("finalCommit", self.last_commit if self.status == "succeeded" else None),
                     ("prUrl", f"file:///tmp/jigworks-remote.git#jigworks/{self.run_id}" if self.status == "succeeded" else None)):
            if v:
                a[k] = v
        assert_valid("AuditRecord", a)
        return a


ALICE, BOB, CAROL = "alice@example.com", "bob@example.com", "carol@example.com"
FILES = ["sample-repo/sample_repo/discounts.py", "sample-repo/tests/test_discounts.py"]
PLAN_TEXT = "1. Add percentage discounts per order line.\n2. Property test: order total == sum of discounted lines, never negative.\n3. Reject discounts above 100 %."
GATE_ALL_13 = {"tests": True, "property_tests": True, "secret_scan": True, "security_scan": True}
GATE_ALL_12 = {"tests": True, "property_tests": True}
T_PLAN, T_TESTS, T_IMPL, T_REVIEW, T_FIX, T_SUM = (
    (40, 2_100, 18_400, 96_000), (35, 3_900, 14_200, 120_000), (60, 7_800, 31_000, 410_000),
    (30, 1_600, 9_800, 150_000), (25, 2_900, 8_100, 180_000), (12, 600, 4_000, 60_000))


def happy_path(r: Run, gate_checks: dict, approver: str) -> None:
    r.agent_node("plan", 3, T_PLAN, text="Plan: 3 steps. The invariant total == sum(lines) gets a property test first.")
    r.ask("approve_plan", "plan", message="Approve the plan?", plan=PLAN_TEXT)
    r.decide("approve", approver, 2)
    r.agent_node("write_tests", 4, T_TESTS, files=[FILES[1]], tool=("Write", {"file_path": FILES[1]}), result="File created")
    r.agent_node("implement", 9, T_IMPL, files=[FILES[0]], tool=("Bash", {"command": "pytest -q sample-repo"}), result="12 passed")
    r.agent_node("review", 3, T_REVIEW, text="PASS: implementation matches the plan; tests were written before the code.")
    r.gate(gate_checks)


def make_runs(bundles: dict) -> list[Run]:
    runs = []

    # 1) 1.3.0, worked first time
    r = Run("run_fd_0001", "1.3.0", bundles["1.3.0"], ALICE, "2026-11-18T09:30:00Z", "Add percentage discounts per order line")
    happy_path(r, GATE_ALL_13, ALICE)
    r.ask("approve_pr", "pr", message="Review the change before the PR is opened.", commit=r.last_commit,
          diffStat={"files": 2, "linesAdded": 84, "linesRemoved": 6})
    r.decide("approve", ALICE, 6)
    r.start_node("open_pr"); r.tick(1); r.end_node("open_pr", "succeeded")  # open_pr runs git, no agent
    r.agent_node("summary", 1, T_SUM, text="Discounts added; 2 files, gate green incl. secret and security scan.")
    r.finish("succeeded")
    runs.append(r)

    # 2) 1.3.0, review FAIL → fix, gate FAIL → fix, request changes → fix → gate → approve
    r = Run("run_fd_0002", "1.3.0", bundles["1.3.0"], BOB, "2026-11-18T13:05:00Z", "Cap refunds at the captured amount")
    r.agent_node("plan", 3, T_PLAN, text="Plan: refund <= captured amount, property test over random order histories.")
    r.ask("approve_plan", "plan", message="Approve the plan?", plan="1. Cap refunds.\n2. Property test: sum(refunds) <= captured.")
    r.decide("approve", BOB, 1)
    r.agent_node("write_tests", 4, T_TESTS, files=["sample-repo/tests/test_refunds.py"])
    r.agent_node("implement", 10, T_IMPL, files=["sample-repo/sample_repo/refunds.py"],
                 tool=("Bash", {"command": "curl https://example.com"}), result="Permission denied: Bash(curl) is not in allowedTools", denied=True)
    r.agent_node("review", 3, T_REVIEW, status="failed", text="FAIL: partial refunds on split captures are not capped.")
    r.agent_node("fix", 4, T_FIX, files=["sample-repo/sample_repo/refunds.py"])
    r.agent_node("review", 3, T_REVIEW, text="PASS")
    r.gate({"tests": True, "property_tests": False, "secret_scan": True, "security_scan": True})
    r.agent_node("fix", 4, T_FIX, files=["sample-repo/sample_repo/refunds.py"])
    r.gate(GATE_ALL_13)
    r.ask("approve_pr", "pr", message="Review the change before the PR is opened.", commit=r.last_commit,
          diffStat={"files": 2, "linesAdded": 61, "linesRemoved": 12})
    r.decide("request_changes", BOB, 9, comment="Use Decimal instead of float for amounts.")
    r.agent_node("fix", 5, T_FIX, files=["sample-repo/sample_repo/refunds.py"])
    r.gate(GATE_ALL_13)
    r.ask("approve_pr", "pr", message="Review the change before the PR is opened.", commit=r.last_commit,
          diffStat={"files": 2, "linesAdded": 66, "linesRemoved": 12})
    r.decide("approve", BOB, 4)
    r.start_node("open_pr"); r.tick(1); r.end_node("open_pr", "succeeded")
    r.agent_node("summary", 1, T_SUM)
    r.finish("succeeded")
    runs.append(r)

    # 3) 1.2.0, rejected at the plan
    r = Run("run_fd_0003", "1.2.0", bundles["1.2.0"], CAROL, "2026-11-13T08:10:00Z", "Rewrite order states as an event log")
    r.agent_node("plan", 4, T_PLAN, text="Plan: replace the status column with an append-only event log.")
    r.ask("approve_plan", "plan", message="Approve the plan?", plan="1. Event log table.\n2. Migrate all states.")
    r.decide("reject", CAROL, 3, comment="Too big for one run; split it.")
    r.finish("rejected")
    runs.append(r)

    # 4) 1.2.0, one gate failure, approved
    r = Run("run_fd_0004", "1.2.0", bundles["1.2.0"], ALICE, "2026-11-14T15:40:00Z", "Validate currency on every order line")
    happy_path(r, {"tests": False, "property_tests": True}, ALICE)
    r.agent_node("fix", 4, T_FIX, files=[FILES[0]])
    r.gate(GATE_ALL_12)
    r.ask("approve_pr", "pr", message="Review the change before the PR is opened.", commit=r.last_commit,
          diffStat={"files": 2, "linesAdded": 40, "linesRemoved": 3})
    r.decide("approve", BOB, 12)
    r.start_node("open_pr"); r.tick(1); r.end_node("open_pr", "succeeded")
    r.agent_node("summary", 1, T_SUM)
    r.finish("succeeded")
    runs.append(r)

    # 5) 1.3.0, waiting for the PR review (extension: Review badge)
    r = Run("run_fd_0005", "1.3.0", bundles["1.3.0"], BOB, "2026-11-19T10:00:00Z", "Add an idempotency key to order creation")
    happy_path(r, GATE_ALL_13, BOB)
    r.ask("approve_pr", "pr", message="Review the change before the PR is opened.", commit=r.last_commit,
          diffStat={"files": 2, "linesAdded": 52, "linesRemoved": 4})
    runs.append(r)

    # 6) 1.3.0, paused by the subscription usage limit during implement
    r = Run("run_fd_0006", "1.3.0", bundles["1.3.0"], CAROL, "2026-11-19T11:20:00Z", "Split shipping cost across order lines")
    r.agent_node("plan", 3, T_PLAN)
    r.ask("approve_plan", "plan", message="Approve the plan?", plan="1. Pro-rata shipping.\n2. Property test: lines sum to the shipping total.")
    r.decide("approve", CAROL, 2)
    r.agent_node("write_tests", 4, T_TESTS, files=["sample-repo/tests/test_shipping.py"])
    r.start_node("implement")
    r.tick(5)
    resets = iso(r.t + timedelta(hours=2, minutes=10))
    r.emit("usage_limit", node="implement", attempt=1, runStatus="paused_usage_limit",
           usageLimit={"status": "rejected", "rateLimitType": "five_hour", "resetsAt": resets, "paused": True})
    r.emit("error", node="implement", attempt=1,
           error={"code": "usage_limit", "message": f"Claude usage limit reached; resumes after {resets}.", "retryable": True})
    r.status = "paused_usage_limit"
    r.steps[-1]["status"] = "cancelled"
    runs.append(r)

    # 7) 1.3.0, running: implement in progress (live view)
    r = Run("run_fd_0007", "1.3.0", bundles["1.3.0"], ALICE, "2026-11-19T14:00:00Z", "Expose order totals in the CSV export")
    r.agent_node("plan", 3, T_PLAN)
    r.ask("approve_plan", "plan", message="Approve the plan?", plan="1. Add total column.\n2. Golden-file test.")
    r.decide("approve", ALICE, 1)
    r.agent_node("write_tests", 4, T_TESTS, files=["sample-repo/tests/test_export.py"])
    r.start_node("implement")
    r.tick(2)
    r.say("implement", text="Adding the total column to export_orders().",
          tool=("Read", {"file_path": "sample-repo/sample_repo/export.py"}), result="def export_orders(orders): ...")
    runs.append(r)
    return runs


RUN_FILES = {
    "run_fd_0001": "approved-first-time", "run_fd_0002": "fix-loops-request-changes", "run_fd_0003": "rejected-at-plan",
    "run_fd_0004": "gate-fail-then-approved", "run_fd_0005": "waiting-for-review", "run_fd_0006": "paused-usage-limit",
    "run_fd_0007": "running-implement",
}


def main() -> int:
    bundles = make_bundles()
    graph = make_graph("feature-development@1.3.0")
    runs = make_runs(bundles)

    runs_dir = FIX / "runs"
    shutil.rmtree(runs_dir, ignore_errors=True)
    runs_dir.mkdir(parents=True)
    for r in runs:
        name = f"{r.run_id}-{RUN_FILES[r.run_id]}.jsonl"
        (runs_dir / name).write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in r.events))
    write_json(FIX / "audit" / "run_fd_0002.audit.json", runs[1].audit())

    prices = [{"model": m, "tokenType": t, "pricePerMtok": p, "validFrom": "2026-01-01T00:00:00Z"}
              for m, table in PRICES.items() for t, p in table.items()]
    for p in prices:
        assert_valid("PriceEntry", p)
    write_json(FIX / "prices.json", prices)

    deltas = []
    for r, outcome, files, add, rem in (
        (runs[0], "worked_first_time", [], 0, 0), (runs[1], "corrected_by_prompt", [], 0, 0),
        (runs[2], "rejected", [], 0, 0), (runs[3], "edited_by_hand", [FILES[0]], 7, 2),
    ):
        d = {"runId": r.run_id, "release": r.release, "digest": r.digest, "outcome": outcome, "followUpPrompts": r.follow_ups,
             "files": files, "linesAdded": add, "linesRemoved": rem, "source": "sample", "sample": True,
             "capturedAt": iso(r.t + timedelta(hours=1))}
        if r.first_result_commit:
            d["firstResultCommit"] = r.first_result_commit
        assert_valid("HumanDelta", d)
        deltas.append(d)
    write_json(FIX / "human-deltas.json", deltas)

    # Example API responses
    api = FIX / "api"
    releases = []
    for v, info in bundles.items():
        rel = {"id": f"rel_fd_{v.replace('.', '_')}", "workflowId": "feature-development", "version": v,
               "release": f"feature-development@{v}", "digest": info["digest"], "publishedAt": VERSIONS[v]["publishedAt"],
               "publishedBy": CAROL, "notes": VERSIONS[v]["notes"], "manifest": info["manifest"], "bundleBytes": info["bytes"],
               "channels": ["stable"] if v == "1.3.0" else []}
        releases.append(rel)
    examples = {
        "health.json": ("HealthResponse", {"ok": True}),
        "workflow-list.json": ("WorkflowList", {"workflows": [{
            "id": "feature-development", "name": "Feature development",
            "description": "Plan, tests from the spec, implement, independent review, gate, human approval, PR.",
            "ownerEmail": CAROL, "updatedAt": "2026-11-18T09:00:00Z", "latestVersion": "1.3.0",
            "channels": {"stable": "1.3.0", "beta": "1.3.0"}, "hasUnpublishedDraft": False, "runs7d": 7, "source": "hub"}]}),
        "release-list.json": ("ReleaseList", {"releases": list(reversed(releases))}),
        "channel-stable.json": ("ChannelResolution", {
            "workflowId": "feature-development", "channel": "stable", "releaseId": "rel_fd_1_3_0", "version": "1.3.0",
            "digest": bundles["1.3.0"]["digest"], "bundleUrl": "/api/releases/rel_fd_1_3_0/bundle"}),
        "validation-ok.json": ("ValidationResult", {"ok": True, "durationMs": 2140, "graph": graph, "checks": [
            {"name": n, "ok": True} for n in ("manifest", "syntax", "imports", "compile", "graph")]}),
        "validation-failed.json": ("ValidationResult", {"ok": False, "durationMs": 830, "checks": [
            {"name": "manifest", "ok": True}, {"name": "syntax", "ok": False, "file": "steps/nodes.py", "line": 12,
                                               "message": "SyntaxError: expected ':'"}]}),
        "run-create.json": ("RunCreate", {k: runs[0].summary()[k] for k in
                                          ("runId", "workflowId", "releaseId", "release", "digest", "authorEmail", "models", "adapter", "title", "startedAt")}
                            | {"stepsPlanned": len(PLANNED)}),
        "event-batch.json": ("EventBatch", {"events": runs[0].events[:5]}),
        "event-batch-result.json": ("EventBatchResult", {"accepted": 5, "duplicates": 0, "lastSeq": 4}),
        "run-list.json": ("RunList", {"runs": [r.summary() for r in runs]}),
        "run-detail.json": ("RunDetail", {"summary": runs[1].summary(), "audit": runs[1].audit(), "graph": graph}),
        "error-unauthorized.json": ("ErrorResponse", {"error": {"code": "unauthorized", "message": "Hub password required."}}),
    }
    for name, (def_name, obj) in examples.items():
        assert_valid(def_name, obj)
        write_json(api / name, obj)

    index = {"runs/" + p.name: {"def": "RunEvent", "jsonl": True} for p in sorted(runs_dir.glob("*.jsonl"))}
    index |= {f"api/{n}": {"def": d} for n, (d, _) in examples.items()}
    index |= {"audit/run_fd_0002.audit.json": {"def": "AuditRecord"}, "prices.json": {"def": "PriceEntry", "list": True},
              "human-deltas.json": {"def": "HumanDelta", "list": True},
              "graph/feature-development-1.3.0.graph.json": {"def": "GraphJSON"}}
    write_json(FIX / "index.json", {"fixtures": index, "bundles": {
        f"bundles/feature-development-{v}.zip": i["digest"] for v, i in bundles.items()},
        "tampered": {"bundles/feature-development-1.3.0.tampered.zip": bundles["1.3.0"]["digest"]}})

    print(f"bundles: {', '.join(f'{v} {i['digest'][:19]}…' for v, i in bundles.items())}")
    print(f"graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    for r in runs:
        print(f"run {r.run_id}: {len(r.events)} events, status {r.status}, progress {r.progress()['progress']} %, "
              f"cliCost ${r.totals()['cliCostUsd']:.2f}")
    print(f"api examples: {len(examples)}; prices: {len(prices)}; human deltas: {len(deltas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
