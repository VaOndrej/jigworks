// Standalone UI for screenshots and development: the real webview components inside a VS Code-like
// frame (docs/mockups/jigworks-ui.html), fed by the recorded runs in packages/contracts/fixtures —
// no VS Code, no runner, no tokens.
//   index.html?screen=new                     new session
//   index.html?screen=session&run=run_fd_0007 a session (any recorded run)
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { GraphJSON, RunEvent } from "@jigworks/contracts";
import graph13 from "../../../packages/contracts/fixtures/graph/feature-development-1.3.0.graph.json";
import r1 from "../../../packages/contracts/fixtures/runs/run_fd_0001-approved-first-time.jsonl";
import r2 from "../../../packages/contracts/fixtures/runs/run_fd_0002-fix-loops-request-changes.jsonl";
import r5 from "../../../packages/contracts/fixtures/runs/run_fd_0005-waiting-for-review.jsonl";
import r6 from "../../../packages/contracts/fixtures/runs/run_fd_0006-paused-usage-limit.jsonl";
import r7 from "../../../packages/contracts/fixtures/runs/run_fd_0007-running-implement.jsonl";
import md1 from "../test-fixtures/runs/run_md_0001-markdown-questions.jsonl";
import md2 from "../test-fixtures/runs/run_md_0002-changes-requested.jsonl";
import md3 from "../test-fixtures/runs/run_md_0003-running-write-tests.jsonl";
import md4 from "../test-fixtures/runs/run_md_0004-brainstorm-round-1.jsonl";
import { foldEvents } from "../src/shared/session";
import { tabChrome } from "../src/shared/tabTitle";
import type { HostState, ToHost, ToWebview, WorkflowInfo } from "../src/shared/messages";
import type { HostApi } from "./host";
import { useHostState, useSessions } from "./host";
import { NewSession } from "./NewSession";
import { RunView } from "./RunView";
import { Sidebar } from "./Sidebar";
import "./styles.css";
import "./standalone.css";

const parse = (text: string): RunEvent[] => text.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l) as RunEvent);

const RUNS: Record<string, RunEvent[]> = Object.fromEntries(
  [r7, r5, r2, r6, r1, md1, md2, md3, md4].map(parse).map((events) => [events[0].runId, events]),
);

const FD: WorkflowInfo = {
  key: "hub:feature-development@1.3.0",
  name: "feature-development",
  version: "1.3.0",
  release: "feature-development@1.3.0",
  digest: "sha256:e941f267e18b97560bcb4292047781b0844c70f6fea282c8c2a1c14733854c30",
  path: "",
  source: "hub",
  channel: "stable",
  plannedPath: ["plan", "approve_plan", "write_tests", "implement", "review", "gate", "approve_pr", "open_pr", "summary"],
  interruptNodes: ["approve_plan", "approve_pr"],
  models: { default: "claude-sonnet-5", nodes: { write_tests: "claude-haiku-4-5-20251001", summary: "claude-haiku-4-5-20251001" } },
  allowedTools: ["Read", "Edit", "Write", "Bash(pytest:*)", "Bash(git diff:*)"],
  network: false,
  graph: graph13 as GraphJSON,
};
const OLDER: WorkflowInfo = { ...FD, key: "hub:feature-development@1.2.0", version: "1.2.0", release: "feature-development@1.2.0", channel: "beta" };

const params = new URLSearchParams(location.search);
const screen = params.get("screen") ?? "session";
const runParam = params.get("run") ?? "run_fd_0007";
const visibleRuns = (params.get("runs") ?? "run_fd_0007,run_fd_0005,run_fd_0002").split(",");
// ?now=<ISO> freezes the clock (elapsed timers in screenshots); ?alive=0 reports the runner PID gone.
if (params.get("now")) window.__JIGWORKS_NOW__ = params.get("now")!;

const state: HostState = {
  workflows: params.get("local") === "changed"
    ? [FD, OLDER, { ...FD, key: "workspace:feature-development@1.3.0", source: "workspace", channel: undefined, digest: "sha256:local", changed: true }]
    : [FD, OLDER],
  selectedWorkflow: FD.key,
  sessions: Object.fromEntries(visibleRuns.filter((r) => RUNS[r]).map((r) => [r, RUNS[r]])),
  running: ["run_fd_0007", "run_md_0002", "run_md_0003"],
  liveness: params.get("alive") === "0" ? { [runParam]: { alive: false, checkedAt: "2026-11-20T14:00:00Z" } } : {},
  preflight: { ok: true, authMethod: "claude.ai", subscriptionType: "max" },
  activeRun: screen === "session" ? runParam : undefined,
  hub: (
    {
      none: { url: "", hasPassword: false, state: "not_configured" },
      error: { url: "https://jigworks-abc123-team.vercel.app", hasPassword: true, state: "error", message: "The hub at https://jigworks-abc123-team.vercel.app is behind Vercel Deployment Protection. Set the protection bypass secret (gear in the Jigworks view → “Set Vercel protection bypass secret”) or use the production hub URL." },
    } as Record<string, HostState["hub"]>
  )[params.get("hub") ?? ""] ?? { url: "https://jigworks.vercel.app", hasPassword: true, state: "connected" },
};
if (screen === "session" && RUNS[runParam]) state.sessions[runParam] = RUNS[runParam];

