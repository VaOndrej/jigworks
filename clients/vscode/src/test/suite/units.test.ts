// Pure unit tests (no VS Code API): the session fold, tab chrome, plain-language actions and the
// liveness state. Run inside `pnpm test` and on their own with `pnpm test:unit`.
import * as assert from "node:assert/strict";
import type { RunEvent } from "@jigworks/contracts";
import { describeLine, describeTool, elapsed, livenessState, recentActions, stepCounters } from "../../shared/activity";
import { foldEvents, nodeDone, type AgentLine, type SessionView } from "../../shared/session";
import { shortTitle, tabChrome, tabIcon } from "../../shared/tabTitle";

const R = "run_t21";
let seq = 0;
function ev(kind: string, extra: Record<string, unknown>): RunEvent {
  return { runId: R, seq: seq++, kind, at: `2026-11-20T12:${String(40 + Math.floor(seq / 10)).padStart(2, "0")}:${String((seq * 7) % 60).padStart(2, "0")}Z`, release: "feature-development@1.6.0", ...extra } as unknown as RunEvent;
}

function started(title = "Per-line percentage discounts"): RunEvent[] {
  seq = 0;
  return [
    ev("run_started", {
      runStatus: "running",
      runStarted: { workflowId: "feature-development", release: "feature-development@1.6.0", releaseId: "r", digest: "sha256:x", models: { default: "claude-opus-5-5" }, adapter: "claude", title, plannedPath: ["plan", "approve_plan", "write_tests", "implement"] },
    }),
    ev("node_status", { node: "plan", attempt: 1, status: "running" }),
    ev("node_status", { node: "plan", attempt: 1, status: "succeeded", progress: 25, step: 1 }),
    ev("node_status", { node: "approve_plan", attempt: 1, status: "running" }),
    ev("node_status", { node: "approve_plan", attempt: 1, status: "waiting_human", runStatus: "waiting_human" }),
    ev("interrupt", { node: "approve_plan", attempt: 1, interrupt: { interruptId: "i1", stage: "plan", message: "Approve the plan?", plan: "1. x" } }),
  ];
}

function decision(d: "approve" | "request_changes" | "reject", attempt = 1): RunEvent[] {
  return [
    ev("review_decision", { node: "approve_plan", attempt, runStatus: "running", reviewDecision: { interruptId: `i${attempt}`, stage: "plan", decision: d, approverEmail: "va.ondrej@example.com", comment: d === "request_changes" ? "Use Decimal" : undefined } }),
    ev("node_status", { node: "approve_plan", attempt, status: "succeeded", progress: 25, step: 1 }),
  ];
}

function line(kind: AgentLine["kind"], text: string, tool?: string, arg?: string): AgentLine {
  return { seq: seq++, node: "write_tests", attempt: 1, at: "2026-11-20T13:49:41Z", kind, text, tool, arg };
}

