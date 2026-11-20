// Standalone webview screenshots at 1440 px (AGENTS.md: desktop only). Run with
// `pnpm --filter vscode test:ui`, which builds clients/vscode/out/standalone first.
import { defineConfig } from "@playwright/test";
import * as path from "node:path";

export default defineConfig({
  testDir: path.join(__dirname),
  testMatch: /.*\.ui\.spec\.ts/,
  outputDir: path.join(__dirname, "test-results"),
  reporter: [["list"]],
  use: {
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "dark",
  },
});
