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
  /** When the current attempt started running (the `at` of its `running` status). */
  startedAt?: string;
  approvedBy?: string;
  /** Latest human decision on this gate's current attempt; cleared when the gate runs again. */
  decision?: string;
  decidedAt?: string;
}

export interface AgentLine {
  seq: number;
  node: string;
  attempt: number;
  kind: "text" | "tool" | "result" | "denied" | "thinking";
  text: string;
  /** Event time, so "x s ago" is computed from the run, not from the render. */
  at: string;
  /** tool_use only: the tool name and its main argument (path, command, pattern). */
  tool?: string;
  arg?: string;
  isError?: boolean;
}

export interface ActivityLine {
  seq: number;
  at: string;
  text: string;
  tone: "ok" | "fail" | "human" | "info";
}

/** One review, gate or fix attempt after the implementation: what the human reads to see whether
 *  the fix loop is getting anywhere. `open` = open findings (review) or failed checks (gate). */
export interface FixRound {
  node: "review" | "gate" | "fix";
  attempt: number;
  status: string;
  at: string;
  open?: number;
  /** review: first open finding; gate: failed checks; fix: the fixer's first line. */
  text?: string;
  changedFiles?: number;
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
  /** The open gate; `seq` is the interrupt event's seq, unique per round. */
  interrupt?: InterruptPayload & { node: string; seq: number };
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
  /** Time of the latest agent_output / usage event (the agent's last sign of life). */
  lastActivityAt?: string;
  authorEmail?: string;
  fixRounds: FixRound[];
  /** Last agent text per `node#attempt` (review and fix only), to summarise the round. */
  lastText: Record<string, string>;
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
    fixRounds: [],
    lastText: {},
    lastSeq: -1,
  };
}

const FINDING = /^\s*[-*]?\s*\**\[?F(\d+)\]?\**[:.)]?\s+(.*)$/;
const BULLET = /^\s*[-*]\s+\S/;

/** Open findings in a review reply: lines with an ID (`- F3 ...`) not marked FIXED, otherwise the
 *  bullet lines; at least one when the verdict is FAIL. Mirrors the workflow's own count. */
export function reviewOpen(text: string, passed: boolean): { open: number; first?: string } {
  if (passed) return { open: 0 };
  const ids = new Map<string, string | undefined>();
  let bullets = 0;
  let firstBullet: string | undefined;
  for (const line of text.split("\n")) {
    const m = FINDING.exec(line);
    if (m) ids.set(m[1], m[2].replace(/^[\s\-—–:*]+/, "").toUpperCase().startsWith("FIXED") ? undefined : line.trim().replace(/^[-*]\s*/, ""));
    else if (BULLET.test(line)) {
      bullets += 1;
      firstBullet ??= line.trim().replace(/^[-*]\s*/, "");
    }
  }
  if (ids.size) {
    const open = [...ids.values()].filter((v) => v !== undefined) as string[];
    return { open: Math.max(open.length, 1), first: open[0] };
  }
  return { open: Math.max(bullets, 1), first: firstBullet };
}

