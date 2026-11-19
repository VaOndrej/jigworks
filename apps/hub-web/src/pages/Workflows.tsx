import { useState, type FormEvent } from "react";
import type { Release, RunSummary, WorkflowSummary } from "@jigworks/contracts";
import { api } from "../api";
import { useLoad } from "../data";
import { ago, pct, shape, shapeLabel, shortDay, usd, who, workedFirstTime } from "../format";
import { Link, navigate } from "../router";
import { ErrorNote, Pill, Planned, Progress, ReviewBadge, ShapeBar, Stat } from "../ui";

export function WorkflowsPage() {
  const wf = useLoad(() => api.workflows(), []);
  const overview = useLoad(() => api.overview(), []);
  const outcomes = useLoad(() => api.outcomes(), []);
  const live = useLoad(() => api.runs({ status: "live" }), []);
  const releases = useLoad(async () => {
    const list = await api.workflows();
    const all = await Promise.all(list.workflows.map((w) => api.releases(w.id)));
    return all.flatMap((r) => r.releases);
  }, []);
  const [creating, setCreating] = useState(false);

  const o = overview.data;
  const deltas = outcomes.data?.deltas ?? [];
  const change = o && o.previousRuns ? Math.round(((o.runs - o.previousRuns) / o.previousRuns) * 100) : null;
  const latestByWorkflow = new Map<string, Release>();
  for (const r of releases.data ?? []) {
    const cur = latestByWorkflow.get(r.workflowId);
    if (!cur || r.publishedAt > cur.publishedAt) latestByWorkflow.set(r.workflowId, r);
  }

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1 className="h1">Workflows</h1>
          <p className="lead">
            Shared, versioned ways of working with agents. Publish once; every engineer runs the same pinned version from
            VS Code.
          </p>
        </div>
        <button type="button" className="btn btn-accent" onClick={() => setCreating(true)}>
          New workflow
        </button>
      </div>
      {creating && <NewWorkflow onClose={() => setCreating(false)} />}

      <section className="stats-strip" aria-label="This week">
        <Stat
          label="Runs this week"
          value={o ? o.runs : "…"}
          note={change !== null ? `${change >= 0 ? "+" : ""}${change} %` : o ? "first week" : undefined}
          noteTone={change !== null && change >= 0 ? "good" : "muted"}
        />
        <Stat label="Worked first time" planned value={pct(workedFirstTime(deltas))} note="no follow-up, no edit · sample" />
        <Stat
          label="Waiting for review"
          value={o ? o.waitingHuman : "…"}
          valueTone="amber"
          note={o?.oldestWaitingSince ? `oldest ${ago(o.oldestWaitingSince).replace(" ago", "")}` : undefined}
        />
        <Stat label="Cost this week" value={o ? usd(o.costUsd) : "…"} note={o ? `${usd(o.costPerRunUsd)} / run · API equivalent` : undefined} />
      </section>

      <section className="card card-table">
        <ErrorNote error={wf.error} />
        <table className="table">
          <thead>
            <tr>
              <th className="pl">Workflow</th>
              <th style={{ width: 220 }}>Shape</th>
              <th>Channels</th>
              <th>Running</th>
              <th>Runs 7d</th>
              <th>
                Worked first time <Planned />
              </th>
              <th className="pr">Avg cost</th>
            </tr>
          </thead>
          <tbody>
            {(wf.data?.workflows ?? []).map((w) => (
              <WorkflowRow
                key={w.id}
                w={w}
                release={latestByWorkflow.get(w.id)}
                running={(live.data?.runs ?? []).filter((r) => r.workflowId === w.id && r.status === "running").length}
                stats={o?.workflows.find((s) => s.workflowId === w.id)}
                worked={workedFirstTime(deltas.filter((d) => d.release.startsWith(`${w.id}@`)))}
              />
            ))}
          </tbody>
        </table>
        <div className="legend">
          <span><i className="seg-agent" />agent</span>
          <span><i className="seg-review" />human review</span>
          <span><i className="seg-gate" />gate</span>
        </div>
      </section>

      <div className="split">
        <section className="card grow" aria-label="Live now">
          <div className="card-head">
            <h2 className="h2">Live now</h2>
            <Link to="/runs">All runs</Link>
          </div>
          {(live.data?.runs ?? []).length === 0 && !live.loading && <p className="muted">Nothing is running.</p>}
          {(live.data?.runs ?? []).map((r) => (
            <LiveRow key={r.runId} run={r} />
          ))}
        </section>

        <section className="card side" aria-label="Recent releases">
          <h2 className="h2">Recent releases</h2>
          {[...(releases.data ?? [])]
            .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt))
            .slice(0, 5)
            .map((r) => (
              <div className="release-row" key={r.id}>
                {r.channels?.length ? (
                  <Pill tone={r.channels[0] === "stable" ? "green" : "orange"}>{r.channels.join(" · ")}</Pill>
                ) : (
                  <Pill tone="grey">release</Pill>
                )}
                <div>
                  <b>
                    {r.workflowId} {r.version}
                  </b>
                  <div className="muted">
                    {r.publishedBy ? `${who(r.publishedBy)} · ` : ""}
                    {shortDay(r.publishedAt)}
                    {r.notes ? ` · ${r.notes}` : ""}
                  </div>
                </div>
              </div>
            ))}
        </section>
      </div>
    </main>
  );
}

