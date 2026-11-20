// Bundles the extension host code and the React webview with esbuild.
//   node build.mjs               extension (out/extension.js) + webview (out/webview.js, out/webview.css)
//   node build.mjs --production  the same, minified (for the .vsix)
//   node build.mjs --standalone  the webview + a standalone page that replays the recorded runs
//                                (out/standalone/index.html) for the Playwright screenshots
// esbuild-wasm, not esbuild: no install script, so `pnpm install` on Vercel (pnpm 12 refuses
// unapproved build scripts) keeps working for the whole workspace.
import * as esbuild from "esbuild-wasm";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const prod = process.argv.includes("--production");
const standalone = process.argv.includes("--standalone");
const out = path.join(here, "out");

const common = { bundle: true, sourcemap: !prod, minify: prod, logLevel: "warning" };

await esbuild.build({
  ...common,
  entryPoints: [path.join(here, "src/extension.ts")],
  outfile: path.join(out, "extension.js"),
  platform: "node",
  format: "cjs",
  target: "node20",
  external: ["vscode"],
});

await esbuild.build({
  ...common,
  entryPoints: { webview: path.join(here, "webview/main.tsx") },
  outdir: out,
  platform: "browser",
  format: "iife",
  target: "es2022",
  jsx: "automatic",
  loader: { ".json": "json" },
  define: { "process.env.NODE_ENV": JSON.stringify(prod ? "production" : "development") },
});

if (standalone) {
  const dir = path.join(out, "standalone");
  fs.mkdirSync(dir, { recursive: true });
  await esbuild.build({
    ...common,
    entryPoints: { standalone: path.join(here, "webview/standalone.tsx") },
    outdir: dir,
    platform: "browser",
    format: "iife",
    target: "es2022",
    jsx: "automatic",
    loader: { ".json": "json", ".jsonl": "text" },
    define: { "process.env.NODE_ENV": '"production"' },
  });
  fs.copyFileSync(path.join(here, "webview/standalone.html"), path.join(dir, "index.html"));
}
