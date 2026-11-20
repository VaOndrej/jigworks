import { createRoot } from "react-dom/client";
import type { ViewKind } from "../src/shared/messages";
import { useHostState, useSessions } from "./host";
import { NewSession } from "./NewSession";
import { RunView } from "./RunView";
import { Sidebar } from "./Sidebar";
import "./styles.css";

export function App({ view, runId }: { view: ViewKind; runId?: string | null }) {
  const state = useHostState(view, runId);
  const sessions = useSessions(state);
  if (view === "sidebar") return <Sidebar state={state} sessions={sessions} activeRun={state.activeRun} />;
  if (view === "new") return <NewSession state={state} sessions={sessions} />;
  const s = sessions.find((x) => x.runId === runId);
  if (!s) return <div className="center-page muted">Loading session {runId}…</div>;
  return <RunView state={state} s={s} />;
}

const boot = window.__JIGWORKS_BOOT__;
const root = document.getElementById("root");
if (boot && root) createRoot(root).render(<App view={boot.view} runId={boot.runId} />);
