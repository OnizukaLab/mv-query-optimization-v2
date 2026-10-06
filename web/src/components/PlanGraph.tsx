"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layoutPlan, NODE_HEIGHT, NODE_WIDTH, type PlanNode, type PlanNodeData } from "@/lib/plan";
import { costChange, shapeKey, type PlanDiff } from "@/lib/planDiff";

type CardData = PlanNodeData & {
  diffStatus?: "same" | "moved" | "new";
  diffLabel?: string;
  prevCost?: number;
  selected: boolean;
  /** Number of workload queries containing this node (MV candidate), when known. */
  sharedBy?: number;
};

const BADGE: Record<string, string> = {
  new: "bg-blue-500 text-white",
  moved: "bg-amber-500 text-white",
  replaced: "bg-red-500 text-white",
};

/** How a diff status is worded on the cards, e.g. the original plan calls "new" nodes "replaced". */
export type DiffWording = Partial<Record<"new" | "moved", "new" | "moved" | "replaced" | null>>;

function PlanNodeCard({ data }: NodeProps<Node<CardData>>) {
  const { plan, costShare, diffStatus, diffLabel, prevCost, selected, sharedBy } = data;
  const target = plan["Relation Name"] ?? plan["Index Name"];
  const change = costChange(prevCost, plan["Total Cost"]);
  const ring = selected
    ? "ring-2 ring-zinc-900 dark:ring-zinc-100"
    : diffStatus === "new"
      ? "ring-2 ring-blue-500"
      : "";
  return (
    <div
      className={`rounded-lg border border-zinc-300 bg-white px-3 py-2 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900 ${ring}`}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
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
        {diffLabel && BADGE[diffLabel] && (
          <span className={`${sharedBy && sharedBy > 1 ? "" : "ml-auto "}rounded px-1 text-[10px] ${BADGE[diffLabel]}`}>
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

function labelFor(status: "same" | "moved" | "new" | undefined, wording?: DiffWording): string | undefined {
  if (!status || status === "same") return undefined;
  const w = wording?.[status];
  return w === null ? undefined : (w ?? status);
}

export interface PlanGraphProps {
  plan: PlanNode;
  diff?: PlanDiff | null;
  selectedId?: string | null;
  /** pre-order node id -> number of queries sharing that node */
  sharedBy?: Map<string, number> | null;
  wording?: DiffWording;
  onSelect?: (id: string | null, plan: PlanNode | null) => void;
}

export default function PlanGraph({ plan, diff, selectedId, sharedBy, wording, onSelect }: PlanGraphProps) {
  const layout = useMemo(() => layoutPlan(plan), [plan]);
  const nodes = useMemo(
    () =>
      layout.nodes.map((n) => ({
        ...n,
        data: {
          ...n.data,
          diffStatus: diff?.nodes.get(n.id)?.status,
          diffLabel: labelFor(diff?.nodes.get(n.id)?.status, wording),
          prevCost: diff?.nodes.get(n.id)?.prevCost,
          selected: n.id === selectedId,
          sharedBy: sharedBy?.get(n.id),
        } satisfies CardData,
      })),
    [layout, diff, selectedId, sharedBy, wording],
  );
  // Re-fit the viewport only when the plan's shape changes, not on every cost tweak.
  const key = useMemo(() => shapeKey(plan), [plan]);

  return (
    <ReactFlow
      key={key}
      nodes={nodes}
      edges={layout.edges}
      nodeTypes={nodeTypes}
      nodesConnectable={false}
      nodesDraggable={false}
      onNodeClick={(_, n) => onSelect?.(n.id, (n.data as CardData).plan)}
      onPaneClick={() => onSelect?.(null, null)}
      fitView
      minZoom={0.1}
    >
      <Background />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
