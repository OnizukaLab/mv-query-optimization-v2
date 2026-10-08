import type { PlanNode } from "./plan";

/**
 * Did rewriting a query onto MVs change its join order?
 *
 * Same definition as scripts/check_join_order_change.py: a plan's join order is the relative order
 * in which each base table is first scanned. Comparing operator types or plan shape is not enough
 * -- it misses reorderings, and flags every rewrite (it always swaps tables for MV scans). MV
 * names (leaf_X / non_leaf_X) are first replaced by the base tables they contain.
 */
export interface JoinOrder {
  changed: boolean;
  /** Tables present in both plans, in the order the original plan scans them. */
  original: string[];
  /** The same tables in the order the rewritten plan scans them. */
  rewritten: string[];
}

/** Relation names of the scan leaves (nodes without children), in pre-order. */
export function leafScanOrder(node: PlanNode, out: string[] = []): string[] {
  if (!node.Plans) {
    const rel = node["Relation Name"];
    if (rel) out.push(rel);
  } else {
    node.Plans.forEach((c) => leafScanOrder(c, out));
  }
  return out;
}

/**
 * @param baseTables MV node id -> the real tables inside it (names not listed count as tables).
 */
export function joinOrder(original: PlanNode, rewritten: PlanNode, baseTables: Record<string, string[]>): JoinOrder {
  const origPos = new Map<string, number>();
  leafScanOrder(original).forEach((name, i) => {
    if (!origPos.has(name)) origPos.set(name, i);
  });

  const rewrittenPos = new Map<string, number>();
  leafScanOrder(rewritten).forEach((name, i) => {
    for (const table of baseTables[name] ?? [name]) {
      if (!rewrittenPos.has(table)) rewrittenPos.set(table, i);
    }
  });

  const common = [...origPos.keys()].filter((t) => rewrittenPos.has(t));
  const o = (t: string) => origPos.get(t)!;
  const r = (t: string) => rewrittenPos.get(t)!;
  const originalOrder = [...common].sort((a, b) => o(a) - o(b));
  // Tables inside one MV share a position; the original order breaks the tie.
  const rewrittenOrder = [...common].sort((a, b) => r(a) - r(b) || o(a) - o(b));
  return {
    changed: originalOrder.join("|") !== rewrittenOrder.join("|"),
    original: originalOrder,
    rewritten: rewrittenOrder,
  };
}
