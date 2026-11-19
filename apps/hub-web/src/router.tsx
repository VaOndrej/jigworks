// Minimal History API router: the hub has a handful of routes.
import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent } from "react";

export function navigate(to: string) {
  if (to === window.location.pathname + window.location.search) return;
  window.history.pushState(null, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
}

export function usePath(): string {
  const current = () => window.location.pathname + window.location.search;
  const [path, setPath] = useState(current());
  useEffect(() => {
    const on = () => setPath(current());
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  return path;
}

export type Route =
  | { page: "workflows" }
  | { page: "editor"; workflowId: string; view: "code" | "graph" }
  | { page: "runs"; runId?: string }
  | { page: "non-coding" };

export function parse(path: string): Route {
  const parts = path.split("?")[0].split("/").filter(Boolean);
  if (parts[0] === "workflows" && parts[1]) {
    return { page: "editor", workflowId: parts[1], view: parts[2] === "graph" ? "graph" : "code" };
  }
  if (parts[0] === "runs") return { page: "runs", runId: parts[1] };
  if (parts[0] === "non-coding-teams") return { page: "non-coding" };
  return { page: "workflows" };
}

export function Link({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <a
      href={to}
      onClick={(e: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(e);
        if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(to);
      }}
      {...rest}
    />
  );
}
