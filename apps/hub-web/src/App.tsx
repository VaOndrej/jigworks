import { useEffect, useState } from "react";
import { api, setUnauthorizedHandler } from "./api";
import { Link, parse, usePath } from "./router";
import { Login } from "./pages/Login";
import { WorkflowsPage } from "./pages/Workflows";
import { EditorPage } from "./pages/Editor";
import { RunsPage } from "./pages/Runs";
import { NonCodingPage } from "./pages/NonCoding";
import { Logo } from "./ui";

type Auth = "checking" | "in" | "out";

export function App() {
  const [auth, setAuth] = useState<Auth>("checking");
  const [running, setRunning] = useState<number>();
  const path = usePath();
  const route = parse(path);

  useEffect(() => {
    setUnauthorizedHandler(() => setAuth("out"));
    api
      .workflows()
      .then(() => setAuth("in"))
      .catch(() => setAuth("out"));
  }, []);

  useEffect(() => {
    if (auth !== "in") return;
    const load = () =>
      api
        .runs({ status: "running" })
        .then((r) => setRunning(r.runs.length))
        .catch(() => {});
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [auth]);

  if (auth === "checking") return <div className="boot" aria-busy="true" />;
  if (auth === "out") return <Login onDone={() => setAuth("in")} />;

  const tab = route.page === "editor" ? "workflows" : route.page;
  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <Logo />
            Jigworks
          </Link>
          <nav className="tabs" aria-label="Main">
            <Link to="/" aria-current={tab === "workflows" ? "page" : undefined}>
              Workflows
            </Link>
            <Link to="/runs" aria-current={tab === "runs" ? "page" : undefined}>
              Runs &amp; analytics
            </Link>
            <Link to="/non-coding-teams" aria-current={tab === "non-coding" ? "page" : undefined}>
              Non-coding teams
            </Link>
          </nav>
          <div className="topbar-right">
            {running !== undefined && (
              <Link to="/runs" className={tab === "runs" ? "running-pill" : "running-plain"}>
                <span className="dot-live" />
                {tab === "runs" ? `${running} session${running === 1 ? "" : "s"} running now` : `${running} running`}
              </Link>
            )}
            <button type="button" className="link-button" onClick={() => api.logout().finally(() => setAuth("out"))}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      {route.page === "workflows" && <WorkflowsPage />}
      {route.page === "editor" && <EditorPage key={route.workflowId} workflowId={route.workflowId} view={route.view} />}
      {route.page === "runs" && <RunsPage runId={route.runId} />}
      {route.page === "non-coding" && <NonCodingPage />}
    </div>
  );
}
