import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import type { RunEvent } from "@jigworks/contracts";
import { installBundle, sidecarDigest } from "./bundles";
import { RunnerBridge } from "./runner/bridge";
import { checkClaude } from "./runner/preflight";
import { WorkflowRegistry } from "./workflows";
import type { HostState, Preflight, ToHost, ToWebview, ViewKind, WorkflowInfo } from "./shared/messages";
import { foldEvents } from "./shared/session";

export interface JigworksApi {
  bridge: RunnerBridge;
  registry: WorkflowRegistry;
  state(): HostState;
  preflight(): Promise<Preflight>;
  startSession(prompt: string, workflowKey?: string, attachments?: string[]): Promise<string | undefined>;
  openSession(runId: string): void;
  panels(): string[];
  /** runIds that raised an interrupt notification (tests). */
  notified(): string[];
  statusText(): string;
}

function config() {
  return vscode.workspace.getConfiguration("jigworks");
}

function workspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

class Host {
  readonly bridge: RunnerBridge;
  readonly registry: WorkflowRegistry;
  private views = new Set<vscode.Webview>();
  private sessionPanels = new Map<string, vscode.WebviewPanel>();
  private newPanel?: vscode.WebviewPanel;
  private status: vscode.StatusBarItem;
  selected?: string;
  preflightResult?: Preflight;
  /** Runs driven from this window; replayed history (load) never raises notifications. */
  readonly live = new Set<string>();
  readonly notified: string[] = [];

  constructor(private readonly ctx: vscode.ExtensionContext) {
    const root = workspaceRoot() ?? process.cwd();
    const command = config().get<string[]>("runnerCommand", ["uv", "run", "jigworks"]);
    const home = config().get<string>("home") || undefined;
    this.bridge = new RunnerBridge({
      command,
      cwd: root,
      home: home ? path.resolve(root, home) : undefined,
      env: { JIGWORKS_CLAUDE_BIN: config().get<string>("claudePath", "claude") },
    });
    this.registry = new WorkflowRegistry(this.bridge);
    this.status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
    this.status.command = "jigworks.newSession";
    ctx.subscriptions.push(this.status, { dispose: () => this.bridge.dispose() });

    this.bridge.on("event", (runId: string, event: RunEvent) => {
      this.post({ type: "event", runId, event });
      this.refreshChrome();
      if (event.kind === "interrupt" && this.live.has(runId)) void this.notifyInterrupt(runId, event);
    });
    this.bridge.on("change", () => this.broadcast());
    this.bridge.on("exit", (runId: string, code: number, stderr: string) => {
      if (code !== 0 && code !== null) {
        const tail = stderr.trim().split("\n").slice(-2).join(" ");
        void vscode.window.showWarningMessage(`Jigworks ${runId}: runner exited ${code}. ${tail}`);
      }
    });
  }

  private async notifyInterrupt(runId: string, event: RunEvent): Promise<void> {
    const s = foldEvents(runId, this.bridge.events(runId));
    const what = event.interrupt?.stage === "plan" ? "plan approval" : "review before the PR";
    this.notified.push(runId);
    const choice = await vscode.window.showInformationMessage(`Jigworks: "${s.title}" needs your ${what}.`, "Open");
    if (choice === "Open") this.openSession(runId);
  }

  home(): string {
    const root = workspaceRoot() ?? process.cwd();
    const configured = config().get<string>("home");
    return configured ? path.resolve(root, configured) : path.join(root, ".jigworks");
  }

  cacheDir(): string {
    return path.join(this.ctx.globalStorageUri.fsPath, "workflows");
  }

  async init(): Promise<void> {
    const roots = (vscode.workspace.workspaceFolders ?? []).map((f) => f.uri.fsPath);
    await Promise.allSettled([this.registry.scanWorkspace(roots), this.registry.scanCache(this.cacheDir())]);
    this.selected = this.selected ?? this.registry.list()[0]?.key;
    try {
      await this.bridge.load();
    } catch {
      // no runs yet or the runner is not installed; the preflight / start will say so
    }
    void this.preflight();
    this.broadcast();
  }

  async preflight(): Promise<Preflight> {
    if (config().get<string>("adapter", "claude") === "fake") {
      this.preflightResult = { ok: true, authMethod: "fake adapter" };
    } else {
      this.preflightResult = await checkClaude(config().get<string>("claudePath", "claude"));
    }
    this.broadcast();
    return this.preflightResult;
  }

  state(): HostState {
    return {
      workflows: this.registry.list(),
      selectedWorkflow: this.selected,
      sessions: this.bridge.snapshot(),
      running: this.bridge.running(),
      preflight: this.preflightResult,
      repoLabel: config().get<string>("repoPath", "sample-repo"),
    };
  }

  private post(msg: ToWebview): void {
    for (const v of this.views) void v.postMessage(msg);
  }

  broadcast(): void {
    this.post({ type: "state", state: this.state() });
    this.refreshChrome();
  }

