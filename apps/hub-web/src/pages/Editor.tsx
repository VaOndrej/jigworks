import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { parse as parseToml } from "smol-toml";
import type { ChannelName, DraftFile, Release, RunDetail, ValidationResult, WorkflowManifest } from "@jigworks/contracts";
import { api, ApiError } from "../api";
import { useLoad } from "../data";
import { bumpMinor, tomlVersion, usd } from "../format";
import { Link, navigate } from "../router";
import { CodeEditor } from "../components/CodeEditor";
import { FileTree } from "../components/FileTree";
import { GraphView, type NodeState } from "../components/GraphView";
import { ErrorNote, Pill, Planned } from "../ui";

type SaveState = "saved" | "dirty" | "saving" | "error";

export function EditorPage({ workflowId, view }: { workflowId: string; view: "code" | "graph" }) {
  const [files, setFiles] = useState<DraftFile[]>();
  const [loadError, setLoadError] = useState<Error>();
  const [selected, setSelected] = useState("graph.py");
  const [save, setSave] = useState<SaveState>("saved");
  const [baseReleaseId, setBaseReleaseId] = useState<string>();
  const [validation, setValidation] = useState<ValidationResult>();
  const [validating, setValidating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const releases = useLoad(() => api.releases(workflowId), [workflowId]);
  const timer = useRef<number>(undefined);
  const pending = useRef<DraftFile[] | null>(null);

  useEffect(() => {
    api
      .draft(workflowId)
      .then((d) => {
        setFiles(d.files);
        setBaseReleaseId(d.baseReleaseId);
        if (!d.files.some((f) => f.path === "graph.py")) setSelected(d.files[0]?.path ?? "");
      })
      .catch(setLoadError);
  }, [workflowId]);

  const flush = useCallback(async () => {
    window.clearTimeout(timer.current);
    const next = pending.current;
    if (!next) return;
    pending.current = null;
    setSave("saving");
    try {
      await api.saveDraft(workflowId, next);
      setSave(pending.current ? "dirty" : "saved");
    } catch (e) {
      setSave("error");
      throw e;
    }
  }, [workflowId]);

  const update = useCallback(
    (next: DraftFile[], select?: string) => {
      setFiles(next);
      setValidation(undefined);
      if (select) setSelected(select);
      else
        setSelected((cur) =>
          next.some((f) => f.path === cur || f.path.startsWith(`${cur}/`))
            ? cur
            : (next.find((f) => f.path === "graph.py")?.path ?? next[0]?.path ?? ""),
        );
      pending.current = next;
      setSave("dirty");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void flush().catch(() => {}), 700);
    },
    [flush],
  );

  const validate = useCallback(async () => {
    setValidating(true);
    try {
      await flush();
      setValidation(await api.validate(workflowId));
    } catch (e) {
      setValidation({ ok: false, checks: [{ name: "imports", ok: false, message: (e as Error).message }] });
    } finally {
      setValidating(false);
    }
  }, [flush, workflowId]);

  // Switching to Graph compiles the draft in Vercel Sandbox (cached per draft content on the hub).
  useEffect(() => {
    if (view === "graph" && files && !validation && !validating) void validate();
  }, [view, files, validation, validating, validate]);

  const toml = files?.find((f) => f.path === "workflow.toml")?.content;
  const manifest = useMemo(() => {
    try {
      return toml ? (parseToml(toml) as unknown as WorkflowManifest) : undefined;
    } catch {
      return undefined;
    }
  }, [toml]);
  const version = tomlVersion(toml);
  const base = releases.data?.releases.find((r) => r.id === baseReleaseId);

  if (loadError) {
    return (
      <main className="page">
        <ErrorNote error={loadError} />
        <Link to="/">Back to workflows</Link>
      </main>
    );
  }
  const current = files?.find((f) => f.path === selected);

  return (
    <main className="page page-editor">
      <div className="editor-head">
        <div className="grow min0">
          <div className="crumbs">
            <Link to="/">Workflows</Link> / {workflowId}
          </div>
          <h1 className="h1 h1-sm">
            Draft {version ?? "?"}{" "}
            <span className="sub">
              {base ? `based on ${base.channels?.length ? `${base.channels[0]} ` : ""}${base.version}` : "not published yet"}
            </span>
          </h1>
        </div>
        <span className={`save-state save-${save}`} aria-live="polite">
          {save === "saved" ? "Saved" : save === "saving" ? "Saving…" : save === "dirty" ? "Unsaved changes" : "Save failed"}
        </span>
        <div role="tablist" aria-label="View" className="segmented">
          <Link to={`/workflows/${workflowId}`} role="tab" aria-selected={view === "code"}>
            Code
          </Link>
          <Link to={`/workflows/${workflowId}/graph`} role="tab" aria-selected={view === "graph"}>
            Graph
          </Link>
        </div>
        {view === "code" ? (
          <button type="button" className="btn" onClick={() => void validate()} disabled={validating || !files}>
            {validating ? "Validating…" : "Validate"}
          </button>
        ) : (
          <OverlaySelect workflowId={workflowId} />
        )}
        <button type="button" className="btn btn-dark" onClick={() => setPublishing(true)} disabled={!files}>
          Publish…
        </button>
      </div>

      {view === "code" ? (
        <>
          <div className="source-bar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3F424A" strokeWidth="1.8" aria-hidden="true">
              <circle cx="6" cy="6" r="2.5" />
              <circle cx="6" cy="18" r="2.5" />
              <circle cx="18" cy="8" r="2.5" />
              <path d="M6 8.5v7M18 10.5c0 4-5 3.5-10 6" />
            </svg>
            <span>
              <b>Source:</b> stored in the hub
            </span>
            <span className="muted">
              Connect a GitHub repo and this editor becomes a view on it: a push to the repo updates the draft, a save here
              commits to the repo.
            </span>
            <button type="button" className="btn btn-sm push-right" disabled title="Planned, not built in the prototype">
              Connect GitHub repo
            </button>
            <Planned title="Planned: GitHub source is designed, not built" />
          </div>

          <div className="editor-grid">
            {files ? (
              <FileTree files={files} selected={selected} onSelect={setSelected} onChange={update} />
            ) : (
              <nav className="files" aria-busy="true" />
            )}
            <section className="code-panel" aria-label={selected}>
              <div className="code-bar">
                <span>{selected || "no file"}</span>
                <span>{selected.endsWith(".py") ? "Python · LangGraph 1.x" : selected.endsWith(".md") ? "Markdown prompt" : selected.endsWith(".toml") ? "TOML" : ""}</span>
              </div>
              {current ? (
                <CodeEditor
                  key={selected}
                  path={selected}
                  value={current.content}
                  onChange={(v) => update(files!.map((f) => (f.path === selected ? { ...f, content: v } : f)))}
                />
              ) : (
                <div className="code-empty">Select a file, or create one with the buttons above the file list.</div>
              )}
            </section>
            <aside className="editor-aside">
              <ValidationPanel result={validation} busy={validating} />
              <section className="card">
                <h2 className="h3">workflow.toml</h2>
                <ModelsSummary manifest={manifest} />
                <button type="button" className="btn btn-sm btn-block" onClick={() => setSelected("workflow.toml")}>
                  Edit workflow.toml
                </button>
              </section>
              <ReleasesPanel workflowId={workflowId} releases={releases.data?.releases} onChanged={releases.reload} />
            </aside>
          </div>
        </>
      ) : (
        <GraphPanel
          workflowId={workflowId}
          validation={validation}
          validating={validating}
          manifest={manifest}
          files={files ?? []}
          onOpen={(p) => {
            setSelected(p);
            navigate(`/workflows/${workflowId}`);
          }}
        />
      )}

      {publishing && files && (
        <PublishDialog
          workflowId={workflowId}
          version={version}
          suggested={base ? bumpMinor(base.version) : "0.1.0"}
          flush={flush}
          onClose={() => setPublishing(false)}
          onPublished={(r) => {
            setBaseReleaseId(r.id);
            releases.reload();
          }}
        />
      )}
    </main>
  );
}

