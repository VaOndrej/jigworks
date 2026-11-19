// A session's view model, folded from its RunEvents. Pure: used by the extension host and the
// webview alike, and by the standalone UI that replays the recorded runs.
import type {
  GateResultPayload,
  InterruptPayload,
  NodeStatus,
  RunEvent,
  RunStatus,
  UsageRecord,
} from "@jigworks/contracts";

export interface NodeState {
  id: string;
  status: NodeStatus;
  attempt: number;
  at: string;
  approvedBy?: string;
  decision?: string;
}

export interface AgentLine {
  seq: number;
  node: string;
  attempt: number;
  kind: "text" | "tool" | "result" | "denied" | "thinking";
  text: string;
  isError?: boolean;
}

export interface ActivityLine {
  seq: number;
  at: string;
  text: string;
  tone: "ok" | "fail" | "human" | "info";
}

export interface SessionView {
  runId: string;
  title: string;
  workflowId: string;
  release: string;
  digest: string;
  status: RunStatus;
  progress: number;
  step: number;
  stepsPlanned: number;
  plannedPath: string[];
  models: { default: string; nodes?: Record<string, string> };
  currentNode?: string;
  currentAttempt?: number;
  nodes: Record<string, NodeState>;
  fixLoops: number;
  followUps: number;
  interrupt?: InterruptPayload & { node: string };
  lastGate?: GateResultPayload;
  usage: { input: number; output: number; cache_write: number; cache_read: number; cliCostUsd: number };
  usageRecords: UsageRecord[];
  output: AgentLine[];
  activity: ActivityLine[];
  branch?: string;
  prUrl?: string;
  error?: { code: string; message: string };
  usageLimit?: { status: string; resetsAt?: string };
  startedAt?: string;
  updatedAt?: string;
  authorEmail?: string;
  lastSeq: number;
}

const MAX_OUTPUT = 400;
const MAX_ACTIVITY = 200;

export function emptySession(runId: string): SessionView {
  return {
    runId,
    title: runId,
    workflowId: "",
    release: "",
    digest: "",
    status: "running",
    progress: 0,
    step: 0,
    stepsPlanned: 1,
    plannedPath: [],
    models: { default: "" },
    nodes: {},
    fixLoops: 0,
    followUps: 0,
    usage: { input: 0, output: 0, cache_write: 0, cache_read: 0, cliCostUsd: 0 },
    usageRecords: [],
    output: [],
    activity: [],
    lastSeq: -1,
  };
}

function time(at: string): string {
  return at.slice(11, 16);
}

function push<T>(list: T[], item: T, max: number): void {
  list.push(item);
  if (list.length > max) list.splice(0, list.length - max);
}

