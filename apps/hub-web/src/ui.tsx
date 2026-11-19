// Small shared UI pieces that follow docs/mockups/jigworks-ui.html.
import type { ReactNode } from "react";
import type { Segment } from "./format";

export function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#F59E5B" strokeWidth="2" aria-hidden="true">
      <path d="M4 4h10v6H8v10H4z" />
      <path d="M14 14h6v6h-6z" />
    </svg>
  );
}

export function Planned({ title = "Planned: shows recorded sample data, not computed yet" }: { title?: string }) {
  return (
    <span className="planned" title={title}>
      PLANNED
    </span>
  );
}

export function Pill({ tone, children }: { tone: "green" | "orange" | "grey" | "blue" | "red" | "amber"; children: ReactNode }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function ReviewBadge() {
  return (
    <span className="review-badge">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="2" />
      </svg>
      Review required
    </span>
  );
}

export function ShapeBar({ segments }: { segments: Segment[] }) {
  const reviews = segments.filter((s) => s.kind === "review").length;
  const gates = segments.filter((s) => s.kind === "gate").length;
  return (
    <div
      className="shape"
      role="img"
      aria-label={`Agent steps, ${reviews} human review${reviews === 1 ? "" : "s"}, ${gates} gate${gates === 1 ? "" : "s"}`}
    >
      {segments.map((s) => (
        <span key={s.node} className={`seg seg-${s.kind}`} style={{ flex: s.weight }} title={s.node} />
      ))}
    </div>
  );
}

export function Progress({ value, tone = "blue" }: { value: number; tone?: "blue" | "amber" }) {
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`progress-fill progress-${tone}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

export function Stat({ label, value, note, noteTone, valueTone, planned }: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  noteTone?: "good" | "muted";
  valueTone?: "amber";
  planned?: boolean;
}) {
  return (
    <div className="stat">
      <div className="stat-label">
        {label} {planned && <Planned />}
      </div>
      <div className="stat-row">
        <span className={`stat-value ${valueTone === "amber" ? "amber" : ""}`}>{value}</span>
        {note && <span className={`stat-note ${noteTone === "good" ? "good" : ""}`}>{note}</span>}
      </div>
    </div>
  );
}

export function ErrorNote({ error }: { error: Error | undefined }) {
  if (!error) return null;
  return <div className="error-note" role="alert">{error.message}</div>;
}
