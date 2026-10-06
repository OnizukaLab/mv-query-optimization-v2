import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

/** Subset of PostgreSQL's EXPLAIN (FORMAT JSON) plan node. */
export interface PlanNode {
  "Node Type": string;
  "Relation Name"?: string;
  Alias?: string;
  "Index Name"?: string;
  "Total Cost": number;
  "Plan Rows": number;
  "Actual Rows"?: number;
  "Actual Total Time"?: number;
  "Actual Loops"?: number;
  Plans?: PlanNode[];
  [key: string]: unknown;
}

export interface PlanNodeData extends Record<string, unknown> {
  plan: PlanNode;
  /** This node's share of the root's total cost, 0..1. */
  costShare: number;
}

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 88;

/** Convert a plan tree into positioned React Flow nodes and edges (top-down). */
export function layoutPlan(root: PlanNode): { nodes: Node<PlanNodeData>[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 24, ranksep: 56 });
  g.setDefaultEdgeLabel(() => ({}));

  const nodes: Node<PlanNodeData>[] = [];
  const edges: Edge[] = [];
  const rootCost = root["Total Cost"] || 1;
  let nextId = 0;

  const visit = (plan: PlanNode, parentId?: string) => {
    const id = String(nextId++);
    g.setNode(id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    nodes.push({
      id,
      type: "plan",
      position: { x: 0, y: 0 },
      data: { plan, costShare: Math.min(plan["Total Cost"] / rootCost, 1) },
    });
    if (parentId !== undefined) {
      g.setEdge(parentId, id);
      edges.push({ id: `${parentId}-${id}`, source: parentId, target: id });
    }
    plan.Plans?.forEach((child) => visit(child, id));
  };
  visit(root);

  dagre.layout(g);
  for (const n of nodes) {
    const p = g.node(n.id);
    n.position = { x: p.x - NODE_WIDTH / 2, y: p.y - NODE_HEIGHT / 2 };
  }
  return { nodes, edges };
}