function firstLine(text: string, max = 110): string {
  const line = text.split("\n").map((l) => l.trim().replace(/^[#*\-\s]+/, "")).find((l) => l) ?? "";
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

/** ` · 2 open (was 3) · F2 ...` for the activity line of a review, gate or fix round. */
function roundDetail(r: FixRound, before?: FixRound): string {
  const parts: string[] = [];
  if (r.node === "fix") {
    if (r.text) parts.push(r.text);
    if (r.changedFiles !== undefined) parts.push(`${r.changedFiles} file${r.changedFiles === 1 ? "" : "s"} changed`);
  } else if (r.status === "failed" && r.open !== undefined) {
    const unit = r.node === "review" ? "open finding" : "failed check";
    parts.push(`${r.open} ${unit}${r.open === 1 ? "" : "s"}${before?.open !== undefined ? ` (was ${before.open})` : ""}`);
    if (r.node === "review" && r.text) parts.push(r.text);
  }
  return parts.length ? ` · ${parts.join(" · ")}` : "";
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
      const again = status === "running" || status === "waiting_human";
      s.nodes[node] = {
        ...prev,
        id: node,
        status,
        attempt,
        at: e.at,
        // A new attempt of a gate starts undecided: an older request_changes must not linger.
        ...(again ? { approvedBy: undefined, decision: undefined, decidedAt: undefined } : {}),
        ...(status === "running" ? { startedAt: e.at } : {}),
      };
      if (status === "running" || status === "waiting_human") {
        s.currentNode = node;
        s.currentAttempt = attempt;
      } else if (s.currentNode === node) {
        s.currentNode = undefined;
      }
      if (node === "fix" && status === "succeeded") s.fixLoops += 1;
      let detail = "";
      const looped = node === "fix" || ((node === "review" || node === "gate") && (s.fixRounds.length > 0 || status === "failed"));
      if (looped && (status === "succeeded" || status === "failed")) {
        const text = s.lastText[`${node}#${attempt}`] ?? "";
        const round: FixRound = { node: node as FixRound["node"], attempt, status, at: e.at, changedFiles: e.snapshot?.changedFiles?.length };
        if (node === "review") {
          const r = reviewOpen(text, status === "succeeded");
          round.open = r.open;
          round.text = r.first ? firstLine(r.first) : status === "succeeded" ? "passed" : undefined;
        } else if (node === "fix") {
          round.text = firstLine(text) || undefined;
        } else if (s.lastGate) {
          const failed = s.lastGate.checks.filter((c) => !c.passed).map((c) => c.name);
          round.open = failed.length;
          round.text = failed.length ? failed.join(", ") : "passed";
        }
        // A 1.6.0 fix that hit the limit did no work: it is the end of the loop, not a round.
        if (!(node === "fix" && status === "failed" && !text)) {
          const before = [...s.fixRounds].reverse().find((r) => r.node === node && r.open !== undefined);
          push(s.fixRounds, round, 100);
          detail = roundDetail(round, before);
        }
      }
      if (status !== "running") {
        const tone = status === "succeeded" ? "ok" : status === "waiting_human" ? "human" : status === "failed" ? "fail" : "info";
        const label = status === "waiting_human" ? "waiting for you" : status;
        push(s.activity, { seq, at: e.at, text: `${time(e.at)} ${node}${attempt > 1 ? ` #${attempt}` : ""} ${label}${detail}`, tone }, MAX_ACTIVITY);
      }
      break;
    }
    case "interrupt":
      s.interrupt = { ...e.interrupt!, node, seq };
      break;
    case "review_decision": {
      const d = e.reviewDecision!;
      if (d.decision === "request_changes") s.followUps += 1;
      const n = s.nodes[node];
      if (n) s.nodes[node] = { ...n, approvedBy: d.approverEmail, decision: d.decision, decidedAt: e.at };
      s.interrupt = undefined;
      const verb = d.decision === "approve" ? "approved" : d.decision === "reject" ? "rejected" : "requested changes";
      // approve_fix and a continued fix limit use the contract's "plan" stage; name what it was.
      const what = node === "approve_fix" || node === "fix" ? "fixes" : d.stage;
      push(s.activity, { seq, at: e.at, text: `${time(e.at)} ${d.approverEmail} ${verb} (${what})${d.comment ? `: ${d.comment}` : ""}`, tone: "human" }, MAX_ACTIVITY);
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
      const at = e.at;
      s.lastActivityAt = at;
      let line: AgentLine | undefined;
      if (o.block === "text" && o.text) line = { seq, node, attempt, at, kind: "text", text: o.text };
      else if (o.block === "thinking" && o.text) line = { seq, node, attempt, at, kind: "thinking", text: o.text };
      else if (o.block === "tool_use" && o.tool) {
        const input = o.tool.input ?? {};
        const raw = input["command"] ?? input["file_path"] ?? input["notebook_path"] ?? input["pattern"] ?? input["path"] ?? input["url"] ?? input["query"] ?? "";
        const arg = typeof raw === "string" ? raw : "";
        line = { seq, node, attempt, at, kind: o.denied ? "denied" : "tool", text: `${o.tool.name}${arg ? ` ${arg}` : ""}`, tool: o.tool.name, arg };
      } else if (o.block === "tool_result") {
        line = { seq, node, attempt, at, kind: "result", text: (o.text ?? "").split("\n").slice(0, 3).join("\n"), isError: o.isError };
      }
      if (line) push(s.output, line, MAX_OUTPUT);
      if (o.block === "text" && o.text && (node === "review" || node === "fix")) s.lastText[`${node}#${attempt}`] = o.text;
      break;
    }
    case "usage": {
      const u = e.usage!;
      s.lastActivityAt = e.at;
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
  if (e.runStatus) {
    // A failed run that is continued (a retry, or more fixes) is running again: its old error is history.
    if (e.runStatus === "running" && (s.status === "failed" || s.status === "cancelled")) s.error = undefined;
    s.status = e.runStatus;
  }
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

/** A step counts as done only when it succeeded and, for a gate, was not sent back with
 *  Request changes (the runner finishes such a gate as `succeeded`, then reruns the step). */
export function nodeDone(s: SessionView, id: string): boolean {
  const n = s.nodes[id];
  return n?.status === "succeeded" && n.decision !== "request_changes" && n.decision !== "reject";
}

export function needsYou(s: SessionView): boolean {
  return s.status === "waiting_human";
}
