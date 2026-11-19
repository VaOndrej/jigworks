import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphJSON } from "@jigworks/contracts";
import { END, START, layout } from "../graphLayout";

export type NodeState = { status: "done" | "running" | "waiting" | "failed" | "approved"; attempt?: number };
type Data = { label: string; kind: string; note?: string; state?: NodeState; selected: boolean };

const W = 220;
const H = 48;

function JigNode({ data }: NodeProps<Node<Data>>) {
  const { kind, label, state, note, selected } = data;
  if (kind === "start" || kind === "end") {
    return (
      <div className="g-terminal">
        <Handle type="target" position={Position.Top} id="t" />
        <Handle type="target" position={Position.Left} id="lt" />
        {label}
        <Handle type="source" position={Position.Bottom} id="b" />
      </div>
    );
  }
  const cls = ["g-node", kind === "interrupt" ? "g-interrupt" : "", state?.status === "running" ? "g-running" : "",
    state?.status === "waiting" ? "g-waiting" : "", selected ? "g-selected" : ""].join(" ");
  const statusText =
    state?.status === "running"
      ? `running${state.attempt && state.attempt > 1 ? ` · try ${state.attempt}` : ""}`
      : state?.status === "waiting"
        ? "waiting for you"
        : state?.status === "approved"
          ? "approved"
          : state?.status === "failed"
            ? "failed"
            : state?.status === "done"
              ? "done"
              : undefined;
  return (
    <div className={cls} style={{ width: kind === "side" ? 200 : W }}>
      <Handle type="target" position={Position.Top} id="t" />
      <Handle type="target" position={Position.Right} id="rt" />
      <Handle type="source" position={Position.Right} id="rs" />
      <Handle type="source" position={Position.Left} id="ls" />
      <Handle type="target" position={Position.Left} id="lt" />
      <div className="g-label">
        <span className="g-name">
          {kind === "interrupt" && (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#854D0E" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="8" r="4" />
              <path d="M4 21c1.5-4 5-6 8-6s6.5 2 8 6" />
            </svg>
          )}
          {label}
        </span>
        {note && !statusText && <span className="g-note">{note}</span>}
      </div>
      {statusText && <span className={`g-status g-status-${state?.status}`}>{statusText}</span>}
      <Handle type="source" position={Position.Bottom} id="b" />
    </div>
  );
}

const nodeTypes = { jig: JigNode };
const NOTES: Record<string, string> = {
  fix: "back to the failing check",
  gate: "tests + invariant property tests",
  review: "independent agent session",
};

export function GraphView({ graph, plannedPath, states, selected, onSelect }: {
  graph: GraphJSON;
  plannedPath?: string[];
  states?: Record<string, NodeState>;
  selected?: string;
  onSelect?: (id: string) => void;
}) {
  const { nodes, edges } = useMemo(() => {
    const placed = layout(graph, plannedPath);
    const kindOf = new Map(graph.nodes.map((n) => [n.id, n.kind]));
    const nodes: Node<Data>[] = placed.nodes.map((p) => {
      const kind = kindOf.get(p.id) ?? "step";
      const terminal = kind === "start" || kind === "end";
      return {
        id: p.id,
        type: "jig",
        position: { x: terminal ? p.x + (W - 80) / 2 : p.x, y: p.y + (terminal ? 10 : 0) },
        data: {
          label: p.id === START ? "START" : p.id === END ? "END" : p.id,
          kind: p.column === "side" && !terminal ? "side" : kind,
          note: NOTES[p.id],
          state: states?.[p.id],
          selected: selected === p.id,
        },
        draggable: false,
        connectable: false,
        selectable: !terminal,
      };
    });
    const colors = { plain: "#9A9DA6", pass: "#0F766E", fail: "#B42318", branch: "#6B6F79" };
    const handles = {
      down: ["b", "t"],
      left: ["ls", "lt"],
      toSide: ["rs", "t"],
      fromSide: ["b", "rt"],
    } as const;
    const edges: Edge[] = placed.edges.map((e, i) => {
      const [sourceHandle, targetHandle] = handles[e.route];
      const color = colors[e.tone];
      return {
        id: `e${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        sourceHandle,
        targetHandle,
        type: e.route === "down" ? "straight" : "smoothstep",
        label:
          kindOf.get(e.source) === "interrupt"
            ? e.tone === "pass"
              ? "approve"
              : e.tone === "fail"
                ? "request changes"
                : e.target === END
                  ? "reject"
                  : e.label
            : e.tone === "pass"
              ? "PASS"
              : e.tone === "fail"
                ? "FAIL"
                : e.label,
        labelStyle: { fontSize: 11, fontWeight: 600, fill: e.tone === "fail" ? "#9B1C1C" : "#0F5F58" },
        labelBgStyle: { fill: "#FFFFFF" },
        style: { stroke: color, strokeWidth: 2, strokeDasharray: e.conditional ? "6 4" : undefined },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
        focusable: false,
      };
    });
    return { nodes, edges };
  }, [graph, plannedPath, states, selected]);

  return (
    <div className="graph-canvas" aria-label="Workflow graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => onSelect?.(n.id)}
        minZoom={0.4}
        maxZoom={1.5}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="#DAD7CF" />
      </ReactFlow>
      <div className="graph-legend">
        <span><i className="l-edge" />add_edge</span>
        <span><i className="l-cond" />add_conditional_edges</span>
        <span><i className="l-int" />interrupt (human)</span>
        <span><i className="l-run" />running now</span>
      </div>
    </div>
  );
}

export const graphHeight = (graph: GraphJSON) => Math.max(420, (graph.nodes.length + 1) * 80 + 40);
export { H as NODE_HEIGHT };