/** Apply one event. Events at or below `lastSeq` are ignored, so replays are idempotent. */
export function applyEvent(s: SessionView, e: RunEvent): SessionView {
  const seq = e.seq ?? s.lastSeq + 1;
  if (seq <= s.lastSeq) return s;
  s.lastSeq = seq;
  s.updatedAt = e.at;
  if (e.release) s.release = e.release;
  if (e.digest) s.digest = e.digest;
  if (typeof e.progress === "number") s.progress = Math.max(s.progress, e.progress);
  if (typeof e.step === "number") s.step = Math.max(s.step, e.step);
  if (e.stepsPlanned) s.stepsPlanned = e.stepsPlanned;
  const kind = e.kind ?? "node_status";
  const node = e.node ?? "";
  const attempt = e.attempt ?? 1;

  switch (kind) {
    case "run_started": {
      const p = e.runStarted!;
      s.title = p.title ?? s.runId;
      s.workflowId = p.workflowId;
      s.release = p.release;
      s.digest = p.digest;
      s.models = p.models;
      s.plannedPath = p.plannedPath ?? [];
      s.branch = p.branch;
      s.startedAt = e.at;
      s.authorEmail = p.authorEmail;
      push(s.activity, { seq, at: e.at, text: `${time(e.at)} started ${p.release}`, tone: "info" }, MAX_ACTIVITY);
      break;
    }
    case "node_status": {
      const status = e.status!;
      const prev = s.nodes[node];
      s.nodes[node] = { ...prev, id: node, status, attempt, at: e.at };
      if (status === "running" || status === "waiting_human") {
        s.currentNode = node;
        s.currentAttempt = attempt;
      } else if (s.currentNode === node) {
        s.currentNode = undefined;
      }
      if (node === "fix" && status === "succeeded") s.fixLoops += 1;
      if (status !== "running") {
        const tone = status === "succeeded" ? "ok" : status === "waiting_human" ? "human" : status === "failed" ? "fail" : "info";
        const label = status === "waiting_human" ? "waiting for you" : status;
        push(s.activity, { seq, at: e.at, text: `${time(e.at)} ${node}${attempt > 1 ? ` #${attempt}` : ""} ${label}`, tone }, MAX_ACTIVITY);
      }
      break;
    }
    case "interrupt":
      s.interrupt = { ...e.interrupt!, node };
      break;
    case "review_decision": {
      const d = e.reviewDecision!;
      if (d.decision === "request_changes") s.followUps += 1;
      const n = s.nodes[node];
      if (n) s.nodes[node] = { ...n, approvedBy: d.approverEmail, decision: d.decision };
      s.interrupt = undefined;
      const verb = d.decision === "approve" ? "approved" : d.decision === "reject" ? "rejected" : "requested changes";
      push(s.activity, { seq, at: e.at, text: `${time(e.at)} ${d.approverEmail} ${verb} (${d.stage})${d.comment ? `: ${d.comment}` : ""}`, tone: "human" }, MAX_ACTIVITY);
      break;
    }
    case "gate_result": {
      s.lastGate = e.gateResult;
      const failed = e.gateResult!.checks.filter((c) => !c.passed).map((c) => c.name);
      push(s.activity, {
        seq, at: e.at,
        text: `${time(e.at)} gate ${e.gateResult!.passed ? "PASS" : `FAIL (${failed.join(", ")})`}`,
        tone: e.gateResult!.passed ? "ok" : "fail",
      }, MAX_ACTIVITY);
      break;
    }
    case "agent_output": {
      const o = e.agentOutput!;
      let line: AgentLine | undefined;
      if (o.block === "text" && o.text) line = { seq, node, attempt, kind: "text", text: o.text };
      else if (o.block === "thinking" && o.text) line = { seq, node, attempt, kind: "thinking", text: o.text };
      else if (o.block === "tool_use" && o.tool) {
        const input = o.tool.input ?? {};
        const arg = (input["command"] ?? input["file_path"] ?? input["pattern"] ?? input["path"] ?? "") as string;
        line = { seq, node, attempt, kind: o.denied ? "denied" : "tool", text: `${o.tool.name}${arg ? ` ${arg}` : ""}` };
      } else if (o.block === "tool_result") {
        line = { seq, node, attempt, kind: "result", text: (o.text ?? "").split("\n").slice(0, 3).join("\n"), isError: o.isError };
      }
      if (line) push(s.output, line, MAX_OUTPUT);
      break;
    }
    case "usage": {
      const u = e.usage!;
      s.usageRecords.push(u);
      s.usage.input += u.input;
      s.usage.output += u.output;
      s.usage.cache_write += u.cache_write;
      s.usage.cache_read += u.cache_read;
      s.usage.cliCostUsd += u.cliCostUsd ?? 0;
      break;
    }
    case "usage_limit":
      s.usageLimit = { status: e.usageLimit!.status, resetsAt: e.usageLimit!.resetsAt };
      break;
    case "error":
      s.error = { code: e.error!.code, message: e.error!.message };
      push(s.activity, { seq, at: e.at, text: `${time(e.at)} error: ${e.error!.message}`, tone: "fail" }, MAX_ACTIVITY);
      break;
    case "run_finished": {
      const sum = e.summary!;
      s.prUrl = sum.prUrl;
      push(s.activity, { seq, at: e.at, text: `${time(e.at)} run ${sum.status}${sum.prUrl ? ` · ${sum.prUrl}` : ""}`, tone: sum.status === "succeeded" ? "ok" : "fail" }, MAX_ACTIVITY);
      break;
    }
  }
  if (e.runStatus) s.status = e.runStatus;
  if (s.status !== "waiting_human") s.interrupt = s.status === "running" ? s.interrupt : undefined;
  return s;
}

export function foldEvents(runId: string, events: RunEvent[]): SessionView {
  const s = emptySession(runId);
  for (const e of [...events].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0))) applyEvent(s, e);
  return s;
}

export function modelFor(s: SessionView, node: string): string {
  return s.models.nodes?.[node] ?? s.models.default;
}

export const TERMINAL: RunStatus[] = ["succeeded", "failed", "rejected", "cancelled"];

export function needsYou(s: SessionView): boolean {
  return s.status === "waiting_human";
}
