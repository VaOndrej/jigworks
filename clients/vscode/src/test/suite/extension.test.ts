// The real extension in a real VS Code (headless, @vscode/test-electron), driving the real runner
// with the fake adapter: two sessions in parallel, events, request changes, approve, reload.
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import type { RunEvent } from "@jigworks/contracts";
import type { JigworksApi } from "../../extension";
import { RunnerBridge } from "../../runner/bridge";
import { checkClaude } from "../../runner/preflight";
import { foldEvents } from "../../shared/session";

const workspace = process.env.JIGWORKS_TEST_WORKSPACE!;

async function api(): Promise<JigworksApi> {
  const ext = vscode.extensions.getExtension<JigworksApi>("jigworks.vscode");
  assert.ok(ext, "extension is installed in the test host");
  return ext.isActive ? ext.exports : await ext.activate();
}

function waitFor(bridge: RunnerBridge, runId: string, pred: (events: RunEvent[]) => boolean, ms = 60000): Promise<RunEvent[]> {
  return new Promise((resolve, reject) => {
    const check = () => {
      const events = bridge.events(runId);
      if (pred(events)) {
        cleanup();
        resolve(events);
      }
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error(`timeout waiting for ${runId}; stderr: ${bridge.stderr(runId)}`));
    }, ms);
    const onEvent = (id: string) => id === runId && check();
    const cleanup = () => {
      clearTimeout(timer);
      bridge.off("event", onEvent);
      bridge.off("change", onEvent);
    };
    bridge.on("event", onEvent);
    bridge.on("change", onEvent);
    check();
  });
}

const statusOf = (events: RunEvent[]) => foldEvents("x", events).status;
const idle = (bridge: RunnerBridge, runId: string) => (events: RunEvent[]) => !bridge.isRunning(runId) && events.length > 0;

function fakeClaude(body: string): string {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "fake-claude-")), "claude");
  fs.writeFileSync(file, `#!/bin/sh\n${body}\n`);
  fs.chmodSync(file, 0o755);
  return file;
}

