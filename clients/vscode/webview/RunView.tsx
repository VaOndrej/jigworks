import { useEffect, useRef, useState } from "react";
import type { PriceEntry } from "@jigworks/contracts";
import prices from "../../../packages/contracts/fixtures/prices.json";
import type { HostState } from "../src/shared/messages";
import { apiCost, formatTokens } from "../src/shared/cost";
import { modelFor, type SessionView } from "../src/shared/session";
import { Graph } from "./Graph";
import { host } from "./host";
import { label, pct } from "./parts";

const PRICES = prices as PriceEntry[];

function weightsOf(state: HostState, s: SessionView): Record<string, number> {
  const wf = state.workflows.find((w) => w.release === s.release);
  const out: Record<string, number> = {};
  for (const n of wf?.graph?.nodes ?? []) if (typeof n.weight === "number") out[n.id] = n.weight;
  for (const n of s.plannedPath) if (out[n] === undefined) out[n] = 1;
  return out;
}

function ProgressCard({ s, weights, interruptNodes }: { s: SessionView; weights: Record<string, number>; interruptNodes: string[] }) {
  const total = s.plannedPath.reduce((a, n) => a + (weights[n] ?? 1), 0) || 1;
  let acc = 0;
  const bounds = s.plannedPath.map((n) => {
    const start = (acc / total) * 100;
    acc += weights[n] ?? 1;
    return { n, start, end: (acc / total) * 100 };
  });
  const current = bounds.find((b) => b.n === (s.interrupt?.node ?? s.currentNode));
  const nextHuman = bounds.find((b) => interruptNodes.includes(b.n) && s.nodes[b.n]?.status !== "succeeded");
  const node = s.interrupt?.node ?? s.currentNode;
  const detail = [
    `step ${Math.min(s.step + (node ? 1 : 0), s.stepsPlanned)} of ${s.stepsPlanned}`,
    node ? `${label(node)}${(s.currentAttempt ?? 1) > 1 ? `, attempt ${s.currentAttempt}` : ""}` : s.status,
    `${s.fixLoops} fix loop${s.fixLoops === 1 ? "" : "s"} so far`,
  ];
  return (
    <section className="card progress-card" aria-label="Progress">
      <div className="row-base gap-12">
        <span className="big">{pct(s.progress)}</span>
        <span className="muted">of the plan done · {detail.join(" · ")}</span>
      </div>
      <div className="pbar">
        <div className="pbar-done" style={{ width: `${s.progress}%` }} />
        {current && s.status === "running" && (
          <div className="pbar-now" style={{ left: `${current.start}%`, width: `${current.end - current.start}%` }} />
        )}
        {bounds.slice(0, -1).map((b) => (
          <div key={b.n} className="pbar-tick" style={{ left: `${b.end}%` }} />
        ))}
        {nextHuman && <div className="pbar-human" style={{ left: `${nextHuman.start}%` }} />}
      </div>
      <div className="row-between small muted">
        <span>% of plan = weight of finished planned steps / weight of the planned path. A fix loop adds work, so the % can stay put for a while.</span>
        {nextHuman && <span className="amber">your {nextHuman.n === "approve_plan" ? "plan approval" : "review"} ≈ {Math.round(nextHuman.start)} %</span>}
      </div>
    </section>
  );
}

