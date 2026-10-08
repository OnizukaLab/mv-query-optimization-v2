import type { PlanNode } from "./plan";

/**
 * same: identical operation at the same position. moved: identical operation elsewhere.
 * changed: same operation on the same table/index, but its join/filter condition differs (e.g. it
 * now references an MV's columns). new: no counterpart in the other plan.
 */
export type DiffStatus = "same" | "moved" | "changed" | "new";

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

/** `signature` without the condition: what a scan or join *is*, regardless of how it is phrased. */
function looseSignature(n: PlanNode): string {
  return [n["Node Type"], n["Relation Name"] ?? "", n.Alias ?? "", n["Index Name"] ?? ""].join("|");
}

/**
 * Align two plans. A node matches first by identical tree position + signature, then by signature
 * alone (the operation survived but moved, e.g. after a join reorder). Leftovers are matched once
 * more ignoring conditions: at the same position, or elsewhere for scans (those name their table or
 * index) -- these are "changed". Anything still left in `next` is new; anything left in `prev` is
 * removed.
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

  // Third pass: same operation, different condition. Joins carry no table name, so they only
  // match at the same tree position; scans can match anywhere.
  const left = a.filter((p) => !usedPrev.has(p.id));
  for (const tier of ["position", "anywhere"] as const) {
    for (const f of b) {
      if (nodes.get(f.id)?.status !== "new") continue;
      const loose = looseSignature(f.node);
      const named = f.node["Relation Name"] || f.node["Index Name"];
      const hit = left.find(
        (p) =>
          !usedPrev.has(p.id) &&
          looseSignature(p.node) === loose &&
          (tier === "position" ? p.path === f.path : !!named),
      );
      if (hit) {
        usedPrev.add(hit.id);
        nodes.set(f.id, { status: "changed", prevCost: hit.node["Total Cost"] });
      }
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

/**
 * Highlight for an MV selection. In the original plan, `ownerOf` maps pre-order ids to candidate
 * node ids: the selected nodes are `root`, everything beneath them `covered`. In the rewritten
 * plan, pass `scanOf` instead: scans of a selected MV (Relation Name = node id) are `root`.
 */
export function mvMarks(
  root: PlanNode,
  selected: string[],
  source: { ownerOf: Map<string, string> } | { scanOf: true },
): Map<string, { kind: "root" | "covered"; label: string }> {
  const marks = new Map<string, { kind: "root" | "covered"; label: string }>();
  const flat = flattenPlan(root);
  for (const f of flat) {
    const label = "scanOf" in source ? f.node["Relation Name"] : source.ownerOf.get(f.id);
    if (!label || !selected.includes(label)) continue;
    marks.set(f.id, { kind: "root", label });
    if ("scanOf" in source) continue;
    for (const d of flat) {
      if (d.path.startsWith(`${f.path}/`) && !marks.has(d.id)) marks.set(d.id, { kind: "covered", label });
    }
  }
  return marks;
}
