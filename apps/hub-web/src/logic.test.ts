import { describe, expect, it } from "vitest";
import type { AuditRecord, GraphJSON, WorkflowManifest } from "@jigworks/contracts";
import graph from "../../../packages/contracts/fixtures/graph/feature-development-1.3.0.graph.json";
import detail from "../../../packages/contracts/fixtures/api/run-detail.json";
import releases from "../../../packages/contracts/fixtures/api/release-list.json";
import { addFile, addFolder, remove, rename, tree } from "./files";
import { layout, mainColumn } from "./graphLayout";
import { timeline } from "./timeline";
import { bumpMinor, duration, shape, shapeLabel, tomlVersion } from "./format";

const files = [
  { path: "graph.py", content: "" },
  { path: "steps/nodes.py", content: "" },
  { path: "prompts/plan.md", content: "" },
];

describe("draft file operations", () => {
  it("lists files then folders, depth first", () => {
    expect(tree(files).map((e) => e.path)).toEqual(["graph.py", "prompts", "prompts/plan.md", "steps", "steps/nodes.py"]);
  });
  it("creates from a template, creates folders, renames folders, deletes", () => {
    let f = addFile(files, "steps", "scan.py", "node");
    expect(f.find((x) => x.path === "steps/scan.py")?.content).toContain("def scan(state):");
    f = addFolder(f, "", "checks");
    expect(tree(f).some((e) => e.type === "folder" && e.path === "checks")).toBe(true);
    f = rename(f, "steps", "nodes");
    expect(f.map((x) => x.path)).toContain("nodes/scan.py");
    f = remove(f, "nodes");
    expect(f.some((x) => x.path.startsWith("nodes/"))).toBe(false);
    expect(() => addFile(files, "", "graph.py", "empty")).toThrow();
    expect(() => addFile(files, "", "../x.py", "empty")).toThrow();
  });
  it("keeps an emptied folder visible", () => {
    const f = remove(files, "prompts/plan.md");
    expect(tree(f).map((e) => e.path)).toContain("prompts");
  });
});

describe("graph layout", () => {
  const g = graph as GraphJSON;
  const planned = releases.releases[0].manifest.plannedPath;
  it("puts the planned path in one column and fix to the side", () => {
    expect(mainColumn(g, planned)).toEqual(["__start__", ...planned, "__end__"]);
    const { nodes, edges } = layout(g, planned);
    expect(nodes.find((n) => n.id === "fix")?.column).toBe("side");
    expect(edges.find((e) => e.source === "review" && e.target === "fix")?.tone).toBe("fail");
    expect(edges.find((e) => e.source === "review" && e.target === "gate")?.tone).toBe("pass");
  });
  it("falls back to a topological order without a planned path", () => {
    const col = mainColumn(g);
    expect(col[0]).toBe("__start__");
    expect(col[col.length - 1]).toBe("__end__");
    expect(col.indexOf("plan")).toBeLessThan(col.indexOf("summary"));
  });
});

describe("audit timeline", () => {
  it("compresses run_fd_0002 into readable lines", () => {
    const lines = timeline(detail.audit as AuditRecord).map((l) => l.parts.map((p) => p.v).join(""));
    expect(lines[0]).toBe("Started by bob · feature-development@1.3.0 · claude-sonnet-5");
    expect(lines).toContain("Plan approved by bob");
    expect(lines.some((l) => l.startsWith("review FAIL"))).toBe(true);
    expect(lines.some((l) => l.includes('requested changes: "Use Decimal instead of float for amounts."'))).toBe(true);
    expect(lines.some((l) => l.startsWith("PR approved by bob"))).toBe(true);
  });
});

describe("format", () => {
  it("describes the step shape of a release", () => {
    const s = shape(releases.releases[0].manifest as WorkflowManifest);
    expect(s.map((x) => x.kind)).toEqual(["agent", "review", "agent", "agent", "agent", "gate", "review", "agent", "agent"]);
    expect(shapeLabel(s)).toBe("9 steps · 2 reviews · gate");
  });
  it("reads and bumps versions", () => {
    expect(tomlVersion('name = "x"\nversion = "1.3.0"\n')).toBe("1.3.0");
    expect(bumpMinor("1.3.0")).toBe("1.4.0");
    expect(duration(2460)).toBe("41 min");
  });
});
