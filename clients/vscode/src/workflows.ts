// Known workflow packages: the workspace's own `workflows/*/` (development), packages imported
// from a .zip (T10) and releases synced from the hub (T15). Metadata comes from the runner
// (`jigworks inspect`), so the extension never parses workflow.toml itself.
import * as fs from "node:fs";
import * as path from "node:path";
import type { GraphJSON, WorkflowManifest } from "@jigworks/contracts";
import type { RunnerBridge } from "./runner/bridge";
import type { WorkflowInfo } from "./shared/messages";

interface Inspected {
  path: string;
  release: string;
  digest: string;
  manifest: WorkflowManifest;
  graph: GraphJSON;
}

export class WorkflowRegistry {
  private items = new Map<string, WorkflowInfo>();

  constructor(private readonly bridge: RunnerBridge) {}

  list(): WorkflowInfo[] {
    const order = { hub: 0, imported: 1, workspace: 2 } as const;
    return [...this.items.values()].sort((a, b) => order[a.source] - order[b.source] || a.name.localeCompare(b.name));
  }

  get(key: string): WorkflowInfo | undefined {
    return this.items.get(key);
  }

  async add(dir: string, source: WorkflowInfo["source"], channel?: string, digest?: string): Promise<WorkflowInfo> {
    const info = (await this.bridge.inspect(dir)) as unknown as Inspected;
    const m = info.manifest;
    const item: WorkflowInfo = {
      key: `${source}:${m.name}@${m.version}`,
      name: m.name,
      version: m.version,
      release: info.release,
      // For a synced or imported bundle the verified bundle digest is the identity of the release.
      digest: digest ?? info.digest,
      path: info.path,
      source,
      channel,
      description: m.description,
      plannedPath: m.plannedPath ?? [],
      interruptNodes: m.interruptNodes ?? [],
      models: m.models,
      allowedTools: m.permissions?.allowedTools ?? [],
      network: m.permissions?.network,
      graph: info.graph,
    };
    this.items.set(item.key, item);
    return item;
  }

  /** `workflows/*` of every workspace folder that holds a workflow.toml. */
  async scanWorkspace(roots: string[]): Promise<void> {
    for (const root of roots) {
      const dir = path.join(root, "workflows");
      if (!fs.existsSync(dir)) continue;
      for (const name of fs.readdirSync(dir)) {
        const pkg = path.join(dir, name);
        if (fs.existsSync(path.join(pkg, "workflow.toml"))) {
          try {
            await this.add(pkg, "workspace");
          } catch {
            // a broken package in the workspace must not stop the extension
          }
        }
      }
    }
  }

  /** Packages unpacked into the extension's cache: <cache>/<name>@<version>/ with jigworks-source.json. */
  async scanCache(cacheDir: string): Promise<void> {
    if (!fs.existsSync(cacheDir)) return;
    for (const name of fs.readdirSync(cacheDir)) {
      const dir = path.join(cacheDir, name);
      const metaFile = path.join(dir, "jigworks-source.json");
      if (!fs.existsSync(metaFile)) continue;
      const meta = JSON.parse(fs.readFileSync(metaFile, "utf8")) as { source: WorkflowInfo["source"]; channel?: string; digest: string };
      try {
        await this.add(path.join(dir, "package"), meta.source, meta.channel, meta.digest);
      } catch {
        // skip broken cache entries
      }
    }
  }
}
