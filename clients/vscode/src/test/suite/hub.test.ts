// T15: the extension syncs `stable` from the hub, runs the pinned release, and follows a rollback.
// The hub is the runner's contract-validating fake hub, started as a process.
import * as assert from "node:assert/strict";
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import * as fs from "node:fs";
import * as http from "node:http";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import type { RunEvent } from "@jigworks/contracts";
import type { JigworksApi } from "../../extension";
import { HubClient } from "../../hub";
import { foldEvents } from "../../shared/session";

const repoRoot = process.env.JIGWORKS_REPO_ROOT!;
const workspace = process.env.JIGWORKS_TEST_WORKSPACE!;
const python = path.join(repoRoot, ".venv/bin/python");
const KEY = "good-key";

async function api(): Promise<JigworksApi> {
  const ext = vscode.extensions.getExtension<JigworksApi>("jigworks.vscode")!;
  return ext.isActive ? ext.exports : await ext.activate();
}

function startFakeHub(): Promise<{ url: string; proc: ChildProcess }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(python, ["-m", "jigworks_runner.testing.fakehub", "--key", KEY], { stdio: ["ignore", "pipe", "inherit"] });
    proc.stdout!.setEncoding("utf8").once("data", (line: string) => resolve({ url: JSON.parse(line).url as string, proc }));
    proc.on("error", reject);
  });
}

/** Build the release zip of the tiny workflow at `version` with the runner (`jigworks bundle`). */
function bundle(version: string): { zip: string; digest: string } {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `tiny-${version}-`));
  fs.cpSync(path.join(workspace, "workflows/tiny"), path.join(dir, "tiny"), { recursive: true, filter: (p) => !p.includes("__pycache__") });
  const toml = path.join(dir, "tiny/workflow.toml");
  fs.writeFileSync(toml, fs.readFileSync(toml, "utf8").replace(/^version = ".*"$/m, `version = "${version}"`));
  const zip = path.join(dir, `tiny-${version}.zip`);
  const out = JSON.parse(execFileSync(python, ["-m", "jigworks_runner.cli", "bundle", path.join(dir, "tiny"), "--out", zip], { encoding: "utf8" }));
  return { zip, digest: out.digest };
}

async function publish(hubUrl: string, version: string, zip: string): Promise<string> {
  const res = await fetch(`${hubUrl}/_test/release?workflowId=tiny&version=${version}&channel=stable`, {
    method: "POST",
    body: fs.readFileSync(zip),
    headers: { "content-type": "application/zip" },
  });
  return ((await res.json()) as { releaseId: string }).releaseId;
}

function localTiny(a: JigworksApi) {
  return a.state().workflows.filter((w) => w.source === "workspace" && w.name === "tiny");
}

async function until(pred: () => boolean, ms = 10000): Promise<void> {
  const end = Date.now() + ms;
  while (!pred()) {
    if (Date.now() > end) throw new Error("timeout");
    await new Promise((r) => setTimeout(r, 100));
  }
}

function hubTiny(a: JigworksApi) {
  return a.state().workflows.filter((w) => w.source === "hub" && w.name === "tiny");
}

function waitFor(a: JigworksApi, runId: string, pred: (e: RunEvent[]) => boolean, ms = 60000): Promise<RunEvent[]> {
  return new Promise((resolve, reject) => {
    const end = Date.now() + ms;
    const tick = () => {
      const events = a.bridge.events(runId);
      if (pred(events)) return resolve(events);
      if (Date.now() > end) return reject(new Error(`timeout; stderr: ${a.bridge.stderr(runId)}`));
      setTimeout(tick, 100);
    };
    tick();
  });
}

