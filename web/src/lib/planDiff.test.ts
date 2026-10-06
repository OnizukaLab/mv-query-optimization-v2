import { describe, expect, it } from "vitest";
import { costChange, diffPlans, shapeKey } from "./planDiff";
import type { PlanNode } from "./plan";

const n = (type: string, cost: number, extra: Partial<PlanNode> = {}, plans?: PlanNode[]): PlanNode =>
  ({ "Node Type": type, "Total Cost": cost, "Plan Rows": 1, Plans: plans, ...extra }) as PlanNode;

const scan = (rel: string, cost = 10) => n("Seq Scan", cost, { "Relation Name": rel, Alias: rel });

describe("diffPlans", () => {
  it("marks identical plans as same and carries previous cost", () => {
    const p = n("Hash Join", 100, {}, [scan("a"), scan("b")]);
    const d = diffPlans(p, structuredClone(p));
    expect([...d.nodes.values()].every((x) => x.status === "same")).toBe(true);
    expect(d.nodes.get("0")?.prevCost).toBe(100);
    expect(d.removed).toEqual([]);
  });

  it("detects a swapped join order as moved, not new", () => {
    const prev = n("Hash Join", 100, {}, [scan("a"), scan("b")]);
    const next = n("Hash Join", 90, {}, [scan("b"), scan("a")]);
    const d = diffPlans(prev, next);
    expect(d.nodes.get("1")?.status).toBe("moved");
    expect(d.nodes.get("2")?.status).toBe("moved");
    expect(d.removed).toEqual([]);
  });

  it("reports a replaced scan as new and the old one as removed", () => {
    const prev = n("Nested Loop", 100, {}, [scan("a"), scan("big")]);
    const next = n("Nested Loop", 5, {}, [scan("a"), scan("mv_big")]);
    const d = diffPlans(prev, next);
    expect(d.nodes.get("2")).toEqual({ status: "new" });
    expect(d.removed.map((r) => r["Relation Name"])).toEqual(["big"]);
  });
});

describe("helpers", () => {
  it("costChange", () => {
    expect(costChange(100, 28)).toBeCloseTo(-0.72);
    expect(costChange(undefined, 5)).toBeNull();
  });

  it("shapeKey ignores costs but not structure", () => {
    const a = n("Hash Join", 1, {}, [scan("a", 1), scan("b", 1)]);
    const b = n("Hash Join", 999, {}, [scan("a", 500), scan("b", 7)]);
    const c = n("Hash Join", 1, {}, [scan("b"), scan("a")]);
    expect(shapeKey(a)).toBe(shapeKey(b));
    expect(shapeKey(a)).not.toBe(shapeKey(c));
  });
});