function WorkflowRow({ w, release, running, stats, worked }: {
  w: WorkflowSummary;
  release: Release | undefined;
  running: number;
  stats: { costPerRunUsd?: number | null } | undefined;
  worked: number | null;
}) {
  const segments = shape(release?.manifest);
  return (
    <tr>
      <td className="pl">
        <Link to={`/workflows/${w.id}`} className="strong-link">
          {w.id}
        </Link>
        <div className="muted small">{w.description}</div>
      </td>
      <td>
        {segments.length ? (
          <>
            <ShapeBar segments={segments} />
            <div className="muted xsmall">{shapeLabel(segments)}</div>
          </>
        ) : (
          <span className="muted small">not published yet</span>
        )}
      </td>
      <td>
        <span className="pills">
          {w.channels.stable && <Pill tone="green">stable {w.channels.stable}</Pill>}
          {w.channels.beta && <Pill tone="orange">beta {w.channels.beta}</Pill>}
          {!w.channels.stable && !w.channels.beta && <span className="muted small">—</span>}
          {w.hasUnpublishedDraft && <Pill tone="grey">draft</Pill>}
        </span>
      </td>
      <td>
        {running ? (
          <span className="running-count">
            <i />
            {running}
          </span>
        ) : (
          <span className="muted">0</span>
        )}
      </td>
      <td>{w.runs7d ?? 0}</td>
      <td>{pct(worked)}</td>
      <td className="pr">{usd(stats?.costPerRunUsd)}</td>
    </tr>
  );
}

function LiveRow({ run }: { run: RunSummary }) {
  const waiting = run.status === "waiting_human";
  const paused = run.status === "paused_usage_limit";
  const p = run.progress ?? 0;
  return (
    <Link to={`/runs/${run.runId}`} className="live-row">
      <div className="min0">
        <div className="strong">{run.title ?? run.runId}</div>
        <div className="muted xsmall">
          {who(run.authorEmail)} · {run.release} · {waiting ? "review before PR" : (run.currentNode ?? "starting")}
        </div>
      </div>
      <Progress value={p} tone={waiting || paused ? "amber" : "blue"} />
      {waiting ? (
        <ReviewBadge />
      ) : paused ? (
        <Pill tone="amber">Paused · usage limit</Pill>
      ) : (
        <span className="live-pct">{Math.round(p)} %</span>
      )}
    </Link>
  );
}

function NewWorkflow({ onClose }: { onClose: () => void }) {
  const [id, setId] = useState("");
  const [error, setError] = useState<string>();
  const valid = /^[a-z0-9][a-z0-9-]*$/.test(id);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api.saveDraft(id, []); // an empty draft for a new id is filled from the template
      navigate(`/workflows/${id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <form className="card inline-form" onSubmit={submit}>
      <label htmlFor="new-wf">Workflow id</label>
      <input id="new-wf" value={id} onChange={(e) => setId(e.target.value.trim())} placeholder="bugfix-with-repro" autoFocus />
      <span className="muted small">lowercase, digits and dashes; starts from a minimal LangGraph template</span>
      <button type="submit" className="btn btn-dark" disabled={!valid}>
        Create
      </button>
      <button type="button" className="btn" onClick={onClose}>
        Cancel
      </button>
      {error && <div className="error-note">{error}</div>}
    </form>
  );
}