function Output({ s, initialTab }: { s: SessionView; initialTab: "activity" | "output" }) {
  // Agent output is opt-in (design.md §7: "for people who like to watch").
  const [tab, setTab] = useState<"activity" | "output">(initialTab);
  const [follow, setFollow] = useState(true);
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (follow && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  });
  const node = (s.status === "running" ? s.currentNode : undefined) ?? s.output[s.output.length - 1]?.node;
  const header = node ? `${label(node)} #${s.nodes[node]?.attempt ?? 1} · claude -p · ${modelFor(s, node)} (from workflow)` : "";
  return (
    <section className="output" aria-label="Agent output">
      <div className="tabs">
        <button type="button" className={tab === "activity" ? "tab on" : "tab"} onClick={() => setTab("activity")}>Activity</button>
        <button type="button" className={tab === "output" ? "tab on" : "tab"} onClick={() => setTab("output")}>Agent output</button>
        <label className="follow"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />Follow live</label>
      </div>
      <pre ref={ref} className="log mono">
        {tab === "output" ? (
          <>
            {header && <span className="dim">{header}{"\n"}</span>}
            {s.output.slice(-120).map((l) => (
              <span key={l.seq} className={`l-${l.kind}${l.isError ? " err" : ""}`}>
                {l.kind === "tool" ? "▸ " : l.kind === "denied" ? "⊘ denied " : l.kind === "result" ? "  ↳ " : ""}
                {l.text}
                {"\n"}
              </span>
            ))}
            {s.status === "running" && <span className="cursor" />}
          </>
        ) : (
          s.activity.map((a) => (
            <span key={a.seq} className={`a-${a.tone}`}>{a.text}{"\n"}</span>
          ))
        )}
      </pre>
    </section>
  );
}

function NextForYou({ s, interruptNodes, weights }: { s: SessionView; interruptNodes: string[]; weights: Record<string, number> }) {
  const [comment, setComment] = useState("");
  const cost = apiCost(PRICES, s.usageRecords);
  const usage = (
    <div className="row-between small muted push-bottom">
      <span>in {formatTokens(s.usage.input)} · out {formatTokens(s.usage.output)} · cache {formatTokens(s.usage.cache_write + s.usage.cache_read)}</span>
      <span className="strong" title="API-equivalent cost from the price table">${cost.usd.toFixed(2)}</span>
    </div>
  );
  const decide = (decision: "approve" | "request_changes" | "reject") =>
    host().postMessage({ type: "decide", runId: s.runId, decision, comment: decision === "request_changes" ? comment : undefined });

  if (s.status === "waiting_human" && s.interrupt) {
    const i = s.interrupt;
    return (
      <section className="card next waiting" aria-label="Next for you">
        <div className="eyebrow amber">YOUR DECISION · {i.node === "approve_brainstorm" ? "BRAINSTORMING" : i.stage === "plan" ? "PLAN" : "BEFORE THE PR"}</div>
        <div>{i.message}</div>
        {i.plan && <pre className="plan mono">{i.plan}</pre>}
        {i.diffStat && (
          <div className="small muted">
            {i.diffStat.files} files · <span className="green">+{i.diffStat.linesAdded}</span> <span className="red">−{i.diffStat.linesRemoved}</span>
            {i.commit && <> · commit <span className="mono">{i.commit.slice(0, 10)}</span></>}
          </div>
        )}
        {i.stage === "pr" && s.lastGate && (
          <details className="report small">
            <summary>Test report: gate {s.lastGate.passed ? "PASS" : "FAIL"} ({s.lastGate.checks.filter((c) => c.passed).length}/{s.lastGate.checks.length} checks)</summary>
            {s.lastGate.checks.map((c) => (
              <div key={c.name} className={c.passed ? "green" : "red"}>{c.passed ? "✓" : "✗"} {c.name} <span className="dim">· {c.summary}</span></div>
            ))}
          </details>
        )}
        <div className="links small">
          <button type="button" className="link" onClick={() => host().postMessage({ type: "openDiff", runId: s.runId })}>Diff (worktree)</button>
          <button type="button" className="link" onClick={() => host().postMessage({ type: "openAudit", runId: s.runId })}>Audit log</button>
        </div>
        <label htmlFor={`c-${s.runId}`} className="sr-only">Comment for the agent</label>
        <textarea id={`c-${s.runId}`} className="comment" placeholder={i.stage === "plan" ? "Request changes: your answers or comments for the agent" : "Request changes: what should the agent change?"} value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="actions">
          <button type="button" className="btn approve" onClick={() => decide("approve")}>Approve</button>
          <button type="button" className="btn changes" disabled={!comment.trim()} onClick={() => decide("request_changes")}>Request changes</button>
          <button type="button" className="btn reject" onClick={() => decide("reject")}>Reject</button>
        </div>
        {usage}
      </section>
    );
  }

  const total = s.plannedPath.reduce((a, n) => a + (weights[n] ?? 1), 0) || 1;
  let acc = 0;
  let at = 0;
  const next = s.plannedPath.find((n) => {
    if (interruptNodes.includes(n) && s.nodes[n]?.status !== "succeeded") {
      at = (acc / total) * 100;
      return true;
    }
    acc += weights[n] ?? 1;
    return false;
  });
  return (
    <section className="card next" aria-label="Next for you">
      {s.status === "paused_usage_limit" ? (
        <>
          <div className="eyebrow amber">PAUSED · USAGE LIMIT</div>
          <div>The Claude subscription limit was reached{s.usageLimit?.resetsAt ? `; it resets at ${s.usageLimit.resetsAt.slice(11, 16)} UTC` : ""}. The run keeps its checkpoint.</div>
          <div className="actions"><button type="button" className="btn changes" onClick={() => host().postMessage({ type: "resume", runId: s.runId })}>Resume</button></div>
        </>
      ) : next && s.status === "running" ? (
        <>
          <div className="eyebrow amber">NEXT FOR YOU · AT ≈ {Math.round(at)} %</div>
          <div>{next === "approve_plan" ? "Approve the plan." : "Review before PR."} You will get three choices:</div>
          <div className="choices small">
            <span><b className="green">Approve</b> · {next === "approve_plan" ? "go on with the plan" : "open the PR"}</span>
            <span><b className="blue">Request changes</b> · a follow-up prompt back to the agent</span>
            <span><b className="red">Reject</b> · stop the run</span>
          </div>
        </>
      ) : (
        <>
          <div className="eyebrow">{s.status.toUpperCase()}</div>
          {s.prUrl && <div className="small">PR: <span className="mono">{s.prUrl}</span></div>}
          {s.error && <div className="small red">{s.error.message}</div>}
        </>
      )}
      {usage}
    </section>
  );
}

