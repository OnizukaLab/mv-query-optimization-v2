"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import {
  Background,
  Controls,
  Handle,
  Panel,
  Position,
  ReactFlow,
  useReactFlow,
  useStore,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layoutPlan, NODE_HEIGHT, NODE_WIDTH, type PlanNode, type PlanNodeData } from "@/lib/plan";
import {
  CATEGORIES,
  categoryOf,
  categoryStyle,
  resetColors,
  setCategoryColor,
  setColorsEnabled,
  useNodeColors,
} from "@/lib/nodeColors";
import { costChange, shapeKey, type PlanDiff } from "@/lib/planDiff";
import { useDarkMode } from "@/lib/useDarkMode";

type CardData = PlanNodeData & {
  diffStatus?: "same" | "moved" | "changed" | "new";
  diffLabel?: string;
  prevCost?: number;
  selected: boolean;
  /** Set when the node is (or lies inside) a materialized view selection. */
  mv?: MvMark;
  /** Number of workload queries containing this node (MV candidate), when known. */
  sharedBy?: number;
};

/** `root`: the node an MV materializes (or the MV scan in the rewritten plan); `covered`: inside it. */
export interface MvMark {
  kind: "root" | "covered";
  label: string;
}

const BADGE: Record<string, string> = {
  new: "bg-blue-500 text-white",
  moved: "bg-amber-500 text-white",
  changed: "bg-sky-600 text-white",
  replaced: "bg-red-500 text-white",
};

/** How a diff status is worded on the cards, e.g. the original plan calls "new" nodes "replaced". */
export type DiffWording = Partial<Record<"new" | "moved" | "changed", "new" | "moved" | "changed" | "replaced" | null>>;

