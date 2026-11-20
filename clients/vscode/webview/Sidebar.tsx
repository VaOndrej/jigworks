import type { HostState } from "../src/shared/messages";
import type { SessionView } from "../src/shared/session";
import { host } from "./host";
import { barClass, ProgressLabel, sessionSubline } from "./parts";

export function Sidebar({ state, sessions, activeRun }: { state: HostState; sessions: SessionView[]; activeRun?: string | null }) {
  const open = sessions.filter((s) => !["succeeded", "failed", "rejected", "cancelled"].includes(s.status));
  const running = sessions.filter((s) => s.status === "running").length;
  const waiting = sessions.filter((s) => s.status === "waiting_human").length;
  return (
    <aside className="sidebar" aria-label="Jigworks">
      {state.preflight && !state.preflight.ok && (
        <div className="preflight" role="alert">
          <b>Claude Code is not ready.</b> {state.preflight.message}
        </div>
      )}
      <div className="section-head">
        <span>WORKFLOWS</span>
        <span className="head-actions">
          <button type="button" className="link" onClick={() => host().postMessage({ type: "sync" })}>Sync</button>
          <button type="button" className="link" onClick={() => host().postMessage({ type: "importWorkflow" })}>Import</button>
        </span>
      </div>
      <HubLine hub={state.hub} />
      <div className="wf-list">
        {state.workflows.length === 0 && <div className="muted small pad">No workflows yet. Connect a hub and sync, or import a .zip.</div>}
        {state.workflows.map((w) => {
          const selected = w.key === state.selectedWorkflow;
          const tag = [w.version, w.channel && w.channel !== "stable" ? w.channel : "", w.source === "workspace" ? "local" : "", selected ? "selected" : ""]
            .filter(Boolean)
            .join(" · ");
          return (
            <button
              type="button"
              key={w.key}
              className={`wf${selected ? " selected" : ""}`}
              onClick={() => host().postMessage({ type: "selectWorkflow", key: w.key })}
              title={`${w.release} · ${w.digest}`}
            >
              <span>{w.name}</span>
              <span className="wf-tag">{tag}</span>
            </button>
          );
        })}
      </div>

      <div className="section-head border-top">
        <span>SESSIONS</span>
        <span className="accent-blue">
          {running > 0 ? `${running} running` : `${open.length} open`}
          {waiting > 0 ? ` · ${waiting} for you` : ""}
        </span>
      </div>
      <div className="session-list">
        {sessions.length === 0 && <div className="muted small pad">No sessions yet.</div>}
        {sessions.map((s) => (
          <button
            type="button"
            key={s.runId}
            className={`session${s.runId === activeRun ? " active" : ""}${s.status === "waiting_human" ? " waiting" : ""}`}
            onClick={() => host().postMessage({ type: "openSession", runId: s.runId })}
          >
            <div className="row">
              <span className="session-title">{s.title}</span>
              <ProgressLabel s={s} />
            </div>
            <div className={`subline${s.status === "waiting_human" ? " amber" : ""}`}>{sessionSubline(s)}</div>
            <div className="bar">
              <div className={barClass(s)} style={{ width: `${Math.max(2, s.progress)}%` }} />
            </div>
          </button>
        ))}
      </div>
      <div className="sidebar-foot">
        <button type="button" className="new-session" onClick={() => host().postMessage({ type: "newSession" })}>+ New session</button>
      </div>
    </aside>
  );
}

function HubLine({ hub }: { hub: HostState["hub"] }) {
  const settings = () => host().postMessage({ type: "hubSettings" });
  if (!hub || hub.state === "not_configured" || !hub.hasPassword) {
    return (
      <div className="hub-line">
        <span className="hub-dot off" />
        <span className="muted">{hub?.url ? `Hub ${hostOf(hub.url)}: no password yet.` : "Not connected to a hub."}</span>
        <button type="button" className="link accent" onClick={settings}>Connect</button>
      </div>
    );
  }
  const label = hub.state === "connected" ? "connected" : hub.state === "error" ? "sync failed" : "not synced yet";
  return (
    <div className={`hub-line${hub.state === "error" ? " error" : ""}`} title={hub.url}>
      <span className={`hub-dot ${hub.state}`} />
      <span className="hub-text">
        Hub {hostOf(hub.url)} · {label}
        {hub.message && <span className="hub-msg">{hub.message}</span>}
      </span>
      <button type="button" className="link" onClick={settings} aria-label="Hub settings">Settings</button>
    </div>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