  private refreshChrome(): void {
    const views = Object.entries(this.bridge.snapshot()).map(([id, ev]) => foldEvents(id, ev));
    const running = views.filter((s) => s.status === "running").length;
    const waiting = views.filter((s) => s.status === "waiting_human").length;
    this.status.text = `$(rocket) Jigworks: ${running} running · ${waiting} waiting for you`;
    this.status.show();
    for (const [runId, panel] of this.sessionPanels) {
      const s = views.find((v) => v.runId === runId);
      if (s) panel.title = `${s.title.slice(0, 28)} · ${s.status === "waiting_human" ? "Review" : `${Math.round(s.progress)} %`}`;
    }
  }

  html(webview: vscode.Webview, view: ViewKind, runId?: string): string {
    const out = vscode.Uri.joinPath(this.ctx.extensionUri, "out");
    const script = webview.asWebviewUri(vscode.Uri.joinPath(out, "webview.js"));
    const style = webview.asWebviewUri(vscode.Uri.joinPath(out, "webview.css"));
    const nonce = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
    const boot = JSON.stringify({ view, runId: runId ?? null });
    return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}'; img-src ${webview.cspSource} data:;">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="${style}"></head>
<body><div id="root"></div><script nonce="${nonce}">window.__JIGWORKS_BOOT__=${boot};</script><script nonce="${nonce}" src="${script}"></script></body></html>`;
  }

  attach(webview: vscode.Webview, view: ViewKind, runId?: string): vscode.Disposable {
    webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(this.ctx.extensionUri, "out")] };
    webview.html = this.html(webview, view, runId);
    this.views.add(webview);
    const sub = webview.onDidReceiveMessage((m: ToHost) => void this.onMessage(m));
    return { dispose: () => { this.views.delete(webview); sub.dispose(); } };
  }

  async onMessage(m: ToHost): Promise<void> {
    switch (m.type) {
      case "ready":
        this.broadcast();
        break;
      case "selectWorkflow":
        this.selected = m.key;
        this.broadcast();
        break;
      case "newSession":
        this.openNew();
        break;
      case "openSession":
        this.openSession(m.runId);
        break;
      case "start": {
        const runId = await this.startSession(m.prompt, m.workflowKey, m.attachments);
        if (runId) this.openSession(runId);
        break;
      }
      case "attach": {
        const root = workspaceRoot();
        const picked = await vscode.window.showOpenDialog({
          canSelectMany: true,
          defaultUri: root ? vscode.Uri.file(root) : undefined,
          openLabel: "Attach",
        });
        const paths = (picked ?? []).map((u) => (root ? path.relative(root, u.fsPath) : u.fsPath));
        this.post({ type: "attached", paths });
        break;
      }
      case "openAudit": {
        const file = path.join(this.home(), "runs", m.runId, "audit.jsonl");
        await vscode.window.showTextDocument(vscode.Uri.file(file), { preview: true });
        break;
      }
      case "decide":
        this.live.add(m.runId);
        await this.bridge.decide(m.runId, m.decision, m.comment);
        break;
      case "resume":
        this.live.add(m.runId);
        await this.bridge.resume(m.runId);
        break;
      case "stop":
        this.bridge.stop(m.runId);
        break;
      case "openDiff":
        await vscode.commands.executeCommand("jigworks.openWorktree", m.runId);
        break;
      case "importWorkflow":
        await vscode.commands.executeCommand("jigworks.importWorkflow");
        break;
      case "sync":
        await vscode.commands.executeCommand("jigworks.syncWorkflows");
        break;
    }
  }

  async startSession(prompt: string, workflowKey?: string, attachments: string[] = []): Promise<string | undefined> {
    const wf = this.registry.get(workflowKey ?? this.selected ?? "");
    if (!wf) {
      void vscode.window.showErrorMessage("Jigworks: pick a workflow first.");
      return undefined;
    }
    const pre = await this.preflight();
    if (!pre.ok) {
      void vscode.window.showErrorMessage(`Jigworks: ${pre.message}`);
      return undefined;
    }
    const root = workspaceRoot() ?? process.cwd();
    const adapter = config().get<"claude" | "fake">("adapter", "claude");
    const fakeScript = config().get<string>("fakeScript") || undefined;
    // Attachments are workspace paths; the agent reads them from its worktree (same tree).
    const fullPrompt = attachments.length
      ? `${prompt}\n\nAttached files (read them first): ${attachments.join(", ")}`
      : prompt;
    const runId = RunnerBridge.newRunId();
    this.live.add(runId);
    this.bridge.start({
      runId,
      title: prompt.split("\n")[0].slice(0, 200),
      workflowDir: wf.path,
      repoPath: path.resolve(root, config().get<string>("repoPath", "sample-repo")),
      prompt: fullPrompt,
      adapter,
      fakeScript: fakeScript ? path.resolve(root, fakeScript) : undefined,
      extraArgs: config().get<string[]>("runArgs", []),
    });
    return runId;
  }

  openNew(): void {
    if (this.newPanel) {
      this.newPanel.reveal();
      return;
    }
    const panel = vscode.window.createWebviewPanel("jigworks.new", "New session", vscode.ViewColumn.One, {
      enableScripts: true,
      retainContextWhenHidden: true,
    });
    const d = this.attach(panel.webview, "new");
    panel.onDidDispose(() => { d.dispose(); this.newPanel = undefined; });
    this.newPanel = panel;
  }

  openSession(runId: string): void {
    const existing = this.sessionPanels.get(runId);
    if (existing) {
      existing.reveal();
      return;
    }
    const panel = vscode.window.createWebviewPanel("jigworks.session", runId, vscode.ViewColumn.One, {
      enableScripts: true,
      retainContextWhenHidden: true,
    });
    const d = this.attach(panel.webview, "session", runId);
    panel.onDidDispose(() => { d.dispose(); this.sessionPanels.delete(runId); });
    this.sessionPanels.set(runId, panel);
    this.refreshChrome();
  }

  panels(): string[] {
    return [...this.sessionPanels.keys()];
  }

  statusText(): string {
    return this.status.text;
  }

  /** "Import workflow from file" (design.md §6 fallback): the same .zip the hub serves. */
  async importZip(zipPath?: string, digest?: string): Promise<WorkflowInfo | undefined> {
    let file = zipPath;
    if (!file) {
      const picked = await vscode.window.showOpenDialog({ filters: { "Workflow bundle": ["zip"] }, openLabel: "Import" });
      file = picked?.[0]?.fsPath;
      if (!file) return undefined;
    }
    let expected = digest ?? sidecarDigest(file);
    if (!expected) {
      expected = await vscode.window.showInputBox({
        prompt: "Digest of the release (sha256:…), as shown in the hub",
        validateInput: (v) => (/^sha256:[0-9a-f]{64}$/.test(v.trim()) ? undefined : "expected sha256: followed by 64 hex digits"),
      });
      if (!expected) return undefined;
    }
    try {
      const out = await installBundle(this.bridge, this.cacheDir(), fs.readFileSync(file), expected, {
        source: "imported",
        fileName: path.basename(file),
      });
      const wf = await this.registry.add(out.path, "imported", undefined, out.digest);
      this.selected = wf.key;
      this.broadcast();
      void vscode.window.showInformationMessage(`Jigworks: imported ${wf.release} (${wf.digest.slice(0, 19)}…).`);
      return wf;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      void vscode.window.showErrorMessage(`Jigworks: import refused. ${msg}`);
      throw err;
    }
  }
}

class SidebarProvider implements vscode.WebviewViewProvider {
  constructor(private readonly host: Host) {}
  resolveWebviewView(view: vscode.WebviewView): void {
    const d = this.host.attach(view.webview, "sidebar");
    view.onDidDispose(() => d.dispose());
  }
}

export async function activate(context: vscode.ExtensionContext): Promise<JigworksApi> {
  const host = new Host(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("jigworks.sidebar", new SidebarProvider(host), {
      webviewOptions: { retainContextWhenHidden: true },
    }),
    vscode.commands.registerCommand("jigworks.newSession", () => host.openNew()),
    vscode.commands.registerCommand("jigworks.openSession", (runId: string) => host.openSession(runId)),
    vscode.commands.registerCommand("jigworks.approve", (runId: string) => host.onMessage({ type: "decide", runId, decision: "approve" })),
    vscode.commands.registerCommand("jigworks.reject", (runId: string) => host.onMessage({ type: "decide", runId, decision: "reject" })),
    vscode.commands.registerCommand("jigworks.requestChanges", async (runId: string, comment?: string) => {
      const text = comment ?? (await vscode.window.showInputBox({ prompt: "What should the agent change?" }));
      if (text) return host.onMessage({ type: "decide", runId, decision: "request_changes", comment: text });
      return undefined;
    }),
    vscode.commands.registerCommand("jigworks.resume", (runId: string) => host.onMessage({ type: "resume", runId })),
    vscode.commands.registerCommand("jigworks.refresh", () => host.init()),
    vscode.commands.registerCommand("jigworks.importWorkflow", (zipPath?: string, digest?: string) => host.importZip(zipPath, digest)),
    vscode.commands.registerCommand("jigworks.preflight", () => host.preflight()),
    vscode.commands.registerCommand("jigworks.openWorktree", async (runId: string) => {
      const rows = await host.bridge.list();
      const row = rows.find((r) => r.runId === runId);
      if (row) await vscode.commands.executeCommand("vscode.openFolder", vscode.Uri.file(row.worktree), { forceNewWindow: true });
    }),
  );
  await host.init();

  return {
    bridge: host.bridge,
    registry: host.registry,
    state: () => host.state(),
    preflight: () => host.preflight(),
    startSession: (prompt, key, attachments) => host.startSession(prompt, key, attachments),
    openSession: (runId) => host.openSession(runId),
    panels: () => host.panels(),
    notified: () => [...host.notified],
    statusText: () => host.statusText(),
  };
}

export function deactivate(): void {}
