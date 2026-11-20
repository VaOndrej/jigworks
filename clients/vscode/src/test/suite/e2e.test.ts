// Integration (pnpm verify:e2e): the real hub API publishes feature-development, the extension syncs
// `stable`, runs it with the fake adapter through the real runner (real gate on sample-repo), and the
// runner streams the events to the hub. Skipped unless verify:e2e passes JIGWORKS_E2E_HUB_URL.
import * as assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import type { RunEvent } from "@jigworks/contracts";
import type { JigworksApi } from "../../extension";
import { foldEvents } from "../../shared/session";

const hubUrl = process.env.JIGWORKS_E2E_HUB_URL;
const hubKey = process.env.JIGWORKS_E2E_HUB_KEY;
const workspace = process.env.JIGWORKS_TEST_WORKSPACE!;

const NOTES = 'def describe(order):\n    return f"{order.side.value} {order.quantity} {order.instrument}"\n';
const SCRIPT = {
  plan: [{ text: "1. Add describe(order) in sample-repo/sample_repo/notes.py.\n2. Test it." }],
  write_tests: [{ text: "added tests", files: { "sample-repo/tests/test_notes.py": "from sample_repo.notes import describe\n\n\ndef test_describe_exists():\n    assert callable(describe)\n" } }],
  implement: [{ text: "implemented describe", files: { "sample-repo/sample_repo/notes.py": NOTES } }],
  review: [{ text: "- describe() has no docstring\nVERDICT: FAIL" }, { text: "VERDICT: PASS" }],
  fix: [{ text: "added the docstring", files: { "sample-repo/sample_repo/notes.py": `"""Order descriptions."""\n\n${NOTES}` } }],
  summary: [{ text: "describe(order) added after one review fix loop." }],
};

async function api(): Promise<JigworksApi> {
  const ext = vscode.extensions.getExtension<JigworksApi>("jigworks.vscode")!;
  return ext.isActive ? ext.exports : await ext.activate();
}

function waitFor(a: JigworksApi, runId: string, pred: (e: RunEvent[]) => boolean, ms = 150000): Promise<RunEvent[]> {
  return new Promise((resolve, reject) => {
    const end = Date.now() + ms;
    const tick = () => {
      const events = a.bridge.events(runId);
      if (pred(events)) return resolve(events);
      if (Date.now() > end) return reject(new Error(`timeout; stderr: ${a.bridge.stderr(runId)}`));
      setTimeout(tick, 200);
    };
    tick();
  });
}

suite("e2e: hub → extension → runner → hub", function () {
  const cfg = () => vscode.workspace.getConfiguration("jigworks");

  suiteSetup(async function () {
    if (!hubUrl || !hubKey) this.skip();
    const remote = path.join(workspace, ".jigworks-e2e-remote.git");
    execFileSync("git", ["init", "-q", "--bare", remote]);
    fs.writeFileSync(path.join(workspace, "e2e-script.json"), JSON.stringify(SCRIPT));
    await cfg().update("hubUrl", hubUrl, vscode.ConfigurationTarget.Workspace);
    await cfg().update("repoPath", "sample-repo", vscode.ConfigurationTarget.Workspace);
    await cfg().update("fakeScript", "e2e-script.json", vscode.ConfigurationTarget.Workspace);
    await cfg().update("runArgs", ["--pr-remote", remote], vscode.ConfigurationTarget.Workspace);
  });

  test("publish → sync stable → run → events in the hub", async () => {
    const a = await api();
    await vscode.commands.executeCommand("jigworks.setHubPassword", hubKey);
    await vscode.commands.executeCommand("jigworks.syncWorkflows");
    const wf = a.state().workflows.find((w) => w.source === "hub" && w.name === "feature-development");
    assert.ok(wf, "feature-development synced from the hub");
    assert.equal(wf.channel, "stable");

    const runId = (await a.startSession("Add describe(order) (verify:e2e)", wf.key))!;
    const idle = (status: string) => (e: RunEvent[]) => foldEvents(runId, e).status === status && !a.bridge.isRunning(runId);
    await waitFor(a, runId, idle("waiting_human"));
    await vscode.commands.executeCommand("jigworks.approve", runId); // plan
    await waitFor(a, runId, idle("waiting_human"));
    await vscode.commands.executeCommand("jigworks.approve", runId); // PR
    const events = await waitFor(a, runId, idle("succeeded"));
    const s = foldEvents(runId, events);
    assert.equal(s.release, wf.release);
    assert.equal(s.digest, wf.digest, "the run is pinned to the synced release digest");
    assert.equal(s.fixLoops, 1);

    const res = await fetch(`${hubUrl}/api/runs/${runId}`, { headers: { "X-Jigworks-Key": hubKey! } });
    assert.equal(res.status, 200);
    const onHub = (await res.json()) as { summary: { status: string; fixLoops?: number; digest: string } };
    assert.equal(onHub.summary.status, "succeeded");
    assert.equal(onHub.summary.digest, wf.digest);
    assert.equal(onHub.summary.fixLoops, 1);
    if (process.env.JIGWORKS_E2E_OUT) {
      fs.writeFileSync(process.env.JIGWORKS_E2E_OUT, JSON.stringify({ runId, release: s.release, digest: s.digest, events: events.length }));
    }
  });
});