function ValidationPanel({ result, busy }: { result?: ValidationResult; busy: boolean }) {
  const labels: Record<string, string> = {
    manifest: "workflow.toml",
    syntax: "Syntax",
    imports: "Imports (uv lock)",
    compile: "compile() + get_graph()",
    graph: "Graph",
  };
  return (
    <section className="card" aria-label="Validation">
      <h2 className="h3">Validation · Vercel Sandbox</h2>
      {busy && <p className="muted small">Compiling the draft in Vercel Sandbox…</p>}
      {!busy && !result && <p className="muted small">Not validated since the last change. Validate, or switch to Graph.</p>}
      {!busy && result && (
        <div className="checks">
          {result.checks.map((c) => (
            <div key={c.name} className="check">
              <div className="check-row">
                <span>{labels[c.name] ?? c.name}</span>
                <span className={c.ok ? "ok" : "bad"}>
                  {c.ok ? (c.name === "graph" && c.message ? c.message : "OK") : "FAIL"}
                </span>
              </div>
              {!c.ok && c.message && (
                <div className="check-msg">
                  {c.file ? `${c.file}${c.line ? `:${c.line}` : ""} · ` : ""}
                  {c.message}
                </div>
              )}
              {c.ok && c.message?.startsWith("mocked") && <div className="check-msg muted">{c.message}</div>}
            </div>
          ))}
          {result.durationMs !== undefined && <div className="muted xsmall">{(result.durationMs / 1000).toFixed(1)} s</div>}
        </div>
      )}
      <div className="muted xsmall">Code runs only in the sandbox, never in the Hub API process.</div>
    </section>
  );
}