suite("Jigworks hub sync (T15)", () => {
  let hub: { url: string; proc: ChildProcess };

  suiteSetup(async () => {
    hub = await startFakeHub();
    await vscode.workspace.getConfiguration("jigworks").update("hubUrl", hub.url, vscode.ConfigurationTarget.Workspace);
  });

  suiteTeardown(async () => {
    hub?.proc.kill();
    await vscode.workspace.getConfiguration("jigworks").update("hubUrl", undefined, vscode.ConfigurationTarget.Workspace);
  });

  test("the password lives in secret storage; a wrong one is a clear error", async () => {
    await vscode.commands.executeCommand("jigworks.setHubPassword", "wrong-password");
    const settings = fs.readFileSync(path.join(workspace, ".vscode/settings.json"), "utf8");
    assert.ok(!settings.includes("wrong-password"), "never written to settings.json");
    await assert.rejects(
      () => Promise.resolve(vscode.commands.executeCommand("jigworks.syncWorkflows")),
      /hub refused the password.*Set hub password/,
    );
    const status = (await api()).state().hub!;
    assert.equal(status.state, "error", "the sidebar shows the failed sync");
    assert.match(status.message ?? "", /refused the password/);
  });

  test("a hub behind Vercel Deployment Protection is named as such, not a JSON parse error", async () => {
    const sso = http.createServer((_req, res) => {
      res.writeHead(302, { location: "https://vercel.com/sso-api?url=x" }).end();
    });
    await new Promise<void>((r) => sso.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${(sso.address() as { port: number }).port}`;
    try {
      await assert.rejects(() => new HubClient(url, KEY).workflows(), /behind Vercel Deployment Protection/);
    } finally {
      sso.close();
    }
  });

  test("publish v1 → run → publish v2 → roll stable back to v1 → the extension picks up v1", async () => {
    const a = await api();
    await vscode.commands.executeCommand("jigworks.setHubPassword", KEY);
    const v1 = bundle("0.1.0");
    const v2 = bundle("0.2.0");
    assert.notEqual(v1.digest, v2.digest);

    // publish v1 to stable → sync → run it
    const v1Id = await publish(hub.url, "0.1.0", v1.zip);
    await vscode.commands.executeCommand("jigworks.syncWorkflows");
    assert.deepEqual(hubTiny(a).map((w) => [w.version, w.digest, w.channel]), [["0.1.0", v1.digest, "stable"]]);
    assert.deepEqual(
      (({ url, hasPassword, state }) => ({ url, hasPassword, state }))(a.state().hub!),
      { url: hub.url, hasPassword: true, state: "connected" },
    );
    // the workspace copy is the same package as the hub's release → listed once
    assert.deepEqual(localTiny(a), [], "workspace tiny with the hub's digest is hidden");
    const runId = (await a.startSession("Task on the pinned release", hubTiny(a)[0].key))!;
    const events = await waitFor(a, runId, (e) => foldEvents(runId, e).status === "waiting_human" && !a.bridge.isRunning(runId));
    const started = events[0].runStarted!;
    assert.equal(started.release, "tiny@0.1.0");
    assert.equal(started.digest, foldEvents(runId, events).digest);
    // the run's events reached the hub too (the runner got the hub URL and key from the extension)
    const onHub = (await (await fetch(`${hub.url}/_test/events`, { method: "POST" })).json()) as Record<string, number[]>;
    assert.ok((onHub[runId] ?? []).length >= events.length - 1, `hub has ${onHub[runId]?.length} of ${events.length}`);

    // publish v2 → stable moves → sync picks v2
    await publish(hub.url, "0.2.0", v2.zip);
    await vscode.commands.executeCommand("jigworks.syncWorkflows");
    assert.deepEqual(hubTiny(a).map((w) => [w.version, w.digest]), [["0.2.0", v2.digest]]);
    assert.deepEqual(localTiny(a).map((w) => [w.version, w.changed]), [["0.1.0", true]], "differs from the hub → local (changed)");

    // roll the channel back to v1 (hub API, with the key) → sync picks v1 again
    const put = await fetch(`${hub.url}/api/workflows/tiny/channels/stable`, {
      method: "PUT",
      headers: { "content-type": "application/json", "X-Jigworks-Key": KEY },
      body: JSON.stringify({ releaseId: v1Id }),
    });
    assert.equal(put.status, 200);
    await vscode.commands.executeCommand("jigworks.syncWorkflows");
    assert.deepEqual(hubTiny(a).map((w) => [w.version, w.digest]), [["0.1.0", v1.digest]]);

    assert.deepEqual(localTiny(a), []);

    // editing the workspace package shows it again as changed, without a reload; undoing hides it
    const graphPy = path.join(workspace, "workflows/tiny/graph.py");
    const original = fs.readFileSync(graphPy, "utf8");
    fs.writeFileSync(graphPy, original + "\n# local edit\n");
    try {
      await until(() => localTiny(a)[0]?.changed === true);
    } finally {
      fs.writeFileSync(graphPy, original);
    }
    await until(() => localTiny(a).length === 0);

    // the running session never changed version (design.md §6: a running task stays pinned)
    assert.equal(foldEvents(runId, a.bridge.events(runId)).release, "tiny@0.1.0");
    await vscode.commands.executeCommand("jigworks.reject", runId);

    // the hub is emptied (sample data removed) → the next sync drops the hub workflow from the sidebar
    await fetch(`${hub.url}/_test/reset`, { method: "POST" });
    await vscode.commands.executeCommand("jigworks.syncWorkflows");
    assert.deepEqual(hubTiny(a), [], "a workflow the hub no longer offers on stable is not left behind");
    assert.ok(a.state().workflows.every((w) => w.source !== "hub"));
  });
});