const listeners: string[] = [];
const decides: ToHost[] = [];
const mock: HostApi = {
  postMessage(msg: ToHost) {
    listeners.push(msg.type);
    const send = (m: ToWebview) => window.postMessage(m, "*");
    if (msg.type === "decide") {
      decides.push(msg);
      // ?replay=round2: play the runner's answer to Request changes: the gate closes, the step
      // reruns and stops at the same gate again (the next brainstorming round).
      const events = state.sessions[msg.runId];
      if (params.get("replay") === "round2" && msg.decision === "request_changes" && events) {
        const s = foldEvents(msg.runId, events);
        const gate = s.interrupt!;
        const attempt = (s.nodes[gate.node]?.attempt ?? 1) + 1;
        const step = gate.node.replace(/^approve_/, "");
        let seq = s.lastSeq;
        const at = "2026-11-20T11:05:00Z";
        const base = { runId: msg.runId, at, release: s.release };
        const more = [
          { ...base, seq: ++seq, kind: "review_decision", node: gate.node, attempt: attempt - 1, runStatus: "running", reviewDecision: { interruptId: gate.interruptId, stage: gate.stage, decision: "request_changes", approverEmail: "va.ondrej@example.com", comment: msg.comment } },
          { ...base, seq: ++seq, kind: "node_status", node: gate.node, attempt: attempt - 1, status: "succeeded" },
          { ...base, seq: ++seq, kind: "node_status", node: step, attempt, status: "running" },
          { ...base, seq: ++seq, kind: "node_status", node: step, attempt, status: "succeeded" },
          { ...base, seq: ++seq, kind: "node_status", node: gate.node, attempt, status: "running" },
          { ...base, seq: ++seq, kind: "node_status", node: gate.node, attempt, status: "waiting_human", runStatus: "waiting_human" },
          { ...base, seq: ++seq, kind: "interrupt", node: gate.node, attempt, interrupt: { interruptId: `${gate.interruptId}_r${attempt}`, stage: gate.stage, message: `Brainstorming, round ${attempt}: two more questions.`, plan: "QUESTIONS:\n\n1. **Fees:** a flat 0.1 % per fill?\n2. **Timeframes:** 1m to 1d?" } },
        ] as unknown as RunEvent[];
        state.sessions[msg.runId] = [...events, ...more];
        setTimeout(() => more.forEach((event) => send({ type: "event", runId: msg.runId, event })), 150);
      }
    }
    if (msg.type === "ready") send({ type: "state", state });
    if (msg.type === "selectWorkflow") {
      state.selectedWorkflow = msg.key;
      send({ type: "state", state: { ...state } });
    }
    if (msg.type === "openSession") location.search = `?screen=session&run=${msg.runId}&runs=${visibleRuns.join(",")}`;
    if (msg.type === "newSession") location.search = `?screen=new&runs=${visibleRuns.join(",")}`;
  },
};
window.__JIGWORKS_HOST__ = mock;
(window as unknown as { __messages: string[] }).__messages = listeners;
(window as unknown as { __decides: ToHost[] }).__decides = decides;

function Frame() {
  const hostState = useHostState(screen === "new" ? "new" : "session", runParam);
  const sessions = useSessions(hostState);
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(hostState.workflows.length > 0), [hostState.workflows.length]);
  const active = sessions.find((s) => s.runId === runParam);
  const open = sessions.filter((s) => s.status === "running" || s.status === "waiting_human");
  const title = screen === "new" ? "Jigworks: New session" : `Jigworks: ${active?.title ?? runParam}`;
  return (
    <div className="vs" data-ready={ready ? "1" : "0"}>
      <div className="vs-title">jigworks — {title}</div>
      <div className="vs-main">
        <div className="vs-activity" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#7D818C" strokeWidth="1.6"><path d="M6 3h9l4 4v14H6z" /></svg>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#7D818C" strokeWidth="1.6"><circle cx="11" cy="11" r="6" /><path d="M20 20l-4-4" /></svg>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#7D818C" strokeWidth="1.6"><circle cx="6" cy="6" r="2" /><circle cx="6" cy="18" r="2" /><circle cx="18" cy="9" r="2" /><path d="M6 8v8M18 11c0 4-6 3-12 5" /></svg>
          <div className="vs-active-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#F59E5B" strokeWidth="2"><path d="M4 4h10v6H8v10H4z" /><path d="M14 14h6v6h-6z" /></svg></div>
        </div>
        <div className="vs-side"><Sidebar state={hostState} sessions={sessions} activeRun={hostState.activeRun} /></div>
        <div className="vs-editor">
          <div className="vs-tabs">
            {sessions.filter((s) => s.status === "running" || s.status === "waiting_human" || s.runId === runParam).map((s) => (
              <div key={s.runId} className={`vs-tab${screen === "session" && s.runId === runParam ? " on" : ""}`} data-run={s.runId}>
                {/* The same title and icon the extension sets on the real WebviewPanel (tabChrome). */}
                <img className="vs-tab-icon" src={`../../media/state-${tabChrome(s).icon}.svg`} alt="" width={14} height={14} />
                {tabChrome(s).title}
              </div>
            ))}
            {screen === "new" && <div className="vs-tab on new">New session</div>}
          </div>
          <div className="vs-content">
            {screen === "new" ? (
              <NewSession
                state={hostState}
                sessions={sessions}
                initialPrompt="Allow cancelling a partially filled order: cancel keeps the filled quantity, releases the rest, and the position stays the sum of fills. Keep every invariant in INVARIANTS.md."
                initialAttachments={["sample-repo/sample_repo/orders.py", "sample-repo/INVARIANTS.md"]}
              />
            ) : active ? (
              <RunView state={hostState} s={active} initialTab={params.get("tab") === "output" ? "output" : "activity"} />
            ) : null}
          </div>
        </div>
      </div>
      <div className="vs-status">
        <span>{active?.branch ?? "jigworks"}</span>
        <span>Jigworks: {open.filter((s) => s.status === "running").length} running · {open.filter((s) => s.status === "waiting_human").length} needs your review</span>
        <span className="push-right">runner 0.1 · standalone replay of recorded runs</span>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Frame />);
