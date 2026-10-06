import type { PlanNode } from "./plan";
import { flattenPlan, shapeKey } from "./planDiff";

/**
 * Transfer MV-candidate ids from the stored (annotated) plan onto a live plan.
 *
 * Only valid when both plans have the identical shape *and* the SQL is unmodified; returns
 * pre-order index -> node_id, or null when the plans differ.
 */
export function mapNodeIds(live: PlanNode, snapshot: PlanNode): Map<string, string> | null {
  if (shapeKey(live) !== shapeKey(snapshot)) return null;
  const ids = new Map<string, string>();
  flattenPlan(snapshot).forEach((f) => {
    const nodeId = f.node["node_id"];
    if (typeof nodeId === "string") ids.set(f.id, nodeId);
  });
  return ids;
}
