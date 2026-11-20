// Bridge to the local runner (`jigworks` CLI). Several runner processes at once, keyed by runId.
//
// Every runner command prints the run's new RunEvents as JSONL on stdout and exits at the next
// interrupt, pause or end; the run's state lives on disk in the runner home. The bridge keeps the
// events of every session in memory, so a webview reload loses nothing, and `load()` rebuilds
// them from the runner after a window reload.
import { spawn, type ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import { randomBytes } from "node:crypto";
import type { GraphJSON, RunEvent } from "@jigworks/contracts";

export interface BridgeOptions {
  /** Command that runs the runner CLI, e.g. ["uv", "run", "jigworks"]. */
  command: string[];
  /** Working directory for the runner (the workspace / target repo). */
  cwd: string;
  /** Runner state directory; default is the runner's own (<repo>/.jigworks). */
  home?: string;
  env?: NodeJS.ProcessEnv;
}

export interface StartOptions {
  runId?: string;
  workflowDir: string;
  repoPath: string;
  prompt: string;
  title?: string;
  adapter?: "claude" | "fake";
  fakeScript?: string;
  extraArgs?: string[];
}

export interface RunRow {
  runId: string;
  release: string;
  status: string;
  node: string | null;
  progress: number;
  title: string | null;
  worktree: string;
  busy: boolean;
}

interface Session {
  events: RunEvent[];
  proc?: ChildProcess;
  stderr: string;
}

export class RunnerBridge extends EventEmitter {
  private sessions = new Map<string, Session>();

  constructor(private readonly opts: BridgeOptions) {
    super();
  }

  /** Extra environment for every runner process started from now on (e.g. hub URL and key). */
  setEnv(extra: Record<string, string | undefined>): void {
    this.opts.env = { ...this.opts.env, ...extra };
  }

  static newRunId(): string {
    const ts = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
    return `run_${ts}_${randomBytes(3).toString("hex")}`;
  }

  runIds(): string[] {
    return [...this.sessions.keys()].sort();
  }

  events(runId: string): RunEvent[] {
    return this.sessions.get(runId)?.events ?? [];
  }

  snapshot(): Record<string, RunEvent[]> {
    return Object.fromEntries([...this.sessions].map(([id, s]) => [id, s.events]));
  }

  isRunning(runId: string): boolean {
    return Boolean(this.sessions.get(runId)?.proc);
  }

  running(): string[] {
    return [...this.sessions].filter(([, s]) => s.proc).map(([id]) => id);
  }

  private homeArgs(): string[] {
    return this.opts.home ? ["--home", this.opts.home] : [];
  }

  private session(runId: string): Session {
    let s = this.sessions.get(runId);
    if (!s) {
      s = { events: [], stderr: "" };
      this.sessions.set(runId, s);
    }
    return s;
  }

  private accept(runId: string, event: RunEvent): void {
    const s = this.session(runId);
    const last = s.events.length ? (s.events[s.events.length - 1].seq ?? -1) : -1;
    if ((event.seq ?? last + 1) <= last) return; // duplicate (replayed log)
    s.events.push(event);
    this.emit("event", runId, event);
  }

  /** Spawn a runner command that drives `runId`; resolves when the process exits. */
  private drive(runId: string, args: string[]): Promise<number> {
    const s = this.session(runId);
    if (s.proc) return Promise.reject(new Error(`a runner process is already working on ${runId}`));
    const [cmd, ...base] = this.opts.command;
    const proc = spawn(cmd, [...base, ...args], {
      cwd: this.opts.cwd,
      env: { ...process.env, ...this.opts.env },
      stdio: ["ignore", "pipe", "pipe"],
    });
    s.proc = proc;
    s.stderr = "";
    this.emit("change", runId);
    let buf = "";
    proc.stdout!.setEncoding("utf8");
    proc.stdout!.on("data", (chunk: string) => {
      buf += chunk;
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line) continue;
        try {
          this.accept(runId, JSON.parse(line) as RunEvent);
        } catch {
          // not an event line; the runner only prints events on stdout
        }
      }
    });
    proc.stderr!.setEncoding("utf8");
    proc.stderr!.on("data", (chunk: string) => {
      s.stderr = (s.stderr + chunk).slice(-8000);
    });
    return new Promise((resolve) => {
      proc.on("error", (err) => {
        s.stderr += `\n${err.message}`;
      });
      proc.on("close", (code) => {
        s.proc = undefined;
        this.emit("exit", runId, code ?? -1, s.stderr);
        this.emit("change", runId);
        resolve(code ?? -1);
      });
    });
  }

  /** Start a run; resolves with its runId as soon as the process is spawned. */
  start(o: StartOptions): { runId: string; done: Promise<number> } {
    const runId = o.runId ?? RunnerBridge.newRunId();
    const args = ["run", "--workflow", o.workflowDir, "--repo", o.repoPath, "--prompt", o.prompt, "--run-id", runId,
      ...this.homeArgs()];
    if (o.title) args.push("--title", o.title);
    if (o.adapter) args.push("--adapter", o.adapter);
    if (o.fakeScript) args.push("--fake-script", o.fakeScript);
    if (o.extraArgs) args.push(...o.extraArgs);
    return { runId, done: this.drive(runId, args) };
  }

  decide(runId: string, decision: "approve" | "request_changes" | "reject", comment?: string): Promise<number> {
    const verb = decision === "request_changes" ? "request-changes" : decision;
    const args = [verb, runId, ...this.homeArgs()];
    if (decision === "request_changes") args.push("--comment", comment ?? "");
    return this.drive(runId, args);
  }

  /** `moreFixes`: continue a run that failed at the fix loop limit (releases before 1.7.0). */
  resume(runId: string, opts: { moreFixes?: number; comment?: string } = {}): Promise<number> {
    const args = ["resume", runId, ...this.homeArgs()];
    if (opts.moreFixes) {
      args.push("--more-fixes", String(opts.moreFixes));
      if (opts.comment?.trim()) args.push("--comment", opts.comment.trim());
    }
    return this.drive(runId, args);
  }

  stop(runId: string): void {
    this.sessions.get(runId)?.proc?.kill("SIGTERM");
  }

  stderr(runId: string): string {
    return this.sessions.get(runId)?.stderr ?? "";
  }

  /** Run a read-only runner command and return its stdout. */
  async query(args: string[]): Promise<string> {
    const [cmd, ...base] = this.opts.command;
    return new Promise((resolve, reject) => {
      const proc = spawn(cmd, [...base, ...args], { cwd: this.opts.cwd, env: { ...process.env, ...this.opts.env } });
      let out = "";
      let err = "";
      proc.stdout.setEncoding("utf8").on("data", (c: string) => (out += c));
      proc.stderr.setEncoding("utf8").on("data", (c: string) => (err += c));
      proc.on("error", reject);
      proc.on("close", (code) => (code === 0 ? resolve(out) : reject(new Error(`jigworks ${args[0]} exited ${code}: ${err.trim()}`))));
    });
  }

  async list(): Promise<RunRow[]> {
    return JSON.parse(await this.query(["ls", "--json", ...this.homeArgs()])) as RunRow[];
  }

  async graph(workflowDir: string): Promise<GraphJSON> {
    return JSON.parse(await this.query(["graph", workflowDir])) as GraphJSON;
  }

  async inspect(workflowDir: string): Promise<Record<string, unknown>> {
    return JSON.parse(await this.query(["inspect", workflowDir])) as Record<string, unknown>;
  }

  /** Rebuild every known session from the runner's event logs (after a window reload). */
  async load(): Promise<string[]> {
    const rows = await this.list();
    for (const row of rows) {
      const out = await this.query(["events", row.runId, ...this.homeArgs()]);
      for (const line of out.split("\n")) {
        if (line.trim()) this.accept(row.runId, JSON.parse(line) as RunEvent);
      }
    }
    return rows.map((r) => r.runId);
  }

  dispose(): void {
    for (const s of this.sessions.values()) s.proc?.kill("SIGTERM");
  }
}
