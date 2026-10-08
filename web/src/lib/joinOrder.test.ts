import { describe, expect, it } from "vitest";
import { joinOrder } from "./joinOrder";
import type { PlanNode } from "./plan";

const n = (type: string, extra: Partial<PlanNode> = {}, plans?: PlanNode[]): PlanNode =>
  ({ "Node Type": type, "Total Cost": 1, "Plan Rows": 1, Plans: plans, ...extra }) as PlanNode;
const scan = (rel: string) => n("Seq Scan", { "Relation Name": rel });

describe("joinOrder", () => {
  // JOB 1a: the MVs replace sub-plans, but tables are still reached in the same order.
  it("is unchanged when MVs only replace sub-plans in place", () => {
    const original = n("Hash Join", {}, [n("Nested Loop", {}, [scan("info_type"), scan("movie_companies")]), scan("company_type")]);
    const rewritten = n("Hash Join", {}, [scan("non_leaf_2"), scan("company_type")]);
    const d = joinOrder(original, rewritten, { non_leaf_2: ["info_type", "movie_companies"] });
    expect(d.changed).toBe(false);
  });

  it("detects a different scan order after normalizing MV names", () => {
    const original = n("Nested Loop", {}, [scan("a"), n("Nested Loop", {}, [scan("b"), scan("c")])]);
    const rewritten = n("Nested Loop", {}, [scan("mv_bc"), scan("a")]);
    const d = joinOrder(original, rewritten, { mv_bc: ["b", "c"] });
    expect(d.changed).toBe(true);
    expect(d.original).toEqual(["a", "b", "c"]);
    expect(d.rewritten).toEqual(["b", "c", "a"]);
  });

  it("detects reordering that keeps the same operator types", () => {
    const original = n("Hash Join", {}, [scan("a"), scan("b")]);
    const rewritten = n("Hash Join", {}, [scan("b"), scan("a")]);
    expect(joinOrder(original, rewritten, {}).changed).toBe(true);
  });

  it("ignores tables that appear in only one of the plans", () => {
    const original = n("Hash Join", {}, [scan("a"), scan("b")]);
    const rewritten = n("Hash Join", {}, [scan("a"), scan("x")]);
    expect(joinOrder(original, rewritten, {}).changed).toBe(false);
  });

  it("skips tables read only through a Bitmap Heap Scan (matches the reference script)", () => {
    const bitmap = n("Bitmap Heap Scan", { "Relation Name": "mi" }, [n("Bitmap Index Scan", { "Index Name": "i" })]);
    const original = n("Nested Loop", {}, [scan("a"), bitmap]);
    const rewritten = n("Nested Loop", {}, [scan("a"), bitmap]);
    expect(joinOrder(original, rewritten, {}).original).toEqual(["a"]);
  });
});
