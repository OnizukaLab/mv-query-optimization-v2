import { ApiError, fetchMvPlan, type MvPlan } from "./api";

// The database runs one what-if at a time, so every mv-plan call in the page goes through one
// queue. Module-level on purpose: it must outlive components that remount on query changes.
let tail: Promise<unknown> = Promise.resolve();

export function runExclusive<T>(fn: () => Promise<T>): Promise<T> {
  const next = tail.then(fn, fn);
  tail = next.catch(() => undefined);
  return next;
}

/**
 * Plan a query rewritten onto MVs. Requests are never aborted mid-flight: the server keeps
 * working on them, so freeing the queue early would make the next call hit "Another what-if is
 * running". Callers drop stale results instead. A busy answer (e.g. from another tab) is retried.
 */
export async function planWithMvs(
  queryId: string,
  nodeIds: string[],
  opts: { confirm?: boolean; force?: boolean; analyze?: boolean } = {},
): Promise<MvPlan> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetchMvPlan(queryId, {
        node_ids: nodeIds,
        confirm_large: opts.confirm,
        force: opts.force,
        analyze: opts.analyze,
      });
    } catch (e) {
      const busy = e instanceof ApiError && e.status === 409 && String(e.detail).includes("Another what-if");
      if (!busy || attempt >= 10) throw e;
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
}
