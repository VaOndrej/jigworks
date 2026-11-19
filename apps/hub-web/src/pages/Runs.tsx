import { useMemo, useState } from "react";
import type { HumanDelta, RunSummary } from "@jigworks/contracts";
import { api, type Overview } from "../api";
import { useLoad } from "../data";
import { deltaLabel, duration, pct, statusLabel, time, tokens, usd, who, workedFirstTime } from "../format";
import { navigate } from "../router";
import { timeline, type Part } from "../timeline";
import { ErrorNote, Pill, Planned, Stat } from "../ui";

const PERIODS = { "7d": 7, "30d": 30, all: 3650 } as const;
type Period = keyof typeof PERIODS;

export function RunsPage({ runId }: { runId?: string }) {
  const [workflow, setWorkflow] = useState("");
  const [period, setPeriod] = useState<Period>("7d");
  const range = useMemo(() => {
    const to = new Date();
    const from = new Date(to.getTime() - PERIODS[period] * 86400000);
    return { from: from.toISOString(), to: to.toISOString() };
  }, [period]);

  const workflows = useLoad(() => api.workflows(), []);
  const compareId = workflow || workflows.data?.workflows[0]?.id;
  const overview = useLoad(() => api.overview({ workflowId: workflow || undefined, ...range }), [workflow, range]);
  const runs = useLoad(() => api.runs({ workflowId: workflow || undefined }), [workflow]);
  const outcomes = useLoad(() => api.outcomes(workflow || undefined), [workflow]);
  const comparison = useLoad(() => (compareId ? api.releaseComparison(compareId) : Promise.resolve(undefined)), [compareId]);
  const releases = useLoad(() => (compareId ? api.releases(compareId) : Promise.resolve(undefined)), [compareId]);

  const inPeriod = (runs.data?.runs ?? []).filter((r) => r.startedAt >= range.from);
  const deltas = outcomes.data?.deltas ?? [];
  const deltaByRun = new Map(deltas.map((d) => [d.runId, d]));
  const selected = runId ?? inPeriod.find((r) => r.approverEmail)?.runId ?? inPeriod[0]?.runId;

  return (
    <main className="page">
      <div className="page-head page-head-filters">
        <div className="grow min0">
          <h1 className="h1">Runs &amp; analytics</h1>
          <p className="lead">
            Every run is an audit record. The numbers are computed from those records: raw tokens × a price table with
            validity.
          </p>
        </div>
        <label htmlFor="f-wf" className="muted small">Workflow</label>
        <select id="f-wf" className="select" value={workflow} onChange={(e) => setWorkflow(e.target.value)}>
          <option value="">All workflows</option>
          {workflows.data?.workflows.map((w) => (
            <option key={w.id} value={w.id}>{w.id}</option>
          ))}
        </select>
        <label htmlFor="f-period" className="muted small">Period</label>
        <select id="f-period" className="select" value={period} onChange={(e) => setPeriod(e.target.value as Period)}>
          <option value="7d">{periodLabel(range.from, range.to)}</option>
          <option value="30d">Last 30 days</option>
          <option value="all">All time</option>
        </select>
      </div>
      <ErrorNote error={overview.error ?? runs.error} />

      <KeyNumbers o={overview.data} deltas={deltas} />

      <div className="split">
        <CostChart o={overview.data} />
        <OutcomesPanel deltas={deltas} />
      </div>

      <section className="card" aria-label="Compare versions">
        <h2 className="h2">Compare versions · {compareId}</h2>
        <p className="muted small">Is the new version better? All runs per version, same price table.</p>
        <div className="table-wrap">
          <table className="table table-compact">
            <thead>
              <tr>
                <th>Version</th>
                <th>Runs</th>
                <th>Success</th>
                <th>Gate pass 1st try</th>
                <th>Avg fix loops</th>
                <th>Follow-up prompts</th>
                <th>Worked first time <Planned /></th>
                <th>Median time to PR</th>
                <th>Avg cost</th>
              </tr>
            </thead>
            <tbody>
              {(comparison.data?.rows ?? []).map((row) => {
                const rel = releases.data?.releases.find((r) => r.version === row.version);
                const stats = overview.data?.releases.find((r) => r.release === row.release);
                const stable = rel?.channels?.includes("stable");
                return (
                  <tr key={row.release} className={stable ? "row-stable" : ""}>
                    <td className={stable ? "strong" : ""}>
                      {row.version}{" "}
                      {rel?.channels?.map((c) => (
                        <Pill key={c} tone={c === "stable" ? "green" : "orange"}>{c}</Pill>
                      ))}
                    </td>
                    <td>{row.runs}</td>
                    <td>{pct(row.successRate)}</td>
                    <td>{pct(stats?.gatePassFirstTry)}</td>
                    <td>{row.runs ? row.avgFixLoops.toFixed(1) : "—"}</td>
                    <td>{row.avgFollowUpPrompts?.toFixed(1) ?? "—"}</td>
                    <td>{pct(workedFirstTime(deltas.filter((d) => d.release === row.release)))}</td>
                    <td>{duration(stats?.medianTimeToPrSec)}</td>
                    <td>{row.runs ? usd(row.avgCostUsd) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <PromotionNote rows={comparison.data?.rows ?? []} />
      </section>

      <div className="split split-top">
        <section className="card card-table grow" aria-label="Runs">
          <h2 className="h2 pad">Runs</h2>
          <table className="table table-runs">
            <thead>
              <tr>
                <th className="pl">Run</th>
                <th>Task</th>
                <th>Author → approver</th>
                <th>Status</th>
                <th>Human delta <Planned /></th>
                <th className="pr">Cost</th>
              </tr>
            </thead>
            <tbody>
              {inPeriod.map((r) => (
                <RunRow key={r.runId} run={r} delta={deltaByRun.get(r.runId)} selected={r.runId === selected} />
              ))}
              {!inPeriod.length && !runs.loading && (
                <tr><td colSpan={6} className="pl muted">No runs in this period.</td></tr>
              )}
            </tbody>
          </table>
        </section>
        {selected && <RunDetailPanel runId={selected} delta={deltaByRun.get(selected)} />}
      </div>
    </main>
  );
}

function periodLabel(from: string, to: string) {
  const f = new Date(from);
  const t = new Date(to);
  const fmt = (d: Date, month: boolean) => d.toLocaleDateString("en-GB", { day: "numeric", ...(month ? { month: "short", year: "numeric" } : {}) });
  return `${fmt(f, f.getMonth() !== t.getMonth())}–${fmt(t, true)}`;
}

function KeyNumbers({ o, deltas }: { o?: Overview; deltas: HumanDelta[] }) {
  const rel = o?.releases.filter((r) => r.gatePassFirstTry !== null && r.gatePassFirstTry !== undefined) ?? [];
  const last = rel[rel.length - 1];
  const prev = rel[rel.length - 2];
  const change = last && prev ? Math.round(((last.gatePassFirstTry ?? 0) - (prev.gatePassFirstTry ?? 0)) * 100) : null;
  return (
    <section className="stats-grid" aria-label="Key numbers">
      <Stat label="Runs" value={o?.runs ?? "…"} note={o ? `${o.running} running · ${o.waitingHuman} waiting for a human` : undefined} />
      <Stat
        label="Gate pass, first try"
        value={pct(o?.gatePassFirstTry)}
        note={change !== null ? `${change >= 0 ? "+" : ""}${change} pts in ${last.release.split("@")[1]} vs ${prev.release.split("@")[1]}` : o ? `${o.gateRuns} runs reached the gate` : undefined}
        noteTone={change !== null && change >= 0 ? "good" : "muted"}
      />
      <Stat label="Worked first time" planned value={pct(workedFirstTime(deltas))} note="no follow-up prompt, no hand edit · sample" />
      <Stat label="Median time to PR" value={duration(o?.medianTimeToPrSec)} note={o?.medianHumanWaitSec ? `of which waiting for humans ${duration(o.medianHumanWaitSec)}` : undefined} />
      <Stat label="Cost" value={o ? usd(o.costUsd) : "…"} note={o ? `API equivalent · ${usd(o.costPerRunUsd)} per run` : undefined} />
    </section>
  );
}

const TOKEN_COLORS = { input: "#1E3A8A", output: "#C2410C", cache_write: "#F0A868", cache_read: "#9DB8F5" } as const;
const TOKEN_LABELS = { input: "input", output: "output", cache_write: "cache write", cache_read: "cache read" } as const;
type TokenKey = keyof typeof TOKEN_COLORS;

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v)!;
}

function CostChart({ o }: { o?: Overview }) {
  const days = (o?.costByDay ?? []).slice(-14);
  const totals = days.map((d) => d.input + d.output + d.cache_write + d.cache_read);
  const max = niceMax(Math.max(0, ...totals));
  const H = 160;
  const keys: TokenKey[] = ["input", "output", "cache_write", "cache_read"];
  return (
    <section className="card grow" aria-label="Cost per day">
      <div className="card-head wrap">
        <h2 className="h2">Cost per day by token type</h2>
        <div className="chart-legend">
          {keys.map((k) => (
            <span key={k}><i style={{ background: TOKEN_COLORS[k] }} />{TOKEN_LABELS[k]}</span>
          ))}
        </div>
      </div>
      <div className="chart">
        <div className="chart-axis">
          <span>{usd(max, Number.isInteger(max) ? 0 : 2)}</span>
          <span>{usd(max / 2, Number.isInteger(max / 2) ? 0 : 2)}</span>
          <span>$0</span>
        </div>
        <div className="chart-plot" style={{ height: H }}>
          {days.map((d, i) => {
            const last = i === days.length - 1;
            return (
              <div
                key={d.day}
                className={`bar ${last ? "bar-today" : ""}`}
                title={`${d.day}: ${usd(totals[i])} (${keys.map((k) => `${TOKEN_LABELS[k]} ${usd(d[k])}`).join(", ")})`}
              >
                {keys.map((k) => (
                  <span key={k} style={{ height: (d[k] / max) * H, background: TOKEN_COLORS[k] }} />
                ))}
              </div>
            );
          })}
        </div>
      </div>
      <div className="chart-x">
        {days.map((d, i) => (
          <span key={d.day} className={i === days.length - 1 ? "strong" : ""}>
            {new Date(d.day).getUTCDate()}
            {i === days.length - 1 ? ` · ${usd(totals[i])}` : ""}
          </span>
        ))}
      </div>
      <p className="muted xsmall">API equivalent: raw tokens per call × the price valid at the call time. Cache tokens are priced separately.</p>
    </section>
  );
}

const OUTCOMES = [
  { key: "worked_first_time", label: "Worked first time", color: "#0F766E" },
  { key: "corrected_by_prompt", label: "Corrected by a follow-up prompt", color: "#5B8DEF" },
  { key: "edited_by_hand", label: "Edited by hand before push", color: "#F0A868" },
  { key: "rejected", label: "Rejected", color: "#9B1C1C" },
] as const;

function OutcomesPanel({ deltas }: { deltas: HumanDelta[] }) {
  const n = deltas.length || 1;
  const share = OUTCOMES.map((o) => ({ ...o, v: deltas.filter((d) => d.outcome === o.key).length / n }));
  const files = new Map<string, number>();
  for (const d of deltas) for (const f of d.files) files.set(f, (files.get(f) ?? 0) + 1);
  const top = [...files.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
  return (
    <section className="card side" aria-label="Outcomes">
      <div className="card-head start">
        <h2 className="h2">What humans did with the result</h2>
        <Planned />
      </div>
      <p className="muted xsmall">
        Baseline is the first result of a session. Every later prompt and every hand edit before merge is stored as a diff
        against it. Sample data ({deltas.length} recorded sessions), not computed yet.
      </p>
      <div className="outcome-bar" role="img" aria-label={share.map((s) => `${s.label} ${Math.round(s.v * 100)} percent`).join(", ")}>
        {share.map((s) => <span key={s.key} style={{ width: `${s.v * 100}%`, background: s.color }} />)}
      </div>
      <div className="outcome-list">
        {share.map((s) => (
          <div key={s.key}>
            <span><i style={{ background: s.color }} />{s.label}</span>
            <b>{Math.round(s.v * 100)} %</b>
          </div>
        ))}
      </div>
      <div className="outcome-edits">
        <div className="strong">Where humans edit most</div>
        {top.length ? (
          top.map(([f, c]) => (
            <div key={f} className="kv-line"><span className="mono xsmall">{f}</span><span className="muted">{c} run{c === 1 ? "" : "s"}</span></div>
          ))
        ) : (
          <div className="muted small">No hand edits in the sample yet.</div>
        )}
        <span className="muted small" title="Planned: supervised workflow learning">Propose a workflow change from these edits (planned)</span>
      </div>
    </section>
  );
}

function PromotionNote({ rows }: { rows: { version: string; runs: number }[] }) {
  const latest = rows[rows.length - 1];
  if (!latest || rows.length < 2) return null;
  return latest.runs < 20 ? (
    <p className="muted xsmall">
      {latest.version} has {latest.runs} run{latest.runs === 1 ? "" : "s"}; too few to judge. The hub suggests promotion after
      20 runs with no regression.
    </p>
  ) : null;
}

function RunRow({ run, delta, selected }: { run: RunSummary; delta?: HumanDelta; selected: boolean }) {
  const s = statusLabel(run);
  return (
    <tr className={`clickable ${selected ? "row-selected" : ""}`} onClick={() => navigate(`/runs/${run.runId}`)}>
      <td className="pl mono xsmall">{run.runId}</td>
      <td>
        <div className="strong">{run.title ?? "—"}</div>
        <div className="muted xsmall">{run.release}</div>
      </td>
      <td>
        {who(run.authorEmail)} → {run.approverEmail ? who(run.approverEmail) : "—"}
      </td>
      <td><Pill tone={s.tone}>{s.text}</Pill></td>
      <td className={delta?.outcome === "worked_first_time" ? "good" : "muted"}>{deltaLabel(delta)}</td>
      <td className="pr">{usd(run.costUsd)}</td>
    </tr>
  );
}

function PartView({ p }: { p: Part }) {
  switch (p.t) {
    case "who":
      return <b>{p.v}</b>;
    case "pass":
      return <span className="good strong">{p.v}</span>;
    case "fail":
      return <span className="bad strong">{p.v}</span>;
    case "mono":
      return <span className="mono xsmall">{p.v}</span>;
    case "pill":
      return <Pill tone="green">{p.v}</Pill>;
    default:
      return <>{p.v}</>;
  }
}

function RunDetailPanel({ runId, delta }: { runId: string; delta?: HumanDelta }) {
  const detail = useLoad(() => api.run(runId), [runId]);
  const d = detail.data;
  const lines = d?.audit ? timeline(d.audit) : [];
  const u = d?.summary.usage;
  return (
    <aside className="card side run-detail" aria-label="Run detail">
      <div className="card-head">
        <h2 className="h2">{runId} · audit trail</h2>
        {d && <span className="mono xsmall muted" title={d.summary.digest}>{d.summary.digest.slice(0, 11)}…{d.summary.digest.slice(-4)}</span>}
      </div>
      <ErrorNote error={detail.error} />
      <div className="timeline">
        {lines.map((l, i) => (
          <div key={i} className="tl-line">
            <span className="muted">{time(l.at)}</span>
            <span>{l.parts.map((p, j) => <PartView key={j} p={p} />)}</span>
          </div>
        ))}
      </div>
      {d?.audit?.changedFiles?.length ? (
        <div className="muted xsmall">Changed: {d.audit.changedFiles.join(", ")}</div>
      ) : null}
      <div className="delta-box">
        <div className="strong small">
          Human delta <Planned />
        </div>
        {delta ? (
          <>
            <div className="small">
              {deltaLabel(delta)}
              {delta.files.length ? ` · ${delta.files.join(", ")}` : ""}
            </div>
            <div className="muted xsmall">
              Sample record: first result of the session ({delta.firstResultCommit ?? "—"}) vs what was merged. Once capture is
              built it is stored in the hub and grouped with similar corrections as input for a supervised workflow change.
            </div>
          </>
        ) : (
          <div className="muted xsmall">No sample for this run. Captured after merge once the human-delta loop is built.</div>
        )}
      </div>
      <div className="detail-foot">
        <span className="muted">
          {u ? `in ${tokens(u.input)} · out ${tokens(u.output)} · cache ${tokens(u.cache_write + u.cache_read)}` : ""}
        </span>
        <b>{usd(d?.summary.costUsd)}</b>
      </div>
    </aside>
  );
}
