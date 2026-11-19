// Release bundles in the extension: import from a .zip (T10) and, later, sync from the hub (T15).
// The digest is checked here first (a clear error before anything runs) and again by the runner's
// `jigworks unpack`, which uses the frozen contract's read_bundle (digest + unsafe paths) and writes
// nothing unless both pass.
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type { RunnerBridge } from "./runner/bridge";

export class DigestMismatch extends Error {
  constructor(readonly expected: string, readonly actual: string) {
    super(`digest_mismatch: expected ${expected}, got ${actual}`);
  }
}

export function sha256Digest(data: Buffer): string {
  return `sha256:${createHash("sha256").update(data).digest("hex")}`;
}

export function sidecarDigest(zipPath: string): string | undefined {
  const sidecar = `${zipPath}.sha256`;
  return fs.existsSync(sidecar) ? fs.readFileSync(sidecar, "utf8").trim() : undefined;
}

export interface Unpacked {
  path: string;
  release: string;
  digest: string;
  source: "imported" | "hub";
  channel?: string;
}

/** Verify `data` against `expected` and unpack it into `<cacheDir>/<digest prefix>/`. */
export async function installBundle(
  bridge: RunnerBridge,
  cacheDir: string,
  data: Buffer,
  expected: string,
  opts: { source: "imported" | "hub"; channel?: string; fileName: string },
): Promise<Unpacked> {
  const actual = sha256Digest(data);
  if (actual !== expected.trim()) throw new DigestMismatch(expected.trim(), actual);
  fs.mkdirSync(cacheDir, { recursive: true });
  const dest = path.join(cacheDir, expected.replace("sha256:", "").slice(0, 16));
  const zipPath = path.join(cacheDir, `.${opts.fileName}`);
  fs.writeFileSync(zipPath, data);
  try {
    const args = ["unpack", zipPath, "--digest", expected.trim(), "--dest", dest, "--source", opts.source];
    if (opts.channel) args.push("--channel", opts.channel);
    const out = JSON.parse(await bridge.query(args)) as Unpacked;
    return { ...out, source: opts.source };
  } finally {
    fs.rmSync(zipPath, { force: true });
  }
}
