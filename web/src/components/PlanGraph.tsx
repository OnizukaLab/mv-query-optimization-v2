"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type NodeProps,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layoutPlan, NODE_HEIGHT, NODE_WIDTH, type PlanNode, type PlanNodeData } from "@/lib/plan";

function PlanNodeCard({ data }: NodeProps<Node<PlanNodeData>>) {
  const { plan, costShare } = data;
  const target = plan["Relation Name"] ?? plan["Index Name"];
  const heat = Math.round(costShare * 100);
  return (
    <div
      className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="truncate font-semibold">{plan["Node Type"]}</div>
      <div className="truncate text-zinc-500">{target ?? " "}</div>
      <div className="mt-1 flex justify-between tabular-nums text-zinc-600 dark:text-zinc-400">
        <span>cost {plan["Total Cost"].toFixed(0)}</span>
        <span>
          rows {plan["Actual Rows"] !== undefined ? `${plan["Actual Rows"]} / ` : ""}
          {plan["Plan Rows"]}
        </span>
      </div>
      <div className="mt-1 h-1 rounded bg-zinc-200 dark:bg-zinc-800">
        <div className="h-1 rounded bg-orange-500" style={{ width: `${heat}%` }} />
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { plan: PlanNodeCard };

export default function PlanGraph({ plan }: { plan: PlanNode }) {
  const { nodes, edges } = useMemo(() => layoutPlan(plan), [plan]);
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      nodesConnectable={false}
      fitView
      minZoom={0.1}
    >
      <Background />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
