// What the agent is doing, in plain words, from the folded agent output. Pure: used by the run
// view's Now card, the graph node and the editor tab title.
import type { AgentLine, SessionView } from "./session";

export interface Action {
  seq: number;
  at: string;
  /** "Reading orders.py", "Running tests", "Thinking…", or the first line the agent wrote. */
  text: string;
  /** One or two lowercase words for the tab title ("reading", "running tests"), when known. */
  short?: string;
}

const TEST_COMMAND = /\b(pytest|py\.test|unittest|vitest|jest|mocha|playwright test|go test|cargo test|(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test|uv run pytest|tox|nox)\b/;

function base(p: string): string {
  const clean = p.replace(/[\\/]+$/, "");
  return clean.split(/[\\/]/).pop() || clean;
}

function cut(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

function firstLine(text: string): string {
  const line = text.split("\n").map((l) => l.trim()).find((l) => l.length > 0) ?? "";
  return line.replace(/^#+\s*/, "").replace(/^[-*>]\s+/, "").replace(/\*\*|__|`/g, "");
}

/** tool_use → plain language. Unknown tools fall back to "Using <Tool>". */
export function describeTool(tool: string, arg = ""): { text: string; short?: string } {
  const a = arg.trim();
  switch (tool) {
    case "Read":
      return { text: a ? `Reading ${base(a)}` : "Reading a file", short: "reading" };
    case "Edit":
    case "MultiEdit":
    case "Write":
    case "NotebookEdit":
      return { text: a ? `Editing ${base(a)}` : "Editing a file", short: "editing" };
    case "Bash": {
      if (TEST_COMMAND.test(a)) return { text: "Running tests", short: "running tests" };
      const words = a.split(/\s+/).filter(Boolean).slice(0, 2).join(" ");
      return { text: words ? `Running ${cut(words, 32)}` : "Running a command", short: "running" };
    }
    case "Grep":
    case "Glob":
      return { text: a ? `Searching ${cut(a, 40)}` : "Searching the code", short: "searching" };
    case "LS":
      return { text: a ? `Listing ${base(a)}` : "Listing files", short: "listing" };
    case "WebFetch":
    case "WebSearch":
      return { text: "Searching the web", short: "on the web" };
    case "TodoWrite":
      return { text: "Updating its to-do list", short: "planning" };
    case "Task":
    case "Agent":
      return { text: "Delegating to a subagent", short: "delegating" };
    default:
      return { text: `Using ${tool}` };
  }
}

/** One agent line → an action, or undefined for lines that are not actions (tool results). */
export function describeLine(l: AgentLine): Action | undefined {
  if (l.kind === "result") return undefined;
  if (l.kind === "thinking") return { seq: l.seq, at: l.at, text: "Thinking…", short: "thinking" };
  if (l.kind === "text") {
    const line = firstLine(l.text);
    return line ? { seq: l.seq, at: l.at, text: cut(line, 90), short: "writing" } : undefined;
  }
  const tool = l.tool ?? l.text.split(" ")[0];
  const arg = l.arg ?? l.text.slice(tool.length).trim();
  const d = describeTool(tool, arg);
  if (l.kind === "denied") return { seq: l.seq, at: l.at, text: `Blocked: ${d.text}`, short: "blocked" };
  return { seq: l.seq, at: l.at, ...d };
}

/** The current step's lines (the node and attempt that run now). */
export function stepLines(s: SessionView): AgentLine[] {
  const node = s.currentNode;
  if (!node) return [];
  const attempt = s.currentAttempt ?? 1;
  return s.output.filter((l) => l.node === node && l.attempt === attempt);
}

/** The latest actions of the current step, newest first. */
export function recentActions(s: SessionView, max = 5): Action[] {
  const out: Action[] = [];
  const lines = stepLines(s);
  for (let i = lines.length - 1; i >= 0 && out.length < max; i--) {
    const a = describeLine(lines[i]);
    if (a) out.push(a);
  }
  return out;
}

export interface StepCounters {
  files: number;
  toolCalls: number;
  outputTokens: number;
}

const FILE_TOOLS = new Set(["Read", "Edit", "MultiEdit", "Write", "NotebookEdit"]);

export function stepCounters(s: SessionView): StepCounters {
  const lines = stepLines(s);
  const files = new Set(lines.filter((l) => l.kind === "tool" && FILE_TOOLS.has(l.tool ?? "") && l.arg).map((l) => l.arg));
  const attempt = s.currentAttempt ?? 1;
  const outputTokens = s.usageRecords
    .filter((u) => u.node === s.currentNode && (u.attempt ?? 1) === attempt)
    .reduce((a, u) => a + u.output, 0);
  return { files: files.size, toolCalls: lines.filter((l) => l.kind === "tool" || l.kind === "denied").length, outputTokens };
}

const GERUND: Record<string, string> = {
  triage: "triaging",
  brainstorm: "brainstorming",
  plan: "planning",
  write_tests: "writing tests",
  implement: "implementing",
  review: "reviewing",
  gate: "testing",
  fix: "fixing",
  open_pr: "opening the PR",
  summary: "summarizing",
};

/** "implementing", "writing tests"; unknown steps fall back to their label. */
export function stepGerund(node: string): string {
  return GERUND[node] ?? node.replace(/_/g, " ");
}

/** m:ss (or h:mm:ss) between two ISO times; never negative. */
export function elapsed(fromIso: string | undefined, nowMs: number): string {
  if (!fromIso) return "";
  const secs = Math.max(0, Math.floor((nowMs - Date.parse(fromIso)) / 1000));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const ss = String(secs % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** "4 s ago", "3 min ago". */
export function ago(iso: string | undefined, nowMs: number): string {
  if (!iso) return "";
  const secs = Math.max(0, Math.floor((nowMs - Date.parse(iso)) / 1000));
  if (secs < 60) return `${secs} s ago`;
  const m = Math.floor(secs / 60);
  return m < 60 ? `${m} min ago` : `${Math.floor(m / 60)} h ago`;
}

export type Liveness = "working" | "stopped" | "none";

/**
 * Is the agent working? Silence in the event stream is normal (a tool_use arrives only when its
 * whole block is generated), so only a runner PID that is definitely gone means "stopped".
 * `alive` is undefined when the lock is missing or unreadable: never guess a failure.
 */
export function livenessState(status: SessionView["status"], alive: boolean | undefined): Liveness {
  if (status !== "running") return "none";
  return alive === false ? "stopped" : "working";
}
