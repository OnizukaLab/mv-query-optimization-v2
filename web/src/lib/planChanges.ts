import { useSyncExternalStore } from "react";
import { ApiError, fetchPlan, getQuery, listMvSets } from "./api";
import { joinOrder } from "./joinOrder";
import { loadQueries, type CompareSelection } from "./queryList";
import { planWithMvs, runExclusive } from "./whatifQueue";

/**
 * Per-query answer to "did this experiment/algorithm's rewrite change the join order?"
 *
 * changed/same: see lib/joinOrder.ts. none: the selection chose no MV for the query.
 * unknown: needs a large MV built (asks for consent on the query's page). failed: rewriting or
 * planning failed. A missing entry means "not computed yet".
 */
export type ChangeVerdict = "changed" | "same" | "none" | "unknown" | "failed";

const verdicts = new Map<string, ChangeVerdict>();
const listeners = new Set<() => void>();
let version = 0;

const keyOf = (sel: CompareSelection, queryId: string) => `${sel.setId}|${sel.algorithm}|${queryId}`;

function notify(): void {
  version++;
  listeners.forEach((l) => l());
}

export function setVerdict(sel: CompareSelection, queryId: string, v: ChangeVerdict): void {
  if (verdicts.get(keyOf(sel, queryId)) === v) return;
  verdicts.set(keyOf(sel, queryId), v);
  notify();
}

/** Verdict lookup for one selection, re-rendering the caller as the background probe fills it in. */
export function usePlanChanges(sel: CompareSelection | null): (queryId: string) => ChangeVerdict | undefined {
  useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => version,
    () => 0,
  );
  return (queryId) => (sel ? verdicts.get(keyOf(sel, queryId)) : undefined);
}

/**
 * Compute the verdict of every workload query for one selection, one at a time in the background,
 * starting at `startQuery` (the one on screen). Known verdicts are kept, so restarting after a
 * query switch only continues. Returns a function that stops the probe.
 */
export function startPlanChangeProbe(sel: CompareSelection, startQuery: string): () => void {
  let stopped = false;
  void (async () => {
    let queries;
    try {
      queries = await loadQueries();
    } catch {
      return;
    }
    const at = Math.max(0, queries.findIndex((q) => q.id === startQuery));
    for (const q of [...queries.slice(at), ...queries.slice(0, at)]) {
      if (stopped) return;
      if (verdicts.has(keyOf(sel, q.id))) continue;
      try {
        const chosen = (await listMvSets(q.id)).find((s) => s.set_id === sel.setId && s.algorithm === sel.algorithm);
        if (!chosen) {
          setVerdict(sel, q.id, "none");
          continue;
        }
        const original = await fetchPlan((await getQuery(q.id)).sql, false);
        const rewritten = await runExclusive(() => {
          if (stopped) throw new DOMException("stopped", "AbortError");
          return planWithMvs(q.id, chosen.node_ids);
        });
        const order = joinOrder(
          original.plan,
          rewritten.plan,
          Object.fromEntries(rewritten.mvs.map((v) => [v.node_id, v.base_tables ?? []])),
        );
        setVerdict(sel, q.id, order.changed ? "changed" : "same");
      } catch (e) {
        if (stopped) return;
        const large = e instanceof ApiError && (e.detail as { code?: string } | undefined)?.code === "large_mv";
        setVerdict(sel, q.id, large ? "unknown" : "failed");
      }
    }
  })();
  return () => {
    stopped = true;
  };
}
