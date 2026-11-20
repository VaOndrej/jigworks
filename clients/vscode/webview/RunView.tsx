import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { PriceEntry } from "@jigworks/contracts";
import prices from "../../../packages/contracts/fixtures/prices.json";
import type { HostState } from "../src/shared/messages";
import { apiCost, formatTokens } from "../src/shared/cost";
import { ago, elapsed, livenessState, recentActions, stepCounters, stepGerund, type Liveness } from "../src/shared/activity";
import { modelFor, nodeDone, type SessionView } from "../src/shared/session";
import { Graph } from "./Graph";
import { host, useNow } from "./host";
import { Markdown } from "./Markdown";
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
  const nextHuman = bounds.find((b) => interruptNodes.includes(b.n) && !nodeDone(s, b.n));
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
          <div className="pbar-now working" style={{ left: `${current.start}%`, width: `${current.end - current.start}%` }} />
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
  const ref = useRef<HTMLDivElement>(null);
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
      <div ref={ref} className="log mono">
        {tab === "output" ? (
          <>
            {header && <div className="dim">{header}</div>}
            {s.output.slice(-120).map((l) =>
              l.kind === "text" ? (
                <Markdown key={l.seq} text={l.text} className="l-text" />
              ) : (
                <div key={l.seq} className={`line l-${l.kind}${l.isError ? " err" : ""}`}>
                  {l.kind === "tool" ? "▸ " : l.kind === "denied" ? "⊘ denied " : l.kind === "result" ? "  ↳ " : ""}
                  {l.text}
                </div>
              ),
            )}
            {s.status === "running" && <span className="cursor" />}
          </>
        ) : (
          s.activity.map((a) => (
            <div key={a.seq} className={`line a-${a.tone}`}>{a.text}</div>
          ))
        )}
      </div>
    </section>
  );
}

type Decision = "approve" | "request_changes" | "reject";

function Usage({ s }: { s: SessionView }) {
  const cost = apiCost(PRICES, s.usageRecords);
  return (
    <div className="row-between small muted push-bottom">
      <span>in {formatTokens(s.usage.input)} · out {formatTokens(s.usage.output)} · cache {formatTokens(s.usage.cache_write + s.usage.cache_read)}</span>
      <span className="strong" title="API-equivalent cost from the price table">${cost.usd.toFixed(2)}</span>
    </div>
  );
}

/** If a sent decision never changes the state (the runner refused it), unlock the gate again. */
const UNLOCK_AFTER_MS = 20_000;

/**
 * One human gate. Keyed on the interrupt (node + event seq) by the caller, so every new gate,
 * e.g. brainstorming round 2, starts with an empty, enabled field. Text typed here is an answer:
 * it can only be sent as Request changes, never silently dropped by an Approve.
 */
