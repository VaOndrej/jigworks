// Layout for a read-only get_graph(): the planned path as one column, other nodes (fix) to the side.
import type { GraphEdge, GraphJSON } from "@jigworks/contracts";

export const START = "__start__";
export const END = "__end__";
export const COL_X = 0;
export const SIDE_X = 300;
export const ROW = 80;

export type Placed = { id: string; x: number; y: number; column: "main" | "side" };
export type Routed = GraphEdge & { route: "down" | "left" | "toSide" | "fromSide"; tone: "plain" | "pass" | "fail" | "branch" };

/** Main column order: plannedPath when given, else a longest-path topological order from START. */
export function mainColumn(graph: GraphJSON, plannedPath?: string[]): string[] {
  const ids = new Set(graph.nodes.map((n) => n.id));
  if (plannedPath?.length && plannedPath.every((n) => ids.has(n))) return [START, ...plannedPath, END].filter((n) => ids.has(n));
  // Longest path over the DAG left after dropping back edges (DFS from START).
  const out = new Map<string, string[]>();
  for (const e of graph.edges) out.set(e.source, [...(out.get(e.source) ?? []), e.target]);
  const order: string[] = [];
  const state = new Map<string, 1 | 2>();
  const visit = (n: string) => {
    if (state.get(n)) return;
    state.set(n, 1);
    for (const m of out.get(n) ?? []) if (state.get(m) !== 1) visit(m);
    state.set(n, 2);
    order.unshift(n);
  };
  visit(START);
  for (const n of graph.nodes) visit(n.id);
  const main = order.filter((n) => n !== END);
  return ids.has(END) ? [...main, END] : main;
}

export function layout(graph: GraphJSON, plannedPath?: string[]): { nodes: Placed[]; edges: Routed[] } {
  const main = mainColumn(graph, plannedPath);
  const row = new Map(main.map((id, i) => [id, i]));
  const placed: Placed[] = main.map((id, i) => ({ id, x: COL_X, y: i * ROW, column: "main" }));
  const side = graph.nodes.filter((n) => !row.has(n.id));
  side.forEach((n, k) => {
    // Halfway between the main nodes it connects to.
    const neighbours = graph.edges
      .filter((e) => e.source === n.id || e.target === n.id)
      .map((e) => row.get(e.source === n.id ? e.target : e.source))
      .filter((r): r is number => r !== undefined);
    const mid = neighbours.length ? (Math.min(...neighbours) + Math.max(...neighbours)) / 2 : main.length + k;
    placed.push({ id: n.id, x: SIDE_X, y: mid * ROW + k * 20, column: "side" });
  });
  const sideIds = new Set(side.map((n) => n.id));
  const edges: Routed[] = graph.edges.map((e) => {
    let route: Routed["route"] = "left";
    if (sideIds.has(e.target)) route = "toSide";
    else if (sideIds.has(e.source)) route = "fromSide";
    else if ((row.get(e.target) ?? 0) === (row.get(e.source) ?? 0) + 1) route = "down";
    let tone: Routed["tone"] = "plain";
    if (e.conditional) tone = sideIds.has(e.target) ? "fail" : route === "down" ? "pass" : "branch";
    return { ...e, route, tone };
  });
  return { nodes: placed, edges };
}
