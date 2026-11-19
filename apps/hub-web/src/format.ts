// Formatting and small pure helpers (unit-tested in format.test.ts).
import type { HumanDelta, RunSummary, WorkflowManifest } from "@jigworks/contracts";

export const usd = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "—" : `$${v.toFixed(digits)}`;

export const pct = (ratio: number | null | undefined) =>
  ratio === null || ratio === undefined ? "—" : `${Math.round(ratio * 100)} %`;

export function duration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return "—";
  if (sec < 90) return `${Math.round(sec)} s`;
  const min = sec / 60;
  if (min < 90) return `${Math.round(min)} min`;
  return `${(min / 60).toFixed(1)} h`;
}

export function tokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

/** "alice@example.com" → "alice" (the hub shows people by the local part of git user.email). */
export const who = (email: string | null | undefined) => (email ? email.split("@")[0] : "—");

export function ago(iso: string, now = Date.now()): string {
  const sec = (now - Date.parse(iso)) / 1000;
  if (sec < 90) return "just now";
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400 * 1.5) return `${Math.round(sec / 3600)} h ago`;
  return `${Math.round(sec / 86400)} days ago`;
}

export function shortDay(iso: string, now = new Date()): string {
  const d = new Date(iso);
  const days = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (d.toDateString() === now.toDateString()) return "today";
  if (days < 7) return d.toLocaleDateString("en-GB", { weekday: "short" });
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

export type Segment = { kind: "agent" | "review" | "gate"; weight: number; node: string };

/** The step shape of a release: planned path nodes as agent / human review / gate segments. */
export function shape(manifest: WorkflowManifest | undefined): Segment[] {
  if (!manifest?.plannedPath) return [];
  const interrupts = new Set(manifest.interruptNodes ?? []);
  return manifest.plannedPath.map((node) => ({
    node,
    kind: interrupts.has(node) ? "review" : node === "gate" ? "gate" : "agent",
    weight: Math.max(manifest.weights?.[node] ?? 5, 2),
  }));
}

export function shapeLabel(segments: Segment[]): string {
  const reviews = segments.filter((s) => s.kind === "review").length;
  const gate = segments.some((s) => s.kind === "gate");
  return [`${segments.length} steps`, reviews ? `${reviews} review${reviews > 1 ? "s" : ""}` : null, gate ? "gate" : null]
    .filter(Boolean)
    .join(" · ");
}

export const LIVE_STATUSES = new Set(["running", "waiting_human", "paused_usage_limit"]);

export function statusLabel(run: RunSummary): { text: string; tone: "blue" | "green" | "red" | "amber" | "grey" } {
  switch (run.status) {
    case "running":
      return { text: `Running ${Math.round(run.progress ?? 0)} %`, tone: "blue" };
    case "waiting_human":
      return { text: "Review required", tone: "amber" };
    case "paused_usage_limit":
      return { text: "Paused · usage limit", tone: "amber" };
    case "succeeded":
      return { text: run.prUrl ? "PR opened" : "Succeeded", tone: "green" };
    case "rejected":
      return { text: (run.progress ?? 0) < 20 ? "Rejected at plan" : "Rejected", tone: "red" };
    case "failed":
      return { text: "Failed", tone: "red" };
    default:
      return { text: "Cancelled", tone: "grey" };
  }
}

export function deltaLabel(d: HumanDelta | undefined): string {
  if (!d) return "—";
  switch (d.outcome) {
    case "worked_first_time":
      return "worked first time";
    case "corrected_by_prompt":
      return `${d.followUpPrompts} prompt${d.followUpPrompts === 1 ? "" : "s"}`;
    case "edited_by_hand":
      return `${d.followUpPrompts ? `${d.followUpPrompts} prompt · ` : ""}hand +${d.linesAdded} −${d.linesRemoved}`;
    default:
      return "rejected";
  }
}

/** Share of sample sessions that worked first time (PLANNED metric). */
export function workedFirstTime(deltas: HumanDelta[]): number | null {
  if (!deltas.length) return null;
  return deltas.filter((d) => d.outcome === "worked_first_time").length / deltas.length;
}

/** Read the version from workflow.toml text without a TOML parser (top-level `version = "x"`). */
export function tomlVersion(text: string | undefined): string | null {
  const m = text?.match(/^version\s*=\s*"([^"]+)"/m);
  return m ? m[1] : null;
}

export function bumpMinor(version: string): string {
  const [maj, min] = version.split(".").map((x) => parseInt(x, 10));
  return Number.isFinite(maj) && Number.isFinite(min) ? `${maj}.${min + 1}.0` : version;
}
