import type { PlanNode } from "./plan";

export type DiffStatus = "same" | "moved" | "new";

export interface NodeDiff {
  status: DiffStatus;
  /** Total Cost of the matching node in the baseline plan (absent for new nodes). */
  prevCost?: number;
}

export interface PlanDiff {
  /** Keyed by pre-order node index (the same ids layoutPlan assigns). */
  nodes: Map<string, NodeDiff>;
  /** Baseline nodes that have no counterpart in the new plan. */
  removed: PlanNode[];
}

export interface Flat {
  id: string;
  path: string;
  node: PlanNode;
}

export function flattenPlan(root: PlanNode): Flat[] {
  const out: Flat[] = [];
  const visit = (node: PlanNode, path: string) => {
    out.push({ id: String(out.length), path, node });
    node.Plans?.forEach((c, i) => visit(c, `${path}/${i}`));
  };
  visit(root, "");
  return out;
}

/** What identifies "the same operation" across two plans, ignoring costs. */
export function signature(n: PlanNode): string {
  const cond = n["Hash Cond"] ?? n["Merge Cond"] ?? n["Join Filter"] ?? n["Index Cond"] ?? "";
  return [n["Node Type"], n["Relation Name"] ?? "", n.Alias ?? "", n["Index Name"] ?? "", cond].join("|");
}

/**
 * Align two plans. A node matches first by identical tree position + signature, then by signature
 * alone (the operation survived but moved, e.g. after a join reorder). Anything left in `next` is
 * new; anything left in `prev` is removed.
 */
export function diffPlans(prev: PlanNode, next: PlanNode): PlanDiff {
  const a = flattenPlan(prev);
  const b = flattenPlan(next);
  const usedPrev = new Set<string>();
  const nodes = new Map<string, NodeDiff>();

  const prevByPath = new Map(a.map((f) => [f.path, f]));
  for (const f of b) {
    const p = prevByPath.get(f.path);
    if (p && signature(p.node) === signature(f.node)) {
      usedPrev.add(p.id);
      nodes.set(f.id, { status: "same", prevCost: p.node["Total Cost"] });
    }
  }

  const free = new Map<string, Flat[]>();
  for (const p of a) {
    if (usedPrev.has(p.id)) continue;
    const s = signature(p.node);
    free.set(s, [...(free.get(s) ?? []), p]);
  }
  for (const f of b) {
    if (nodes.has(f.id)) continue;
    const p = free.get(signature(f.node))?.shift();
    if (p) {
      usedPrev.add(p.id);
      nodes.set(f.id, { status: "moved", prevCost: p.node["Total Cost"] });
    } else {
      nodes.set(f.id, { status: "new" });
    }
  }

  return { nodes, removed: a.filter((p) => !usedPrev.has(p.id)).map((p) => p.node) };
}

/** Relative cost change, e.g. -0.72 for a 72% reduction; null when not comparable. */
export function costChange(prevCost: number | undefined, cost: number): number | null {
  return prevCost && prevCost > 0 ? (cost - prevCost) / prevCost : null;
}

/** Changes whenever the plan's shape (operations and tree structure) changes, not its numbers. */
export function shapeKey(root: PlanNode): string {
  return flattenPlan(root)
    .map((f) => `${f.path}:${signature(f.node)}`)
    .join(";");
}

/** The node a pre-order id (as assigned by layoutPlan) refers to. */
export function nodeById(root: PlanNode, id: string): PlanNode | null {
  return flattenPlan(root).find((f) => f.id === id)?.node ?? null;
}