function GateCard({ s, i }: { s: SessionView; i: NonNullable<SessionView["interrupt"]> }) {
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState<{ text: string } | undefined>();
  const hasText = comment.trim().length > 0;
  useEffect(() => {
    if (!sent) return;
    const t = setTimeout(() => {
      setComment((c) => c || sent.text);
      setSent(undefined);
    }, UNLOCK_AFTER_MS);
    return () => clearTimeout(t);
  }, [sent]);

  const decide = (decision: Decision) => {
    if (sent) return;
    if (decision === "request_changes" && !hasText) return;
    if (decision === "approve" && hasText) return;
    const text = comment.trim();
    host().postMessage({ type: "decide", runId: s.runId, decision, comment: decision === "request_changes" ? text : undefined });
    setSent({ text: comment });
    setComment("");
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    if (hasText) decide("request_changes");
  };
  const stage = i.node === "approve_brainstorm" ? "BRAINSTORMING" : i.stage === "plan" ? "PLAN" : "BEFORE THE PR";
  return (
    <section className="card next waiting" aria-label="Next for you" data-gate={`${i.node}#${i.seq}`}>
      <div className="eyebrow amber">YOUR DECISION · {stage}</div>
      {i.message && <Markdown text={i.message} className="md-message" />}
      {i.plan && <Markdown text={i.plan} className="plan" />}
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
      <textarea
        id={`c-${s.runId}`}
        className="comment"
        placeholder="Your answers or comments for the agent · Enter to send, Shift+Enter for a new line"
        value={comment}
        disabled={!!sent}
        onChange={(e) => setComment(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="actions">
        <button type="button" className={hasText ? "btn approve" : "btn approve primary"} disabled={!!sent || hasText} onClick={() => decide("approve")}>Approve</button>
        <button type="button" className={hasText ? "btn changes primary" : "btn changes"} disabled={!!sent || !hasText} onClick={() => decide("request_changes")}>Request changes</button>
        <button type="button" className="btn reject" disabled={!!sent} onClick={() => decide("reject")}>Reject</button>
      </div>
      <div className="gate-hint small" aria-live="polite">
        {sent
          ? "Sent. Waiting for the runner…"
          : hasText
            ? "Enter sends your text as Request changes · clear the text to approve"
            : "Type an answer and press Enter to request changes, or Approve as it is"}
      </div>
      <Usage s={s} />
    </section>
  );
}

function nextGate(s: SessionView, interruptNodes: string[], weights: Record<string, number>) {
  const total = s.plannedPath.reduce((a, n) => a + (weights[n] ?? 1), 0) || 1;
  let acc = 0;
  for (const n of s.plannedPath) {
    if (interruptNodes.includes(n) && !nodeDone(s, n)) return { node: n, at: (acc / total) * 100 };
    acc += weights[n] ?? 1;
  }
  return undefined;
}

function gateName(node: string): string {
  return node === "approve_plan" ? "Approve the plan" : node === "approve_brainstorm" ? "Answer the brainstorming questions" : "Review before the PR";
}

function LiveLine({ s, live, now }: { s: SessionView; live: Liveness; now: number }) {
  const n = s.currentNode ? s.nodes[s.currentNode] : undefined;
  if (live === "stopped") {
    return (
      <div className="live-line stopped small">
        Agent stopped · last activity {(s.lastActivityAt ?? s.updatedAt ?? "").slice(11, 16) || "unknown"} ·{" "}
        <button type="button" className="link" onClick={() => host().postMessage({ type: "resume", runId: s.runId })}>Resume</button>
      </div>
    );
  }
  return (
    <div className="live-line small">
      <span className="live-dot" aria-hidden="true" />
      Working · {elapsed(n?.startedAt, now)}
    </div>
  );
}

/** While a step runs: what the agent is doing now, first; the next review below, smaller. */
function NowCard({ s, interruptNodes, weights, now, live }: { s: SessionView; interruptNodes: string[]; weights: Record<string, number>; now: number; live: Liveness }) {
  const node = s.currentNode!;
  const actions = recentActions(s, 5);
  const latest = actions[0];
  const c = stepCounters(s);
  const next = nextGate(s, interruptNodes, weights);
  return (
    <section className="card next now-card" aria-label="Now">
      <div className="eyebrow blue">NOW · {label(node).toUpperCase()}{(s.currentAttempt ?? 1) > 1 ? ` · ATTEMPT ${s.currentAttempt}` : ""}</div>
      <LiveLine s={s} live={live} now={now} />
      <div className="now-action">
        {latest ? (
          <>
            <span className="now-text">{latest.text}</span> <span className="dim small">· {ago(latest.at, now)}</span>
          </>
        ) : (
          <span className="muted">Starting {stepGerund(node)}…</span>
        )}
      </div>
      {actions.length > 1 && (
        <ul className="now-list small" aria-label="Recent actions">
          {actions.slice(1).map((a) => (
            <li key={a.seq}><span>{a.text}</span><span className="dim">{ago(a.at, now)}</span></li>
          ))}
        </ul>
      )}
      <div className="now-counters small muted">
        <span><b>{c.files}</b> file{c.files === 1 ? "" : "s"} touched</span>
        <span><b>{c.toolCalls}</b> tool call{c.toolCalls === 1 ? "" : "s"}</span>
        <span><b>{formatTokens(c.outputTokens)}</b> output tokens</span>
      </div>
      {next && (
        <div className="next-later small">
          <span className="amber">Next for you ≈ {Math.round(next.at)} %</span> · {gateName(next.node)}. Approve, or type your answer and press Enter to request changes, or Reject.
        </div>
      )}
      <Usage s={s} />
    </section>
  );
}

function NextForYou({ s, interruptNodes, weights, now, live }: { s: SessionView; interruptNodes: string[]; weights: Record<string, number>; now: number; live: Liveness }) {
  if (s.status === "waiting_human" && s.interrupt) {
    const i = s.interrupt;
    return <GateCard key={`${i.node}#${i.seq}`} s={s} i={i} />;
  }
  if (s.status === "running" && s.currentNode) return <NowCard s={s} interruptNodes={interruptNodes} weights={weights} now={now} live={live} />;

  const next = nextGate(s, interruptNodes, weights);
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
          <div className="eyebrow amber">NEXT FOR YOU · AT ≈ {Math.round(next.at)} %</div>
          <div>{gateName(next.node)}. You will get three choices:</div>
          <div className="choices small">
            <span><b className="green">Approve</b> · {next.node === "approve_pr" ? "open the PR" : "go on as proposed"}</span>
            <span><b className="blue">Request changes</b> · type your answer, Enter sends it back to the agent</span>
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
      <Usage s={s} />
    </section>
  );
}

const LIVE_KEY = "jigworks.liveView";

/** The live view (progress, graph, agent output) can be hidden to leave room for the agent's
 *  questions; the choice is remembered across sessions and reloads. */
function useLiveView(): [boolean, (v: boolean) => void] {
  const [live, setLive] = useState(() => {
    try {
      return localStorage.getItem(LIVE_KEY) !== "hidden";
    } catch {
      return true;
    }
  });
  const set = (v: boolean) => {
    setLive(v);
    try {
      localStorage.setItem(LIVE_KEY, v ? "shown" : "hidden");
    } catch {
      /* no storage: keep it for this view only */
    }
  };
  return [live, set];
}

export function RunView({ state, s, initialTab = "activity" }: { state: HostState; s: SessionView; initialTab?: "activity" | "output" }) {
  const wf = state.workflows.find((w) => w.release === s.release);
  const interruptNodes = wf?.interruptNodes ?? s.plannedPath.filter((n) => n.startsWith("approve_"));
  const weights = weightsOf(state, s);
  const running = state.running.includes(s.runId);
  const [live, setLive] = useLiveView();
  const node = s.interrupt?.node ?? s.currentNode;
  const now = useNow(s.status === "running");
  const alive = livenessState(s.status, state.liveness?.[s.runId]?.alive);
  return (
    <div className="run">
      <div className="run-head">
        <div className="grow">
          <h1 className="h1 small-h1">{s.title}</h1>
          <div className="small muted">
            {s.release} · worktree <span className="mono">{s.branch ?? s.runId}</span> · models from the workflow · started {s.startedAt?.slice(11, 16) ?? "–"}
          </div>
        </div>
        <button type="button" className="ghost" aria-expanded={live} aria-controls="live-view" onClick={() => setLive(!live)}>
          {live ? "Hide live view" : "Show live view"}
        </button>
        <button type="button" className="ghost" onClick={() => host().postMessage({ type: "openDiff", runId: s.runId })}>Open worktree</button>
        {running ? (
          <button type="button" className="ghost" onClick={() => host().postMessage({ type: "stop", runId: s.runId })}>Stop</button>
        ) : s.status === "running" || s.status === "paused_usage_limit" ? (
          <button type="button" className="ghost" onClick={() => host().postMessage({ type: "resume", runId: s.runId })}>Resume</button>
        ) : null}
      </div>
      {live ? (
        <>
          <div id="live-view" className="live-view">
            <ProgressCard s={s} weights={weights} interruptNodes={interruptNodes} />
            <Graph s={s} graph={wf?.graph} interruptNodes={interruptNodes} now={now} live={alive} />
          </div>
          <div className="bottom">
            <Output s={s} initialTab={initialTab} />
            <NextForYou s={s} interruptNodes={interruptNodes} weights={weights} now={now} live={alive} />
          </div>
        </>
      ) : (
        <>
          <button type="button" id="live-view" className="live-strip small" onClick={() => setLive(true)} aria-label="Live view hidden, show it">
            <span className="pct">{pct(s.progress)}</span>
            <span className="muted">{node ? label(node) : s.status}</span>
            <span className="dim">step {Math.min(s.step + (node ? 1 : 0), s.stepsPlanned)} of {s.stepsPlanned}</span>
            {alive === "working" && <span className="muted"><span className="live-dot" aria-hidden="true" />Working · {elapsed(s.currentNode ? s.nodes[s.currentNode]?.startedAt : undefined, now)}</span>}
            {alive === "stopped" && <span className="muted">Agent stopped</span>}
            <span className="push-right dim">Live view hidden · show</span>
          </button>
          <div className="bottom solo">
            <NextForYou s={s} interruptNodes={interruptNodes} weights={weights} now={now} live={alive} />
          </div>
        </>
      )}
    </div>
  );
}