function ModelsSummary({ manifest }: { manifest?: WorkflowManifest }) {
  if (!manifest) return <p className="muted small">workflow.toml does not parse.</p>;
  const nodes = Object.entries(manifest.models?.nodes ?? {});
  return (
    <pre className="toml-pre">
      <span className="toml-c"># [models] chosen here, not in VS Code</span>
      {"\n"}default = "{manifest.models?.default}"
      {nodes.map(([n, m]) => `\n${n} = "${m}"`).join("")}
      {manifest.permissions?.allowedTools && (
        <>
          {"\n\n"}
          <span className="toml-c"># [permissions]</span>
          {`\nallowedTools = ${JSON.stringify(manifest.permissions.allowedTools)}`}
          {`\nnetwork = ${manifest.permissions.network ?? false}`}
        </>
      )}
    </pre>
  );
}

function ReleasesPanel({ workflowId, releases, onChanged }: { workflowId: string; releases?: Release[]; onChanged: () => void }) {
  const [error, setError] = useState<string>();
  const stable = releases?.find((r) => r.channels?.includes("stable"));
  async function point(channel: ChannelName, r: Release) {
    try {
      await api.pointChannel(workflowId, channel, r.id);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="card" aria-label="Releases">
      <h2 className="h3">Releases</h2>
      {!releases?.length && <p className="muted small">Nothing published yet.</p>}
      {releases?.slice(0, 5).map((r) => (
        <div key={r.id} className="rel-line">
          <span className="mono">{r.version}</span>
          <span className="pills">
            {r.channels?.map((c) => (
              <Pill key={c} tone={c === "stable" ? "green" : "orange"}>
                {c}
              </Pill>
            ))}
          </span>
          {!r.channels?.includes("stable") && (
            <button type="button" className="btn btn-xs push-right" onClick={() => void point("stable", r)}>
              {stable && stable.publishedAt > r.publishedAt ? "Roll back stable" : "Promote to stable"}
            </button>
          )}
        </div>
      ))}
      {error && <div className="error-note">{error}</div>}
    </section>
  );
}

function OverlaySelect({ workflowId }: { workflowId: string }) {
  const runs = useLoad(() => api.runs({ workflowId, limit: 20 }), [workflowId]);
  const value = new URLSearchParams(window.location.search).get("overlay") ?? "";
  const live = (runs.data?.runs ?? []).filter((r) => ["running", "waiting_human", "paused_usage_limit"].includes(r.status));
  const options = live.length ? live : (runs.data?.runs ?? []).slice(0, 5);
  return (
    <>
      <label htmlFor="overlay" className="muted small">
        Overlay
      </label>
      <select
        id="overlay"
        className="select"
        value={value}
        onChange={(e) => navigate(`/workflows/${workflowId}/graph${e.target.value ? `?overlay=${e.target.value}` : ""}`)}
      >
        <option value="">none</option>
        {options.map((r) => (
          <option key={r.runId} value={r.runId}>
            {r.runId} · {r.status === "running" ? "live" : r.status.replace("_", " ")}
          </option>
        ))}
      </select>
    </>
  );
}

function overlayStates(detail: RunDetail | undefined): Record<string, NodeState> | undefined {
  if (!detail?.audit) return undefined;
  const out: Record<string, NodeState> = {};
  for (const s of detail.audit.steps) {
    const st: NodeState["status"] =
      s.status === "running" ? "running" : s.status === "waiting_human" ? "waiting" : s.status === "failed" ? "failed" : "done";
    out[s.node] = { status: st, attempt: s.attempt };
  }
  for (const d of detail.audit.decisions) {
    const node = d.stage === "plan" ? "approve_plan" : "approve_pr";
    if (d.decision === "approve" && out[node]?.status === "done") out[node] = { status: "approved" };
  }
  return out;
}

function GraphPanel({ workflowId, validation, validating, manifest, files, onOpen }: {
  workflowId: string;
  validation?: ValidationResult;
  validating: boolean;
  manifest?: WorkflowManifest;
  files: DraftFile[];
  onOpen: (path: string) => void;
}) {
  const overlay = new URLSearchParams(window.location.search).get("overlay");
  const detail = useLoad(() => (overlay ? api.run(overlay) : Promise.resolve(undefined)), [overlay]);
  const usage = useLoad(() => api.usage({ groupBy: "node", workflowId }), [workflowId]);
  const [selected, setSelected] = useState<string>();
  const graph = validation?.graph;
  const states = useMemo(() => overlayStates(detail.data), [detail.data]);
  const node = selected ?? detail.data?.summary.currentNode ?? manifest?.plannedPath?.[0];

  return (
    <>
      <div className="readonly-bar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#5B5F6A" strokeWidth="2" aria-hidden="true">
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        </svg>
        Read-only. Rendered from <code>graph.get_graph()</code> in Vercel Sandbox for the current draft. Edit the code to
        change the graph.
      </div>
      <div className="graph-grid">
        <section className="graph-card" aria-label="Workflow graph">
          {validating && <div className="graph-wait">Compiling the draft in Vercel Sandbox…</div>}
          {!validating && validation && !graph && (
            <div className="graph-wait">
              <b>The draft does not compile.</b>
              {validation.checks
                .filter((c) => !c.ok)
                .map((c) => (
                  <div key={c.name} className="check-msg">
                    {c.name}: {c.file ? `${c.file}${c.line ? `:${c.line}` : ""} · ` : ""}
                    {c.message}
                  </div>
                ))}
            </div>
          )}
          {graph && (
            <GraphView graph={graph} plannedPath={manifest?.plannedPath} states={states} selected={node} onSelect={setSelected} />
          )}
        </section>
        <NodeAside
          node={node}
          manifest={manifest}
          files={files}
          kind={graph?.nodes.find((n) => n.id === node)?.kind}
          usage={usage.data?.rows.find((r) => r.key === node)}
          onOpen={onOpen}
        />
      </div>
    </>
  );
}

function NodeAside({ node, manifest, files, kind, usage, onOpen }: {
  node?: string;
  manifest?: WorkflowManifest;
  files: DraftFile[];
  kind?: string;
  usage?: { runs: number; costUsd: number };
  onOpen: (path: string) => void;
}) {
  if (!node) return <aside className="card node-aside" />;
  const source =
    files.find((f) => f.path === `steps/${node}.py`)?.path ??
    files.find((f) => f.path.endsWith(".py") && new RegExp(`^def ${node}\\(`, "m").test(f.content))?.path;
  const prompt = files.find((f) => f.path === `prompts/${node}.md`)?.path;
  const interrupt = kind === "interrupt";
  const model = interrupt ? "human" : (manifest?.models?.nodes?.[node] ?? manifest?.models?.default);
  return (
    <aside className="card node-aside" aria-label="Selected node">
      <div className="eyebrow">Selected node</div>
      <h2 className="node-title">{node}</h2>
      <div className="muted small">
        {interrupt
          ? "Human approval: LangGraph interrupt(). The run waits for Approve / Request changes / Reject in VS Code."
          : node === "gate"
            ? "Deterministic checks: tests, invariant property tests, secret and security scans."
            : "Agent step. Runs a CLI agent with the prompt below and the model from workflow.toml."}
      </div>
      <dl className="kv">
        <div><dt>Source</dt><dd className="mono">{source ?? "—"}</dd></div>
        <div><dt>Prompt</dt><dd className="mono">{prompt ?? "—"}</dd></div>
        <div><dt>Model</dt><dd className="mono">{model ?? "—"}</dd></div>
        <div><dt>Weight</dt><dd>{manifest?.weights?.[node] ?? "—"}</dd></div>
      </dl>
      <dl className="kv">
        <div className="kv-title">All runs of this workflow</div>
        <div><dt>Runs that used it</dt><dd>{usage?.runs ?? 0}</dd></div>
        <div><dt>Avg cost per run</dt><dd>{usage && usage.runs ? usd(usage.costUsd / usage.runs) : "—"}</dd></div>
      </dl>
      {source && (
        <button type="button" className="btn btn-block" onClick={() => onOpen(source)}>
          Open in code
        </button>
      )}
    </aside>
  );
}

function PublishDialog({ workflowId, version, suggested, flush, onClose, onPublished }: {
  workflowId: string;
  version: string | null;
  suggested: string;
  flush: () => Promise<void>;
  onClose: () => void;
  onPublished: (r: Release) => void;
}) {
  const [channel, setChannel] = useState<"" | ChannelName>("beta");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [done, setDone] = useState<Release>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!version) return;
    setBusy(true);
    setError(undefined);
    try {
      await flush();
      const r = await api.publish(workflowId, { version, ...(channel ? { channel } : {}), ...(notes ? { notes } : {}) });
      setDone(r);
      onPublished(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-back" role="presentation" onClick={onClose}>
      <form className="modal" role="dialog" aria-label="Publish" onSubmit={submit} onClick={(e) => e.stopPropagation()}>
        <h2 className="h2">Publish {workflowId}</h2>
        {done ? (
          <>
            <p>
              Published <b className="mono">{done.release}</b>
              {done.channels?.length ? ` to ${done.channels.join(", ")}` : ""}. The release is immutable.
            </p>
            <dl className="kv">
              <div><dt>Digest</dt><dd className="mono xsmall">{done.digest}</dd></div>
              <div><dt>Bundle</dt><dd>{done.bundleBytes} bytes in Vercel Blob</dd></div>
            </dl>
            <p className="muted small">The VS Code extension syncs the channel, checks the digest and installs it.</p>
            <div className="modal-actions">
              <button type="button" className="btn btn-dark" onClick={onClose}>
                Close
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="muted small">
              Bundles the draft as a deterministic .zip, validates it in Vercel Sandbox, stores it in Blob and creates an
              immutable release.
            </p>
            <div className="field">
              <span className="field-label">Version (from workflow.toml)</span>
              <span className="mono">{version ?? "missing"}</span>
              {version && version === suggested ? null : (
                <span className="muted xsmall">Change the version in workflow.toml; suggested next: {suggested}</span>
              )}
            </div>
            <fieldset className="field">
              <legend className="field-label">Channel</legend>
              {(["beta", "stable", ""] as const).map((c) => (
                <label key={c || "none"} className="radio">
                  <input type="radio" name="channel" checked={channel === c} onChange={() => setChannel(c)} />
                  {c || "no channel (release only)"}
                </label>
              ))}
            </fieldset>
            <label className="field">
              <span className="field-label">Release notes</span>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="What changed and why" />
            </label>
            {error && <div className="error-note" role="alert">{error}</div>}
            <div className="modal-actions">
              <button type="button" className="btn" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="btn btn-dark" disabled={busy || !version}>
                {busy ? "Publishing…" : `Publish ${version ?? ""}`}
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
