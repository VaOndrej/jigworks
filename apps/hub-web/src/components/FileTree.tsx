import { useState, type FormEvent } from "react";
import type { DraftFile } from "@jigworks/contracts";
import { addFile, addFolder, parent, remove, rename, tree, type TemplateName } from "../files";

type Mode = { kind: "file" | "folder"; dir: string } | { kind: "rename"; path: string } | null;

export function FileTree({ files, selected, onSelect, onChange }: {
  files: DraftFile[];
  selected: string;
  onSelect: (path: string) => void;
  onChange: (files: DraftFile[], select?: string) => void;
}) {
  const [mode, setMode] = useState<Mode>(null);
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<TemplateName>("node");
  const [error, setError] = useState<string>();
  const entries = tree(files);
  // New items go into the folder of the selected file (or the selected folder).
  const targetDir = entries.find((e) => e.path === selected)?.type === "folder" ? selected : parent(selected);

  function open(next: Mode) {
    setMode(next);
    setError(undefined);
    setName(next?.kind === "rename" ? next.path.slice(next.path.lastIndexOf("/") + 1) : "");
    if (next?.kind === "file") setTemplate(next.dir.startsWith("prompts") ? "prompt" : "node");
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!mode) return;
    try {
      if (mode.kind === "file") {
        const fname = template === "node" && !name.includes(".") ? `${name}.py` : template === "prompt" && !name.includes(".") ? `${name}.md` : name;
        onChange(addFile(files, mode.dir, fname, template), mode.dir ? `${mode.dir}/${fname}` : fname);
      } else if (mode.kind === "folder") {
        onChange(addFolder(files, mode.dir, name));
      } else if (mode.kind === "rename") {
        const next = rename(files, mode.path, name);
        const dir = parent(mode.path);
        onChange(next, selected === mode.path ? (dir ? `${dir}/${name}` : name) : undefined);
      }
      setMode(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const form = (label: string) => (
    <form className="tree-form" onSubmit={submit}>
      <label htmlFor="tree-name">{label}</label>
      <input id="tree-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      {mode?.kind === "file" && (
        <select aria-label="Template" value={template} onChange={(e) => setTemplate(e.target.value as TemplateName)}>
          <option value="node">Template: node function</option>
          <option value="prompt">Template: prompt</option>
          <option value="empty">Empty file</option>
        </select>
      )}
      {error && <span className="tree-error">{error}</span>}
      <div className="tree-form-actions">
        <button type="submit" className="btn btn-xs btn-dark" disabled={!name}>
          {mode?.kind === "rename" ? "Rename" : "Create"}
        </button>
        <button type="button" className="btn btn-xs" onClick={() => setMode(null)}>
          Cancel
        </button>
      </div>
    </form>
  );

  return (
    <nav className="files" aria-label="Files">
      <div className="files-head">
        <span>Package</span>
        <span className="files-actions">
          <button type="button" className="icon-btn" aria-label="New file" title="New file" onClick={() => open({ kind: "file", dir: targetDir })}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3F424A" strokeWidth="1.8" aria-hidden="true">
              <path d="M6 3h8l4 4v14H6z" />
              <path d="M12 11v6M9 14h6" />
            </svg>
          </button>
          <button type="button" className="icon-btn" aria-label="New folder" title="New folder" onClick={() => open({ kind: "folder", dir: targetDir })}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3F424A" strokeWidth="1.8" aria-hidden="true">
              <path d="M3 6h6l2 2h10v11H3z" />
              <path d="M12 11v5M9.5 13.5h5" />
            </svg>
          </button>
        </span>
      </div>
      {mode && mode.kind !== "rename" && mode.dir === "" && form(`New ${mode.kind}`)}
      {entries.map((e) => (
        <div key={`${e.type}:${e.path}`}>
          <div
            className={`tree-item ${e.type} ${selected === e.path ? "active" : ""}`}
            style={{ paddingLeft: 8 + e.depth * 16 }}
            onClick={() => onSelect(e.path)}
            onDoubleClick={() => open({ kind: "rename", path: e.path })}
          >
            <button type="button" className="tree-name" aria-current={selected === e.path ? "true" : undefined}>
              {e.name}
            </button>
            <span className="tree-tools">
              <button type="button" aria-label={`Rename ${e.path}`} title="Rename" onClick={(ev) => { ev.stopPropagation(); open({ kind: "rename", path: e.path }); }}>
                ✎
              </button>
              <button
                type="button"
                aria-label={`Delete ${e.path}`}
                title="Delete"
                onClick={(ev) => {
                  ev.stopPropagation();
                  if (window.confirm(`Delete ${e.path}${e.type === "folder" ? " and everything in it" : ""}?`)) onChange(remove(files, e.path));
                }}
              >
                ×
              </button>
            </span>
          </div>
          {mode?.kind === "rename" && mode.path === e.path && form(`Rename ${e.name}`)}
          {mode && mode.kind !== "rename" && e.type === "folder" && mode.dir === e.path && form(`New ${mode.kind} in ${e.path}/`)}
        </div>
      ))}
    </nav>
  );
}
