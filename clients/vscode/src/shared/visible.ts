import type { WorkflowInfo } from "./messages";

/**
 * The workflow list as the sidebar shows it. A workspace package (`workflows/*` in the open
 * folder) that is byte-identical to a published one (same digest) is the same release and is
 * listed once, as the published one. A workspace package whose name is published with a
 * different digest is marked `changed`: local edits not in the hub yet.
 */
export function visibleWorkflows(all: WorkflowInfo[]): WorkflowInfo[] {
  const published = all.filter((w) => w.source !== "workspace");
  return all.flatMap((w) => {
    if (w.source !== "workspace") return [w];
    if (published.some((p) => p.digest === w.digest)) return [];
    return [published.some((p) => p.name === w.name) ? { ...w, changed: true } : w];
  });
}

/** The selected key, moved to the published twin when the selected workspace copy is hidden. */
export function visibleSelection(all: WorkflowInfo[], visible: WorkflowInfo[], selected?: string): string | undefined {
  if (!selected || visible.some((w) => w.key === selected)) return selected;
  const hidden = all.find((w) => w.key === selected);
  return (hidden && visible.find((w) => w.digest === hidden.digest)?.key) ?? visible[0]?.key;
}
