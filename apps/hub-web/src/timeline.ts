// Compress an AuditRecord into the audit-trail lines of the run detail (unit-tested).
import type { AuditRecord, AuditStep } from "@jigworks/contracts";

export type Line = { at: string; parts: Part[] };
export type Part =
  | { t: "text"; v: string }
  | { t: "who"; v: string }
  | { t: "pass"; v: string }
  | { t: "fail"; v: string }
  | { t: "mono"; v: string }
  | { t: "pill"; v: string };

const who = (e: string) => e.split("@")[0];
const INTERRUPTS = new Set(["approve_plan", "approve_pr"]);

function gateSummary(step: AuditStep): Part[] {
  const g = step.gate;
  if (!g) return [{ t: "text", v: "Gate " }, step.status === "succeeded" ? { t: "pass", v: "PASS" } : { t: "fail", v: "FAIL" }];
  const checks = g.checks.map((c) => `${c.name}${c.passed ? "" : `: ${c.summary ?? "failed"}`}`).join(" · ");
  return [{ t: "text", v: "Gate " }, g.passed ? { t: "pass", v: "PASS" } : { t: "fail", v: "FAIL" }, { t: "text", v: ` · ${checks}` }];
}

export function timeline(audit: AuditRecord, interruptNodes: Set<string> = INTERRUPTS): Line[] {
  type Item = { at: string; step?: AuditStep; decision?: AuditRecord["decisions"][number] };
  const items: Item[] = [
    ...audit.steps.filter((s) => !interruptNodes.has(s.node)).map((s) => ({ at: s.finishedAt ?? s.startedAt, step: s })),
    ...audit.decisions.map((d) => ({ at: d.at, decision: d })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const lines: Line[] = [
    {
      at: audit.startedAt,
      parts: [
        { t: "text", v: "Started by " },
        { t: "who", v: who(audit.authorEmail) },
        { t: "text", v: ` · ${audit.release} · ${audit.models.default}` },
      ],
    },
  ];
  let group: AuditStep[] = [];
  const flush = () => {
    if (!group.length) return;
    const commits = group.map((s) => s.commit).filter(Boolean) as string[];
    const parts: Part[] = [{ t: "text", v: group.map((s) => s.node).join(", ") + " " }, { t: "pass", v: "done" }];
    if (commits.length) parts.push({ t: "text", v: " · commits " }, { t: "mono", v: commits.length > 1 ? `${commits[0].slice(0, 7)}…${commits[commits.length - 1].slice(0, 7)}` : commits[0].slice(0, 7) });
    lines.push({ at: group[group.length - 1].finishedAt ?? group[group.length - 1].startedAt, parts });
    group = [];
  };

  for (const it of items) {
    if (it.step) {
      const s = it.step;
      if (s.node === "gate" && s.status !== "running") {
        flush();
        lines.push({ at: it.at, parts: gateSummary(s) });
      } else if (s.status === "succeeded") {
        group.push(s);
      } else if (s.status === "failed") {
        flush();
        lines.push({ at: it.at, parts: [{ t: "text", v: `${s.node} ` }, { t: "fail", v: "FAIL" }, { t: "text", v: " → fix" }] });
      } else if (s.status === "running") {
        flush();
        lines.push({ at: s.startedAt, parts: [{ t: "text", v: "Now: " }, { t: "mono", v: s.node }, { t: "text", v: s.attempt > 1 ? ` running · try ${s.attempt}` : " running" }] });
      }
      continue;
    }
    flush();
    const d = it.decision!;
    const stage = d.stage === "plan" ? "Plan" : "PR";
    if (d.decision === "approve") {
      const parts: Part[] = [{ t: "text", v: `${stage} approved by ` }, { t: "who", v: who(d.approverEmail) }];
      if (d.stage === "pr" && d.approverEmail !== audit.authorEmail) parts.push({ t: "text", v: " " }, { t: "pill", v: "approver ≠ author" });
      if (d.stage === "pr" && audit.prUrl) parts.push({ t: "text", v: " · PR opened" });
      lines.push({ at: d.at, parts });
    } else if (d.decision === "request_changes") {
      lines.push({
        at: d.at,
        parts: [{ t: "who", v: who(d.approverEmail) }, { t: "text", v: " " }, { t: "who", v: "requested changes" }, { t: "text", v: d.comment ? `: "${d.comment}" → fix` : " → fix" }],
      });
    } else {
      lines.push({ at: d.at, parts: [{ t: "text", v: `${stage} ` }, { t: "fail", v: "rejected" }, { t: "text", v: " by " }, { t: "who", v: who(d.approverEmail) }] });
    }
  }
  flush();
  if (audit.status === "waiting_human") {
    lines.push({ at: audit.steps[audit.steps.length - 1]?.startedAt ?? audit.startedAt, parts: [{ t: "text", v: "Waiting for a human review" }] });
  }
  if (audit.status === "paused_usage_limit") {
    lines.push({ at: audit.steps[audit.steps.length - 1]?.startedAt ?? audit.startedAt, parts: [{ t: "fail", v: "Paused" }, { t: "text", v: ": subscription usage limit; resumable" }] });
  }
  return lines;
}