suite("T21 units", () => {
  suite("session fold: a gate sent back with Request changes", () => {
    test("is not approved while the step reruns, and is undecided on its next attempt", () => {
      const events = [...started(), ...decision("request_changes"), ev("node_status", { node: "plan", attempt: 2, status: "running" })];
      const s = foldEvents(R, events);
      const gate = s.nodes["approve_plan"];
      assert.equal(gate.status, "succeeded", "the runner finishes the gate as succeeded");
      assert.equal(gate.decision, "request_changes");
      assert.equal(nodeDone(s, "approve_plan"), false, "a gate with changes requested is not done");
      assert.equal(s.currentNode, "plan");
      assert.equal(s.currentAttempt, 2);

      const again = foldEvents(R, [
        ...events,
        ev("node_status", { node: "plan", attempt: 2, status: "succeeded" }),
        ev("node_status", { node: "approve_plan", attempt: 2, status: "running" }),
        ev("node_status", { node: "approve_plan", attempt: 2, status: "waiting_human", runStatus: "waiting_human" }),
        ev("interrupt", { node: "approve_plan", attempt: 2, interrupt: { interruptId: "i2", stage: "plan", message: "Approve the plan?" } }),
      ]);
      assert.equal(again.nodes["approve_plan"].decision, undefined, "a new attempt clears the old decision");
      assert.equal(again.nodes["approve_plan"].approvedBy, undefined);
      assert.ok(again.interrupt && again.interrupt.seq > (s.interrupt?.seq ?? -1), "each gate round has its own interrupt seq");
    });

    test("the latest decision wins: approve after request_changes is done", () => {
      const s = foldEvents(R, [
        ...started(),
        ...decision("request_changes"),
        ev("node_status", { node: "plan", attempt: 2, status: "running" }),
        ev("node_status", { node: "plan", attempt: 2, status: "succeeded" }),
        ev("node_status", { node: "approve_plan", attempt: 2, status: "running" }),
        ev("node_status", { node: "approve_plan", attempt: 2, status: "waiting_human", runStatus: "waiting_human" }),
        ev("interrupt", { node: "approve_plan", attempt: 2, interrupt: { interruptId: "i2", stage: "plan" } }),
        ...decision("approve", 2),
      ]);
      assert.equal(s.nodes["approve_plan"].decision, "approve");
      assert.equal(nodeDone(s, "approve_plan"), true);
    });

    test("reject is not done either", () => {
      const s = foldEvents(R, [...started(), ...decision("reject")]);
      assert.equal(nodeDone(s, "approve_plan"), false);
    });

    test("agent lines carry their event time and the step its start time", () => {
      const s = foldEvents(R, [
        ...started(),
        ...decision("approve"),
        ev("node_status", { node: "write_tests", attempt: 1, status: "running" }),
        ev("agent_output", { node: "write_tests", attempt: 1, agentOutput: { block: "tool_use", tool: { id: "t1", name: "Read", input: { file_path: "src/app/orders.py" } } } }),
      ]);
      const last = s.output[s.output.length - 1];
      assert.ok(last.at.startsWith("2026-11-20T"));
      assert.equal(last.tool, "Read");
      assert.equal(last.arg, "src/app/orders.py");
      assert.ok(s.nodes["write_tests"].startedAt);
      assert.equal(s.lastActivityAt, last.at);
    });
  });

  suite("tool_use → plain language", () => {
    const cases: [string, string, string][] = [
      ["Read", "src/app/orders.py", "Reading orders.py"],
      ["Edit", "src/app/orders.py", "Editing orders.py"],
      ["Write", "tests/test_orders.py", "Editing test_orders.py"],
      ["Bash", "uv run pytest tests -q", "Running tests"],
      ["Bash", "pnpm test", "Running tests"],
      ["Bash", "git diff --stat", "Running git diff"],
      ["Grep", "def total", "Searching def total"],
      ["Glob", "**/*.py", "Searching **/*.py"],
      ["FancyNewTool", "x", "Using FancyNewTool"],
    ];
    for (const [tool, arg, want] of cases) {
      test(`${tool} ${arg} → ${want}`, () => assert.equal(describeTool(tool, arg).text, want));
    }
    test("thinking, text and tool results", () => {
      assert.equal(describeLine(line("thinking", "hmm"))?.text, "Thinking…");
      assert.equal(describeLine(line("text", "\n## **Plan**: three steps\nmore"))?.text, "Plan: three steps");
      assert.equal(describeLine(line("result", "ok")), undefined);
      assert.equal(describeLine(line("denied", "Bash rm -rf /", "Bash", "rm -rf /"))?.text, "Blocked: Running rm -rf");
    });
  });

  suite("tab title and icon", () => {
    const base = (over: Partial<SessionView>): SessionView => ({ ...foldEvents(R, started()), ...over });

    test("word-boundary cut, never inside a word", () => {
      assert.equal(shortTitle("Brainstorming, chci tu s tebou probrat novou appku"), "Brainstorming, chci tu s…");
      assert.equal(shortTitle("Short title"), "Short title");
      assert.equal(shortTitle("Supercalifragilisticexpialidocious app"), "Supercalifragilisticexpi…");
    });
    test("Czech title with diacritics keeps whole words and characters", () => {
      const t = shortTitle("Přidej účtování slev pro řádky objednávek");
      assert.equal(t, "Přidej účtování slev pro…");
      assert.ok([...t].length <= 25);
    });
    test("waiting: the gate name and the amber icon", () => {
      const s = foldEvents(R, started());
      assert.deepEqual(tabChrome(s), { title: "Per-line percentage… · plan", icon: "waiting" });
      const pr = base({ interrupt: { ...s.interrupt!, node: "approve_pr" } });
      assert.equal(tabChrome(pr).title, "Per-line percentage… · review");
      const bs = base({ interrupt: { ...s.interrupt!, node: "approve_brainstorm" } });
      assert.equal(tabChrome(bs).title, "Per-line percentage… · brainstorm");
      const other = base({ interrupt: { ...s.interrupt!, node: "approve_deploy" } });
      assert.equal(tabChrome(other).title, "Per-line percentage… · your turn");
    });
    test("running: the current action, else the step; % only from 5 %", () => {
      const s = foldEvents(R, [
        ...started(),
        ...decision("approve"),
        ev("node_status", { node: "write_tests", attempt: 1, status: "running", progress: 3 }),
      ]);
      s.progress = 3;
      assert.deepEqual(tabChrome(s), { title: "Per-line percentage… · writing tests", icon: "running" });
      s.output.push({ ...line("tool", "Edit a.py", "Edit", "a.py") });
      s.progress = 30;
      assert.equal(tabChrome(s).title, "Per-line percentage… · editing · 30 %");
    });
    test("finished states", () => {
      assert.deepEqual(tabChrome(base({ status: "failed" })), { title: "Per-line percentage… · failed", icon: "failed" });
      assert.deepEqual(tabChrome(base({ status: "succeeded" })), { title: "Per-line percentage… · done", icon: "done" });
      assert.equal(tabIcon(base({ status: "rejected" })), "stopped");
      assert.equal(tabIcon(base({ status: "cancelled" })), "stopped");
    });
  });

  suite("liveness", () => {
    test("alive → working, dead + unfinished → stopped, finished → nothing, missing lock → working", () => {
      assert.equal(livenessState("running", true), "working");
      assert.equal(livenessState("running", false), "stopped");
      assert.equal(livenessState("succeeded", false), "none");
      assert.equal(livenessState("waiting_human", false), "none");
      assert.equal(livenessState("running", undefined), "working");
    });
    test("elapsed clock", () => {
      assert.equal(elapsed("2026-11-20T13:49:41Z", Date.parse("2026-11-20T13:51:55Z")), "2:14");
      assert.equal(elapsed("2026-11-20T12:00:00Z", Date.parse("2026-11-20T13:02:03Z")), "1:02:03");
    });
  });

  suite("step counters and recent actions", () => {
    test("unique files, tool calls, output tokens of the current attempt only", () => {
      const s = foldEvents(R, [
        ...started(),
        ...decision("approve"),
        ev("node_status", { node: "write_tests", attempt: 1, status: "running" }),
        ev("agent_output", { node: "write_tests", attempt: 1, agentOutput: { block: "tool_use", tool: { id: "a", name: "Read", input: { file_path: "a.py" } } } }),
        ev("agent_output", { node: "write_tests", attempt: 1, agentOutput: { block: "tool_result", toolUseId: "a", text: "..." } }),
        ev("agent_output", { node: "write_tests", attempt: 1, agentOutput: { block: "tool_use", tool: { id: "b", name: "Edit", input: { file_path: "a.py" } } } }),
        ev("agent_output", { node: "write_tests", attempt: 1, agentOutput: { block: "tool_use", tool: { id: "c", name: "Write", input: { file_path: "t.py" } } } }),
        ev("agent_output", { node: "write_tests", attempt: 1, agentOutput: { block: "tool_use", tool: { id: "d", name: "Bash", input: { command: "uv run pytest" } } } }),
        ev("usage", { node: "write_tests", attempt: 1, usage: { runId: R, node: "write_tests", attempt: 1, model: "m", adapter: "claude", input: 1, output: 1200, cache_write: 0, cache_read: 0 } }),
        ev("usage", { node: "plan", attempt: 1, usage: { runId: R, node: "plan", attempt: 1, model: "m", adapter: "claude", input: 1, output: 999, cache_write: 0, cache_read: 0 } }),
      ]);
      assert.deepEqual(stepCounters(s), { files: 2, toolCalls: 4, outputTokens: 1200 });
      assert.deepEqual(recentActions(s, 3).map((a) => a.text), ["Running tests", "Editing t.py", "Editing a.py"]);
    });
  });
});
