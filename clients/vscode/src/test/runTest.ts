import * as path from "node:path";
import { runTests } from "@vscode/test-electron";

async function main(): Promise<void> {
  // When tests are started from a terminal inside VS Code (or Claude Code in VS Code),
  // ELECTRON_RUN_AS_NODE=1 is inherited and the test VS Code would start as plain Node
  // ("bad option: --extensionTestsPath"). The test instance must run as Electron.
  delete process.env.ELECTRON_RUN_AS_NODE;
  const extensionDevelopmentPath = path.resolve(__dirname, "../../");
  const extensionTestsPath = path.resolve(__dirname, "./suite/index");
  await runTests({
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: ["--disable-extensions"],
  });
}

main().catch((err) => {
  console.error("Failed to run tests", err);
  process.exit(1);
});
