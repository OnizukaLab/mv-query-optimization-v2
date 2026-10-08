import { describe, expect, it } from "vitest";
import { mapNodeIds } from "./nodeIds";
import { costChange, diffPlans, mvMarks, shapeKey } from "./planDiff";
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

describe("mapNodeIds", () => {
  const live = n("Hash Join", 100, {}, [scan("a"), scan("b")]);
  const snap = n("Hash Join", 1, { node_id: "non_leaf_1" }, [
    scan("a", 1),
    n("Seq Scan", 1, { "Relation Name": "b", Alias: "b", node_id: "leaf_2" }),
  ]);
  (snap.Plans![0] as PlanNode).node_id = "leaf_1";

  it("transfers ids by pre-order position when shapes match", () => {
    const m = mapNodeIds(live, snap)!;
    expect([...m.entries()]).toEqual([["0", "non_leaf_1"], ["1", "leaf_1"], ["2", "leaf_2"]]);
  });

  it("returns null when the shapes differ", () => {
    expect(mapNodeIds(n("Nested Loop", 1, {}, [scan("a"), scan("b")]), snap)).toBeNull();
  });
});

describe("mvMarks", () => {
  const plan = n("Hash Join", 100, {}, [n("Nested Loop", 50, {}, [scan("a"), scan("b")]), scan("c")]);
  // ids: 0 Hash Join, 1 Nested Loop, 2 a, 3 b, 4 c

  it("marks the selected node as root and everything beneath it as covered", () => {
    const marks = mvMarks(plan, ["non_leaf_1"], { ownerOf: new Map([["1", "non_leaf_1"], ["4", "leaf_3"]]) });
    expect(marks.get("1")).toEqual({ kind: "root", label: "non_leaf_1" });
    expect(marks.get("2")?.kind).toBe("covered");
    expect(marks.get("3")?.kind).toBe("covered");
    expect(marks.has("0")).toBe(false);
    expect(marks.has("4")).toBe(false);
  });

  it("marks scans of the selected MV in a rewritten plan", () => {
    const rewritten = n("Hash Join", 10, {}, [scan("non_leaf_1"), scan("c")]);
    const marks = mvMarks(rewritten, ["non_leaf_1"], { scanOf: true });
    expect([...marks.keys()]).toEqual(["1"]);
  });
});

describe("diffPlans: changed", () => {
  const idxScan = (cond: string) =>
    n("Index Scan", 5, { "Relation Name": "title", Alias: "t", "Index Name": "title_pkey", "Index Cond": cond });

  it("treats the same scan with a different condition as changed, not new", () => {
    const prev = n("Nested Loop", 100, {}, [scan("a"), idxScan("(id = mi.movie_id)")]);
    const next = n("Nested Loop", 40, {}, [scan("a"), idxScan("(id = mv.movie_id)")]);
    const d = diffPlans(prev, next);
    expect(d.nodes.get("2")?.status).toBe("changed");
    expect(d.nodes.get("2")?.prevCost).toBe(5);
    expect(d.removed).toEqual([]);
  });

  it("matches a join with a rewritten condition only at the same position", () => {
    const join = (cond: string, kids: PlanNode[]) => n("Hash Join", 50, { "Hash Cond": cond }, kids);
    const prev = n("Aggregate", 60, {}, [join("(a.id = b.id)", [scan("a"), scan("b")])]);
    const next = n("Aggregate", 20, {}, [join("(mv.id = b.id)", [scan("mv"), scan("b")])]);
    const d = diffPlans(prev, next);
    expect(d.nodes.get("1")?.status).toBe("changed");
    expect(d.nodes.get("2")?.status).toBe("new"); // scan of a different table is genuinely new
    expect(d.removed.map((x) => x["Relation Name"])).toEqual(["a"]);
  });

  it("does not match a join elsewhere in the tree", () => {
    const join = (cond: string, kids: PlanNode[]) => n("Hash Join", 50, { "Hash Cond": cond }, kids);
    const prev = n("Aggregate", 60, {}, [join("(a.id = b.id)", [scan("a"), scan("b")])]);
    const next = n("Aggregate", 60, {}, [n("Sort", 55, {}, [join("(x.id = b.id)", [scan("x"), scan("b")])])]);
    expect(diffPlans(prev, next).nodes.get("2")?.status).toBe("new");
  });
});
