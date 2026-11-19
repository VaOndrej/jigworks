// "Where in the graph": the planned path in one row, off-path steps (fix) below it, the current
// node highlighted with a NOW marker (design.md §7). Read-only, from the GraphJSON the runner
// returns for the release; falls back to the planned path when no graph is known.
import type { GraphJSON } from "@jigworks/contracts";
import type { SessionView } from "../src/shared/session";
import { label } from "./parts";

const W = 96;
const H = 44;
const GAP = 18;
const TOP = 40;
const BELOW = 136;

interface Placed {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  planned: boolean;
  interrupt: boolean;
}

export function layout(graph: GraphJSON | undefined, plannedPath: string[], interruptNodes: string[]) {
  const planned = plannedPath.length
    ? plannedPath
    : (graph?.nodes ?? []).filter((n) => n.kind === "step" || n.kind === "interrupt").map((n) => n.id);
  const interrupts = new Set([...interruptNodes, ...(graph?.nodes ?? []).filter((n) => n.kind === "interrupt").map((n) => n.id)]);
  const placed = new Map<string, Placed>();
  planned.forEach((id, i) => placed.set(id, { id, x: i * (W + GAP), y: TOP, w: W, h: H, planned: true, interrupt: interrupts.has(id) }));
  const extra = (graph?.nodes ?? []).filter((n) => n.kind === "step" && !placed.has(n.id)).map((n) => n.id);
  if (!graph && !extra.includes("fix") && planned.includes("review")) extra.push("fix");
  const edges = graph?.edges ?? [];
  extra.forEach((id) => {
    const neighbours = edges
      .filter((e) => e.source === id || e.target === id)
      .map((e) => (e.source === id ? e.target : e.source))
      .filter((n) => placed.get(n)?.planned && !interrupts.has(n));
    const xs = (neighbours.length ? neighbours : ["review", "gate"]).map((n) => placed.get(n)?.x).filter((x): x is number => x !== undefined);
    const mid = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 + W / 2 : 0;
    placed.set(id, { id, x: mid - 80, y: BELOW, w: 160, h: 40, planned: false, interrupt: false });
  });
  const width = Math.max(...[...placed.values()].map((p) => p.x + p.w), 0);
  return { placed, planned, width, edges };
}

function nodeState(s: SessionView, id: string, interrupt: boolean) {
  const n = s.nodes[id];
  const current = s.currentNode === id && s.status !== "waiting_human";
  const waiting = s.interrupt?.node === id || (n?.status === "waiting_human" && s.status === "waiting_human");
  if (waiting) return { cls: "needs", sub: "needs you" };
  if (current) return { cls: "now", sub: `running${(s.currentAttempt ?? 1) > 1 ? ` · try ${s.currentAttempt}` : ""}` };
  if (!n || n.status === "pending") return { cls: interrupt ? "todo human" : "todo", sub: "" };
  if (n.status === "succeeded") {
    if (interrupt && n.approvedBy) return { cls: "done", sub: `✓ ${n.approvedBy.split("@")[0]}, ${n.at.slice(11, 16)}` };
    return { cls: "done", sub: id === "fix" ? `✓ ${s.fixLoops} loop${s.fixLoops === 1 ? "" : "s"}` : "✓ done" };
  }
  if (n.status === "failed") return { cls: "failed", sub: interrupt ? "✗ rejected" : `✗ failed${n.attempt > 1 ? ` · try ${n.attempt}` : ""}` };
  if (n.status === "cancelled") return { cls: "todo", sub: interrupt ? "changes requested" : "restarted" };
  return { cls: "todo", sub: n.status };
}

export function Graph({ s, graph, interruptNodes }: { s: SessionView; graph?: GraphJSON; interruptNodes: string[] }) {
  const { placed, planned, width } = layout(graph, s.plannedPath, interruptNodes);
  const nowId = s.status === "waiting_human" ? s.interrupt?.node : s.currentNode;
  const now = nowId ? placed.get(nowId) : undefined;
  const fix = placed.get("fix");
  const height = fix ? BELOW + 44 : TOP + H + 20;
  const doneIdx = planned.reduce((acc, id, i) => (s.nodes[id]?.status === "succeeded" ? i : acc), -1);

  return (
    <section className="card graph-card" aria-label="Where in the graph">
      <div className="graph-legend">
        <span className="eyebrow">WHERE IN THE GRAPH</span>
        <span className="legend"><span className="sw sw-green" />done / approved</span>
        <span className="legend"><span className="sw sw-blue" />now</span>
        <span className="legend"><span className="sw sw-amber" />needs you</span>
      </div>
      <div className="graph" style={{ width, height }}>
        <svg className="edges" width={width} height={height} aria-hidden="true">
          {planned.slice(0, -1).map((id, i) => {
            const a = placed.get(id)!;
            const done = i < doneIdx || (i === doneIdx && s.nodes[planned[i + 1]] !== undefined);
            return <line key={id} x1={a.x + a.w} y1={TOP + H / 2} x2={a.x + a.w + GAP} y2={TOP + H / 2} className={done ? "edge done" : "edge"} />;
          })}
          {fix &&
            ["review", "gate"].map((id) => {
              const p = placed.get(id);
              if (!p) return null;
              const x = p.x + p.w / 2;
              const failed = (s.nodes[id]?.attempt ?? 0) > 1 || s.nodes[id]?.status === "failed";
              return (
                <g key={id}>
                  <line x1={x} y1={TOP + H} x2={x} y2={BELOW} className={failed ? "edge done" : "edge"} />
                  <text x={x + (id === "review" ? -36 : 6)} y={TOP + H + 30} className={failed ? "fail-label hot" : "fail-label"}>FAIL</text>
                </g>
              );
            })}
        </svg>
        {now && (
          <>
            <div className={`now-pill${s.status === "waiting_human" ? " amber" : ""}`} style={{ left: now.x + now.w / 2 - 34, top: now.y - 38 }}>{s.status === "waiting_human" ? "YOU" : "NOW"}</div>
            <div className={`now-arrow${s.status === "waiting_human" ? " amber" : ""}`} style={{ left: now.x + now.w / 2 - 6, top: now.y - 16 }} />
          </>
        )}
        {[...placed.values()].map((p) => {
          const st = nodeState(s, p.id, p.interrupt);
          return (
            <div
              key={p.id}
              className={`gnode ${st.cls}`}
              data-node={p.id}
              style={{ left: p.x, top: p.y, width: p.w, height: p.h }}
            >
              <span className="mono">{p.id === "fix" ? "fix" : label(p.id)}</span>
              {st.sub && <span className="gsub">{st.sub}{p.id === "fix" && s.fixLoops ? " · max 3" : ""}</span>}
            </div>
          );
        })}
      </div>
    </section>
  );
}
