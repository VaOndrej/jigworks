import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { runTests } from "@vscode/test-electron";

/** A throwaway workspace: a git repo with the tiny workflow, settings that point the extension at
 *  the repo's runner (fake adapter, no tokens) and a separate runner home. */
function makeWorkspace(repoRoot: string): string {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "jigworks-vscode-"));
  const fixtures = path.join(repoRoot, "clients/vscode/test-fixtures");
  fs.cpSync(path.join(fixtures, "tiny-workflow"), path.join(ws, "workflows/tiny"), { recursive: true });
  fs.copyFileSync(path.join(fixtures, "fake-script.json"), path.join(ws, "fake-script.json"));
  fs.writeFileSync(path.join(ws, "README.md"), "test workspace\n");
  fs.writeFileSync(path.join(ws, ".gitignore"), ".jigworks/\n__pycache__/\n");
  fs.mkdirSync(path.join(ws, ".vscode"));
  const python = path.join(repoRoot, ".venv/bin/python");
  fs.writeFileSync(
    path.join(ws, ".vscode/settings.json"),
    JSON.stringify(
      {
        "jigworks.runnerCommand": [python, "-m", "jigworks_runner.cli"],
        "jigworks.repoPath": ".",
        "jigworks.adapter": "fake",
        "jigworks.fakeScript": "fake-script.json",
        "jigworks.home": ".jigworks",
      },
      null,
      2,
    ),
  );
  const git = (...args: string[]) => execFileSync("git", args, { cwd: ws, stdio: "ignore" });
  git("init", "-q", "-b", "main");
  git("config", "user.email", "dev@example.com");
  git("config", "user.name", "Dev");
  git("add", "-A");
  git("commit", "-q", "-m", "base");
  return ws;
}

async function main(): Promise<void> {
  // When tests are started from a terminal inside VS Code (or Claude Code in VS Code),
  // ELECTRON_RUN_AS_NODE=1 is inherited and the test VS Code would start as plain Node
  // ("bad option: --extensionTestsPath"). The test instance must run as Electron.
  delete process.env.ELECTRON_RUN_AS_NODE;
  const extensionDevelopmentPath = path.resolve(__dirname, "../../");
  const extensionTestsPath = path.resolve(__dirname, "./suite/index");
  const repoRoot = path.resolve(__dirname, "../../../../");
  const workspace = makeWorkspace(repoRoot);
  // One VS Code download (~375 MB) shared by all worktrees instead of one per checkout.
  const cachePath =
    process.env.JIGWORKS_VSCODE_TEST_CACHE ?? path.join(os.homedir(), ".cache", "jigworks-vscode-test");
  try {
    await runTests({
      cachePath,
      extensionDevelopmentPath,
      extensionTestsPath,
      launchArgs: [workspace, "--disable-extensions"],
      extensionTestsEnv: { JIGWORKS_TEST_WORKSPACE: workspace, JIGWORKS_REPO_ROOT: repoRoot },
    });
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error("Failed to run tests", err);
  process.exit(1);
});