export function RunView({ state, s, initialTab = "activity" }: { state: HostState; s: SessionView; initialTab?: "activity" | "output" }) {
  const wf = state.workflows.find((w) => w.release === s.release);
  const interruptNodes = wf?.interruptNodes ?? s.plannedPath.filter((n) => n.startsWith("approve_"));
  const weights = weightsOf(state, s);
  const running = state.running.includes(s.runId);
  return (
    <div className="run">
      <div className="run-head">
        <div className="grow">
          <h1 className="h1 small-h1">{s.title}</h1>
          <div className="small muted">
            {s.release} · worktree <span className="mono">{s.branch ?? s.runId}</span> · models from the workflow · started {s.startedAt?.slice(11, 16) ?? "–"}
          </div>
        </div>
        <button type="button" className="ghost" onClick={() => host().postMessage({ type: "openDiff", runId: s.runId })}>Open worktree</button>
        {running ? (
          <button type="button" className="ghost" onClick={() => host().postMessage({ type: "stop", runId: s.runId })}>Stop</button>
        ) : s.status === "running" || s.status === "paused_usage_limit" ? (
          <button type="button" className="ghost" onClick={() => host().postMessage({ type: "resume", runId: s.runId })}>Resume</button>
        ) : null}
      </div>
      <ProgressCard s={s} weights={weights} interruptNodes={interruptNodes} />
      <Graph s={s} graph={wf?.graph} interruptNodes={interruptNodes} />
      <div className="bottom">
        <Output s={s} initialTab={initialTab} />
        <NextForYou s={s} interruptNodes={interruptNodes} weights={weights} />
      </div>
    </div>
  );
}
