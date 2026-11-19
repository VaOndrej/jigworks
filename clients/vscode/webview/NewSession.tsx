import { useEffect, useState } from "react";
import type { PriceEntry } from "@jigworks/contracts";
import prices from "../../../packages/contracts/fixtures/prices.json";
import { apiCost } from "../src/shared/cost";
import type { HostState, ToWebview } from "../src/shared/messages";
import type { SessionView } from "../src/shared/session";
import { host } from "./host";
import { label } from "./parts";

/** Typical cost of a finished run of the same release, from the sessions this machine knows. */
function typicalCost(sessions: SessionView[], release: string): string {
  const done = sessions.filter((s) => s.release === release && s.status === "succeeded");
  if (!done.length) return "no finished runs of this release yet";
  const costs = done.map((s) => apiCost(prices as PriceEntry[], s.usageRecords).usd).sort((a, b) => a - b);
  const median = costs[Math.floor(costs.length / 2)];
  return `typical run $${median.toFixed(2)} (median of ${done.length}, API equivalent)`;
}

export function NewSession({ state, sessions, initialPrompt = "", initialAttachments = [] }: { state: HostState; sessions: SessionView[]; initialPrompt?: string; initialAttachments?: string[] }) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [attachments, setAttachments] = useState<string[]>(initialAttachments);
  useEffect(() => {
    const onMessage = (ev: MessageEvent<ToWebview>) => {
      if (ev.data.type === "attached") setAttachments((prev) => [...new Set([...prev, ...(ev.data as { paths: string[] }).paths])]);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);
  const wf = state.workflows.find((w) => w.key === state.selectedWorkflow) ?? state.workflows[0];
  const others = sessions.filter((s) => s.status === "running" || s.status === "waiting_human").length;
  const approvals = wf ? wf.plannedPath.filter((n) => wf.interruptNodes.includes(n)).length : 0;
  const modelNames = wf ? describeModels(wf.models) : "";
  const blocked = state.preflight && !state.preflight.ok;

  return (
    <div className="center-page">
      <div className="new-wrap">
        <div>
          <h1 className="h1">What should the agents work on?</h1>
          <div className="chips">
            <span>Workflow</span>
            {wf ? (
              <span className="chip-wf">{wf.release}{wf.channel ? ` · ${wf.channel}` : wf.source === "workspace" ? " · local" : ""}</span>
            ) : (
              <span className="chip-wf">none</span>
            )}
            <span className="small">pick another one in the sidebar</span>
          </div>
        </div>

        <label htmlFor="task" className="sr-only">Task</label>
        <textarea
          id="task"
          className="task"
          value={prompt}
          placeholder="Describe the change. The first line becomes the session title."
          onChange={(e) => setPrompt(e.target.value)}
        />

        <div className="row-wrap">
          {attachments.map((a) => (
            <button type="button" key={a} className="attachment mono" title="Remove" onClick={() => setAttachments(attachments.filter((x) => x !== a))}>
              {a} ×
            </button>
          ))}
          <button type="button" className="attach" onClick={() => host().postMessage({ type: "attach" })}>+ Attach</button>
          <span className="small muted push-right">Models are set by the workflow release: {modelNames}</span>
        </div>

        {blocked && (
          <div className="preflight" role="alert">
            <b>Cannot start:</b> {state.preflight?.message}
          </div>
        )}

        <div className="row-wrap gap-14">
          <button
            type="button"
            className="primary"
            disabled={!wf || !prompt.trim() || blocked}
            onClick={() => wf && host().postMessage({ type: "start", prompt: prompt.trim(), workflowKey: wf.key, attachments })}
          >
            Start session
          </button>
          <span className="muted">
            Runs in its own git worktree <span className="mono">jigworks/run_…</span>.
            {others > 0 ? ` Your other ${others} session${others === 1 ? "" : "s"} keep running.` : ""}
          </span>
        </div>

        {wf && (
          <div className="card plan-card">
            <div className="eyebrow">WHAT THIS WORKFLOW WILL DO</div>
            <div className="steps mono">
              {wf.plannedPath.map((n, i) => (
                <span key={n} className="step-wrap">
                  <span className={`step${wf.interruptNodes.includes(n) ? " human" : ""}`}>{label(n)}</span>
                  {i < wf.plannedPath.length - 1 && <span className="arrow">→</span>}
                </span>
              ))}
            </div>
            <div className="row-wrap muted small gap-24">
              <span>
                {wf.plannedPath.length} steps · {approvals} approval{approvals === 1 ? "" : "s"} by you · {typicalCost(sessions, wf.release)}
              </span>
              <span>
                Agent may: {wf.allowedTools.join(", ") || "default tools"} · {wf.network ? "network" : "no network"}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function short(model: string): string {
  const m = model.match(/claude-(\w+)-(\d+)(?:-(\d+))?/);
  if (!m) return model;
  const name = m[1][0].toUpperCase() + m[1].slice(1);
  return `${name} ${m[2]}${m[3] && m[3].length <= 2 ? `.${m[3]}` : ""}`;
}

export function describeModels(models: { default: string; nodes?: Record<string, string> }): string {
  const overrides = Object.entries(models.nodes ?? {});
  const groups = new Map<string, string[]>();
  for (const [node, model] of overrides) groups.set(model, [...(groups.get(model) ?? []), node.replace(/_/g, " ")]);
  return [short(models.default), ...[...groups].map(([m, nodes]) => `${nodes.join(" and ")} on ${short(m)}`)].join(", ");
}