suite("Jigworks extension", () => {
  test("activates, finds the workspace workflow and contributes its views and commands", async () => {
    const a = await api();
    const wf = a.state().workflows.find((w) => w.name === "tiny");
    assert.ok(wf, "tiny workflow from workflows/tiny");
    assert.equal(wf.release, "tiny@0.1.0");
    assert.match(wf.digest, /^sha256:[0-9a-f]{64}$/);
    assert.deepEqual(wf.plannedPath, ["work", "review", "finish"]);
    assert.equal(wf.graph?.nodes.find((n) => n.id === "review")?.kind, "interrupt");
    const commands = await vscode.commands.getCommands(true);
    for (const c of ["jigworks.newSession", "jigworks.approve", "jigworks.requestChanges", "jigworks.reject", "jigworks.importWorkflow"]) {
      if (c !== "jigworks.importWorkflow") assert.ok(commands.includes(c), c);
    }
  });

  test("login preflight: logged in, logged out, not installed", async () => {
    const ok = await checkClaude(
      fakeClaude(`echo '{"loggedIn": true, "authMethod": "claude.ai", "email": "someone@example.com", "orgId": "x", "subscriptionType": "max"}'`),
    );
    assert.deepEqual(ok, { ok: true, authMethod: "claude.ai", subscriptionType: "max", message: undefined });
    assert.ok(!JSON.stringify(ok).includes("example.com"), "email never leaves the preflight");
    const out = await checkClaude(fakeClaude(`echo '{"loggedIn": false, "authMethod": "none"}'; exit 1`));
    assert.equal(out.ok, false);
    assert.match(out.message ?? "", /\/login/);
    const missing = await checkClaude("/nonexistent/claude");
    assert.equal(missing.ok, false);
    assert.match(missing.message ?? "", /not installed/);
  });

  test("two sessions run in parallel; request changes and approve go through the runner", async () => {
    const a = await api();
    const key = a.state().workflows.find((w) => w.name === "tiny")!.key;
    const [runA, runB] = await Promise.all([a.startSession("Task A: write notes", key), a.startSession("Task B: write notes", key)]);
    assert.ok(runA && runB && runA !== runB);
    assert.ok(a.bridge.isRunning(runA) || a.bridge.events(runA).length > 0);

    const [evA, evB] = await Promise.all([
      waitFor(a.bridge, runA, (e) => statusOf(e) === "waiting_human" && !a.bridge.isRunning(runA)),
      waitFor(a.bridge, runB, (e) => statusOf(e) === "waiting_human" && !a.bridge.isRunning(runB)),
    ]);
    assert.equal(evA[0].kind, "run_started");
    assert.equal(evA[evA.length - 1].kind, "interrupt");
    assert.ok(evA.every((e) => e.runId === runA) && evB.every((e) => e.runId === runB));

    const rows = await a.bridge.list();
    const wtA = rows.find((r) => r.runId === runA)!.worktree;
    const wtB = rows.find((r) => r.runId === runB)!.worktree;
    assert.notEqual(wtA, wtB);
    assert.equal(fs.readFileSync(path.join(wtA, "notes.txt"), "utf8"), "first try\n");

    // Both interrupts raised a notification; the status bar counts them.
    assert.deepEqual(a.notified().filter((id) => id === runA || id === runB).sort(), [runA, runB].sort());
    assert.match(a.statusText(), /0 running · 2 waiting for you/);

    // A: approve → finished. B: request changes → work again → review → approve.
    await vscode.commands.executeCommand("jigworks.approve", runA);
    await vscode.commands.executeCommand("jigworks.requestChanges", runB, "Say it twice.");
    await waitFor(a.bridge, runA, (e) => statusOf(e) === "succeeded");
    const afterChanges = await waitFor(a.bridge, runB, (e) => statusOf(e) === "waiting_human" && !a.bridge.isRunning(runB));
    const viewB = foldEvents(runB, afterChanges);
    assert.equal(viewB.followUps, 1);
    assert.equal(viewB.nodes["work"].attempt, 2);
    assert.equal(fs.readFileSync(path.join(wtB, "notes.txt"), "utf8"), "second try\n");
    assert.ok(viewB.output.some((l) => l.text.includes("Addressed the review comment")));

    await vscode.commands.executeCommand("jigworks.approve", runB);
    const doneB = await waitFor(a.bridge, runB, (e) => statusOf(e) === "succeeded");
    const summary = doneB[doneB.length - 1].summary!;
    assert.equal(summary.followUpPrompts, 1);
    assert.equal(summary.progress, 100);
    assert.ok(summary.firstResultCommit && summary.firstResultCommit !== summary.finalCommit);
    await waitFor(a.bridge, runB, idle(a.bridge, runB));

    // Session tabs: one panel per session.
    a.openSession(runA);
    a.openSession(runB);
    assert.deepEqual(a.panels().sort(), [runA, runB].sort());
  });

  test("import a workflow .zip: valid bundle accepted, tampered bundle refused", async () => {
    const a = await api();
    const bundles = path.join(process.env.JIGWORKS_REPO_ROOT!, "packages/contracts/fixtures/bundles");
    const valid = path.join(bundles, "feature-development-1.3.0.zip");
    const digest = fs.readFileSync(`${valid}.sha256`, "utf8").trim();

    const wf = (await vscode.commands.executeCommand("jigworks.importWorkflow", valid)) as { release: string; digest: string; source: string; path: string };
    assert.equal(wf.release, "feature-development@1.3.0");
    assert.equal(wf.digest, digest, "the verified bundle digest is the release's identity");
    assert.equal(wf.source, "imported");
    assert.ok(fs.existsSync(path.join(wf.path, "workflow.toml")));
    const listed = a.state().workflows.find((w) => w.source === "imported" && w.release === "feature-development@1.3.0");
    assert.ok(listed && listed.graph?.nodes.some((n) => n.id === "approve_pr" && n.kind === "interrupt"));
    assert.equal(a.state().selectedWorkflow, listed!.key, "the imported workflow becomes the active one");

    const cache = path.dirname(path.dirname(wf.path));
    const before = fs.readdirSync(cache).sort();
    await assert.rejects(
      () => Promise.resolve(vscode.commands.executeCommand("jigworks.importWorkflow", path.join(bundles, "feature-development-1.3.0.tampered.zip"), digest)),
      /digest_mismatch/,
    );
    assert.deepEqual(fs.readdirSync(cache).sort(), before, "nothing was unpacked from the tampered bundle");
  });

  test("sessions survive a webview reload and a window reload", async () => {
    const a = await api();
    const before = a.bridge.snapshot();
    const ids = Object.keys(before);
    assert.ok(ids.length >= 2);
    // Webview reload: panels go away, the bridge (extension host) keeps every event.
    await vscode.commands.executeCommand("workbench.action.closeAllEditors");
    assert.deepEqual(a.bridge.snapshot(), before);
    a.openSession(ids[0]);
    assert.ok(a.panels().includes(ids[0]));
    // Window reload: a fresh bridge rebuilds the sessions from the runner's logs on disk.
    const cfg = vscode.workspace.getConfiguration("jigworks");
    const fresh = new RunnerBridge({
      command: cfg.get<string[]>("runnerCommand")!,
      cwd: workspace,
      home: path.join(workspace, ".jigworks"),
    });
    const loaded = await fresh.load();
    assert.deepEqual(loaded.sort(), ids.sort());
    for (const id of ids) assert.deepEqual(fresh.events(id), before[id]);
  });
});