function PlanNodeCard({ data }: NodeProps<Node<CardData>>) {
  const { plan, costShare, diffStatus, diffLabel, prevCost, selected, mv, sharedBy } = data;
  const { enabled, colors } = useNodeColors();
  const category = categoryOf(plan["Node Type"]);
  const accent = enabled ? categoryStyle(category, colors[category]) : null;
  const target = plan["Relation Name"] ?? plan["Index Name"];
  const change = costChange(prevCost, plan["Total Cost"]);
  const ring = selected
    ? "ring-2 ring-zinc-900 dark:ring-zinc-100"
    : mv?.kind === "root"
      ? "ring-2 ring-violet-500"
      : diffStatus === "new"
      ? "ring-2 ring-blue-500"
      : "";
  return (
    <div
      className={`rounded-lg border border-zinc-300 bg-white px-3 py-2 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900 ${ring} ${
        mv?.kind === "covered" ? "border-dashed !border-violet-400 opacity-60" : ""
      }`}
      style={{
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        ...(accent && {
          borderColor: accent.border,
          borderLeftWidth: 5,
          backgroundColor: accent.background,
        }),
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-1">
        <span className="truncate font-semibold">{plan["Node Type"]}</span>
        {sharedBy !== undefined && sharedBy > 1 && (
          <span
            className="ml-auto rounded bg-zinc-200 px-1 text-[10px] text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200"
            title={`Shared by ${sharedBy} queries`}
          >
            ×{sharedBy}
          </span>
        )}
        {mv?.kind === "root" && (
          <span
            className="ml-auto rounded bg-violet-600 px-1 text-[10px] text-white"
            title="Materialized view selected for this query"
          >
            MV {mv.label}
          </span>
        )}
        {diffLabel && BADGE[diffLabel] && (
          <span className={`${(sharedBy && sharedBy > 1) || mv?.kind === "root" ? "" : "ml-auto "}rounded px-1 text-[10px] ${BADGE[diffLabel]}`}>
            {diffLabel}
          </span>
        )}
      </div>
      <div className="truncate text-zinc-500">{target ?? " "}</div>
      <div className="mt-1 flex justify-between tabular-nums text-zinc-600 dark:text-zinc-400">
        <span>
          cost {plan["Total Cost"].toFixed(0)}
          {change !== null && Math.abs(change) >= 0.01 && (
            <span className={change < 0 ? "text-emerald-600" : "text-red-600"}>
              {" "}
              {change < 0 ? "▼" : "▲"}
              {Math.abs(change * 100).toFixed(0)}%
            </span>
          )}
        </span>
        <span>
          rows {plan["Actual Rows"] !== undefined ? `${plan["Actual Rows"]} / ` : ""}
          {plan["Plan Rows"]}
        </span>
      </div>
      <div className="mt-1 h-1 rounded bg-zinc-200 dark:bg-zinc-800">
        <div className="h-1 rounded bg-orange-500" style={{ width: `${Math.round(costShare * 100)}%` }} />
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { plan: PlanNodeCard };

function ColorPanel({ types }: { types: Set<string> }) {
  const { enabled, colors } = useNodeColors();
  const present = CATEGORIES.filter((c) => types.has(c.key));
  return (
    <Panel position="top-right">
      <div className="rounded-lg border border-zinc-300 bg-white/90 p-2 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900/90">
        <label className="flex items-center gap-1 font-medium">
          <input type="checkbox" checked={enabled} onChange={(e) => setColorsEnabled(e.target.checked)} />
          Color by node type
        </label>
        {enabled && (
          <ul className="mt-1 space-y-1">
            {present.map((c) => (
              <li key={c.key} className="flex items-center gap-2">
                <input
                  type="color"
                  value={colors[c.key]}
                  onChange={(e) => setCategoryColor(c.key, e.target.value)}
                  className="h-4 w-6 cursor-pointer border-0 bg-transparent p-0"
                  aria-label={`${c.label} color`}
                />
                {c.label}
              </li>
            ))}
            <li>
              <button type="button" onClick={resetColors} className="text-zinc-500 underline">
                Reset colors
              </button>
            </li>
          </ul>
        )}
      </div>
    </Panel>
  );
}

function labelFor(status: "same" | "moved" | "changed" | "new" | undefined, wording?: DiffWording): string | undefined {
  if (!status || status === "same") return undefined;
  const w = wording?.[status];
  return w === null ? undefined : (w ?? status);
}

/**
 * `fitView` on <ReactFlow> only fits once, at init. The pane is often still changing size then
 * (editors loading, panels settling), which left the graph scrolled out of view. Re-fit whenever
 * the container is resized, until the user pans or zooms themselves.
 */
function AutoFit({ userMoved }: { userMoved: RefObject<boolean> }) {
  const { fitView } = useReactFlow();
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  useEffect(() => {
    if (userMoved.current || width === 0 || height === 0) return;
    void fitView({ duration: 0 });
  }, [width, height, fitView, userMoved]);
  return null;
}

export interface PlanGraphProps {
  plan: PlanNode;
  diff?: PlanDiff | null;
  selectedId?: string | null;
  /** pre-order node id -> number of queries sharing that node */
  sharedBy?: Map<string, number> | null;
  wording?: DiffWording;
  /** pre-order node id -> MV highlight */
  mvMarks?: Map<string, MvMark> | null;
  onSelect?: (id: string | null, plan: PlanNode | null) => void;
}

type Size = { width: number; height: number };

export default function PlanGraph({ plan, diff, selectedId, sharedBy, wording, mvMarks, onSelect }: PlanGraphProps) {
  const dark = useDarkMode();
  const layout = useMemo(() => layoutPlan(plan), [plan]);

  // React Flow measures each node after it renders and keeps nodes hidden until then. With nodes
  // passed in from outside, those measurements are lost whenever the array is rebuilt (diff and
  // MV marks arrive after mount), and nodes stayed invisible. Keep them here and hand them back.
  const [measured, setMeasured] = useState<Map<string, Size>>(() => new Map());
  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setMeasured((prev) => {
      let next: Map<string, Size> | null = null;
      for (const c of changes) {
        if (c.type !== "dimensions" || !c.dimensions) continue;
        const old = prev.get(c.id);
        if (old && old.width === c.dimensions.width && old.height === c.dimensions.height) continue;
        next ??= new Map(prev);
        next.set(c.id, { width: c.dimensions.width, height: c.dimensions.height });
      }
      return next ?? prev;
    });
  }, []);

  const nodes = useMemo(
    () =>
      layout.nodes.map((n) => ({
        ...n,
        measured: measured.get(n.id),
        data: {
          ...n.data,
          diffStatus: diff?.nodes.get(n.id)?.status,
          diffLabel: labelFor(diff?.nodes.get(n.id)?.status, wording),
          prevCost: diff?.nodes.get(n.id)?.prevCost,
          selected: n.id === selectedId,
          mv: mvMarks?.get(n.id),
          sharedBy: sharedBy?.get(n.id),
        } satisfies CardData,
      })),
    [layout, measured, diff, selectedId, sharedBy, wording, mvMarks],
  );
  // Re-fit the viewport only when the plan's shape changes, not on every cost tweak.
  const key = useMemo(() => shapeKey(plan), [plan]);
  const types = useMemo(() => new Set(layout.nodes.map((n) => categoryOf(n.data.plan["Node Type"]))), [layout]);
  const userMoved = useRef(false);
  useEffect(() => {
    userMoved.current = false; // a different plan shape starts from a fresh fit
  }, [key]);

  return (
    <ReactFlow
      key={key}
      nodes={nodes}
      edges={layout.edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      colorMode={dark ? "dark" : "light"}
      nodesConnectable={false}
      nodesDraggable={false}
      onNodeClick={(_, n) => onSelect?.(n.id, (n.data as CardData).plan)}
      onPaneClick={() => onSelect?.(null, null)}
      fitView
      minZoom={0.1}
      // Only user-initiated moves carry a DOM event; programmatic fitView calls do not.
      onMoveStart={(event) => {
        if (event) userMoved.current = true;
      }}
    >
      <AutoFit userMoved={userMoved} />
      <Background />
      <Controls showInteractive={false} className="plan-controls" />
      <ColorPanel types={types} />
    </ReactFlow>
  );
}
