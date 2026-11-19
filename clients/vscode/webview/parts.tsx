import type { SessionView } from "../src/shared/session";

export function ReviewBadge() {
  return (
    <span className="badge-review">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="2" />
      </svg>
      Review
    </span>
  );
}

export function pct(n: number): string {
  return `${Math.round(n)} %`;
}

/** Review badge instead of % while a human is needed (design.md §7). */
export function ProgressLabel({ s }: { s: SessionView }) {
  if (s.status === "waiting_human") return <ReviewBadge />;
  if (s.status === "paused_usage_limit") return <span className="tag tag-amber">paused</span>;
  if (s.status === "succeeded") return <span className="tag tag-green">done</span>;
  if (s.status === "failed") return <span className="tag tag-red">failed</span>;
  if (s.status === "rejected") return <span className="tag tag-red">rejected</span>;
  return <span className="pct">{pct(s.progress)}</span>;
}

export function sessionSubline(s: SessionView): string {
  const node = s.interrupt?.node ?? s.currentNode;
  if (s.status === "waiting_human") return `${s.workflowId} · waiting for you`;
  if (s.status === "paused_usage_limit") return `${s.workflowId} · usage limit, resumes ${s.usageLimit?.resetsAt?.slice(11, 16) ?? "later"}`;
  if (node) return `${s.workflowId} · ${node}`;
  return `${s.workflowId} · ${s.status}`;
}

export function barClass(s: SessionView): string {
  if (s.status === "waiting_human" || s.status === "paused_usage_limit") return "bar-fill amber";
  if (s.status === "succeeded") return "bar-fill green";
  if (s.status === "failed" || s.status === "rejected") return "bar-fill red";
  return "bar-fill";
}

export function label(node: string): string {
  return node.replace(/_/g, " ").replace(/^approve pr$/, "approve PR");
}
