// Draft file operations. The API replaces the whole file list on save, so every operation is a
// pure function from files to files (unit-tested in files.test.ts).
import type { DraftFile } from "@jigworks/contracts";

export const KEEP = ".gitkeep";
export const NAME_RE = /^[A-Za-z0-9_.-]+$/;

export type TreeEntry = { type: "file" | "folder"; path: string; name: string; depth: number };

export function tree(files: DraftFile[]): TreeEntry[] {
  const folders = new Set<string>();
  for (const f of files) {
    const parts = f.path.split("/");
    for (let i = 1; i < parts.length; i++) folders.add(parts.slice(0, i).join("/"));
  }
  const entries: TreeEntry[] = [];
  const walk = (prefix: string, depth: number) => {
    const childFolders = [...folders].filter((d) => parent(d) === prefix).sort();
    const childFiles = files
      .filter((f) => parent(f.path) === prefix && basename(f.path) !== KEEP)
      .map((f) => f.path)
      .sort();
    // Mockup order: files of a folder first, then its sub-folders.
    for (const p of childFiles) entries.push({ type: "file", path: p, name: basename(p), depth });
    for (const d of childFolders) {
      entries.push({ type: "folder", path: d, name: `${basename(d)}/`, depth });
      walk(d, depth + 1);
    }
  };
  walk("", 0);
  return entries;
}

export const parent = (p: string) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
export const basename = (p: string) => p.slice(p.lastIndexOf("/") + 1);
export const join = (dir: string, name: string) => (dir ? `${dir}/${name}` : name);

export const TEMPLATES = {
  node: (name: string) =>
    `def ${name.replace(/\.py$/, "").replace(/[^A-Za-z0-9_]/g, "_")}(state):\n    """Node function: reads the graph state, returns the keys it updates."""\n    return {}\n`,
  prompt: (name: string) => `# ${name.replace(/\.md$/, "")}\n\nDescribe what the agent should do in this step.\n`,
  empty: () => "",
} as const;
export type TemplateName = keyof typeof TEMPLATES;

export function exists(files: DraftFile[], path: string): boolean {
  return files.some((f) => f.path === path || f.path.startsWith(`${path}/`));
}

export function addFile(files: DraftFile[], dir: string, name: string, template: TemplateName): DraftFile[] {
  const path = join(dir, name);
  if (!NAME_RE.test(name) || exists(files, path)) throw new Error(`cannot create ${path}`);
  const keep = join(dir, KEEP);
  return [...files.filter((f) => f.path !== keep), { path, content: TEMPLATES[template](name) }];
}

export function addFolder(files: DraftFile[], dir: string, name: string): DraftFile[] {
  const path = join(dir, name);
  if (!NAME_RE.test(name) || exists(files, path)) throw new Error(`cannot create ${path}/`);
  return [...files, { path: join(path, KEEP), content: "" }];
}

export function rename(files: DraftFile[], from: string, toName: string): DraftFile[] {
  const to = join(parent(from), toName);
  if (!NAME_RE.test(toName) || (to !== from && exists(files, to))) throw new Error(`cannot rename to ${to}`);
  return files.map((f) =>
    f.path === from ? { ...f, path: to } : f.path.startsWith(`${from}/`) ? { ...f, path: to + f.path.slice(from.length) } : f,
  );
}

export function remove(files: DraftFile[], path: string): DraftFile[] {
  const left = files.filter((f) => f.path !== path && !f.path.startsWith(`${path}/`));
  const dir = parent(path);
  // Keep the parent folder visible when its last file goes.
  if (dir && !left.some((f) => f.path.startsWith(`${dir}/`))) left.push({ path: join(dir, KEEP), content: "" });
  return left;
}
