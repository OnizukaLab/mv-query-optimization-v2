"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import PlanGraph, { type DiffWording } from "./PlanGraph";
import QueryPicker from "./QueryPicker";
import SqlDiff from "./SqlDiff";
import {
  ApiError,
  fetchPlan,
  getQuery,
  getSnapshot,
  listMvSets,
  type MvPlan,
  type MvSet,
  type PlanResponse,
  type Snapshot,
} from "@/lib/api";
import { fmtBytes, fmtMs, fmtSeconds } from "@/lib/format";
import { mapNodeIds } from "@/lib/nodeIds";
import { setVerdict, startPlanChangeProbe, usePlanChanges } from "@/lib/planChanges";
import { loadCompareSelection, saveCompareSelection } from "@/lib/queryList";
import { planWithMvs, runExclusive } from "@/lib/whatifQueue";
import { joinOrder, type JoinOrder } from "@/lib/joinOrder";
import { costChange, diffPlans, mvMarks, type PlanDiff } from "@/lib/planDiff";

// Module-level so the graphs receive the same object every render (a fresh one would rebuild
// the nodes each time and keep React Flow from ever finishing measuring them).
const ORIGINAL_WORDING: DiffWording = { new: "replaced", moved: null };
const MV_WORDING: DiffWording = { moved: null };

/** Which nodes of the original plan the selected MVs materialize (exact, via candidate ids). */
function useOriginalMarks(plan: PlanResponse | null, snapshot: Snapshot | null, nodeKey: string) {
  return useMemo(() => {
    if (!plan || !snapshot || !nodeKey) return null;
    const owners = mapNodeIds(plan.plan, snapshot.plan);
    return owners ? mvMarks(plan.plan, nodeKey.split(","), { ownerOf: owners }) : null;
  }, [plan, snapshot, nodeKey]);
}

/** Scans of the selected MVs in the rewritten plan. */
function useScanMarks(result: MvPlan | null, nodeKey: string) {
  return useMemo(
    () => (result && nodeKey ? mvMarks(result.plan, nodeKey.split(","), { scanOf: true }) : null),
    [result, nodeKey],
  );
}

/** Whether the rewrite changed the join order (see lib/joinOrder.ts) for the query on screen. */
type Verdict = "changed" | "same" | "pending" | "unknown" | "failed";

function pct(change: number | null) {
  if (change === null) return null;
  return (
    <span className={change < 0 ? "text-emerald-600" : "text-red-600"}>
      {change > 0 ? "+" : ""}
      {(change * 100).toFixed(0)}%
    </span>
  );
}

/**
 * Original query vs. the query rewritten onto one algorithm's MV selection: the two SQL texts
 * side by side on top, their execution plans below.
 */
export default function QueryCompare({ queryId }: { queryId: string }) {
  const [sql, setSql] = useState<string | null>(null);
  const [originalPlan, setOriginalPlan] = useState<PlanResponse | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [sets, setSets] = useState<MvSet[] | null>(null);
  const [setId, setSetId] = useState<string | null>(null);
  const [algorithm, setAlgorithm] = useState<string | null>(null);
  // The remembered experiment/algorithm has no MV selection for this query.
  const [fellBack, setFellBack] = useState(false);
  const [result, setResult] = useState<MvPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsConfirm, setNeedsConfirm] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [measuring, setMeasuring] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    getQuery(queryId)
      .then((q) => {
        setSql(q.sql);
        return fetchPlan(q.sql, false);
      })
      .then(setOriginalPlan)
      .catch((e: Error) => setError(e.message));
    getSnapshot(queryId).then(setSnapshot).catch(() => undefined);
    listMvSets(queryId)
      .then((s) => {
        setSets(s);
        // Keep the experiment/algorithm the user chose on another query. Without a saved choice
        // (or when it has nothing for this query) show the newest experiment. A fallback is not
        // saved, so the choice comes back on queries that do have it.
        const pref = loadCompareSelection();
        const inExperiment = pref ? s.filter((x) => x.set_id === pref.setId) : [];
        const pick = inExperiment.find((x) => x.algorithm === pref?.algorithm) ?? inExperiment[0] ?? s[0];
        setSetId(pick?.set_id ?? null);
        setAlgorithm(pick?.algorithm ?? null);
        setFellBack(!!pref && (pick?.set_id !== pref.setId || pick?.algorithm !== pref.algorithm));
      })
      .catch((e: Error) => setError(e.message));
  }, [queryId]);

  // Experiments (result sets), newest first; each offers the algorithms that selected MVs for this query.
  const experiments = useMemo(() => [...new Set((sets ?? []).map((s) => s.set_id))], [sets]);
  const algorithms = useMemo(() => (sets ?? []).filter((s) => s.set_id === setId), [sets, setId]);
  const chosen = algorithms.find((s) => s.algorithm === algorithm) ?? null;

  const pickExperiment = (id: string) => {
    const available = (sets ?? []).filter((s) => s.set_id === id);
    // Keep the algorithm when the new experiment has it, otherwise fall back to its first one.
    const next = available.find((s) => s.algorithm === algorithm) ?? available[0];
    setSetId(id);
    setAlgorithm(next?.algorithm ?? null);
    setFellBack(false);
    if (next) saveCompareSelection({ setId: id, algorithm: next.algorithm });
  };
  const nodeKey = chosen?.node_ids.join(",") ?? "";

  const run = async (opts: { confirm?: boolean; force?: boolean; analyze?: boolean } = {}) => {
    if (!nodeKey) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError(null);
    setNeedsConfirm(null);
    try {
      const r = await runExclusive(() => {
        if (ctrl.signal.aborted) throw new DOMException("aborted", "AbortError");
        return planWithMvs(queryId, nodeKey.split(","), opts);
      });
      if (!ctrl.signal.aborted) setResult(r);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      if (e instanceof ApiError && e.status === 409 && (e.detail as { code?: string })?.code === "large_mv") {
        setNeedsConfirm((e.detail as { size_bytes: number }).size_bytes);
      } else {
        setError((e as Error).message);
      }
    } finally {
      if (abortRef.current === ctrl) setLoading(false);
    }
  };

  // EXPLAIN ANALYZE both sides, one after the other so they do not compete for the database.
  // The analyzed plans replace the estimated ones (same shape, plus actual rows and timings).
  const measure = async () => {
    if (sql === null || !nodeKey) return;
    setMeasuring(true);
    setError(null);
    try {
      setOriginalPlan(await fetchPlan(sql, true));
      await run({ analyze: true, force: true });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setMeasuring(false);
    }
  };

  // (Re)plan whenever the chosen MV set changes.
  useEffect(() => {
    if (!nodeKey) return;
    const t = setTimeout(() => void run(), 0);
    return () => {
      clearTimeout(t);
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run only depends on queryId/nodeKey
  }, [queryId, nodeKey]);

  const shown = result && result.node_ids.join(",") === nodeKey ? result : null;

  const originalMarks = useOriginalMarks(originalPlan, snapshot, nodeKey);
  const mvScanMarks = useScanMarks(shown, nodeKey);

  const orderOf = (mvPlan: MvPlan): JoinOrder | null =>
    originalPlan
      ? joinOrder(
          originalPlan.plan,
          mvPlan.plan,
          Object.fromEntries(mvPlan.mvs.map((v) => [v.node_id, v.base_tables ?? []])),
        )
      : null;

  // Verdict for the query on screen; other queries are computed in the background (lib/planChanges).
  const selection = setId && algorithm ? { setId, algorithm } : null;
  const shownOrder = shown ? orderOf(shown) : null;
  const verdict: Verdict = shown
    ? shownOrder?.changed
      ? "changed"
      : shownOrder
        ? "same"
        : "pending"
    : error
      ? "failed"
      : needsConfirm !== null
        ? "unknown"
        : "pending";
  const planChanges = usePlanChanges(selection);

  // Share the on-screen result with the query dropdown right away ...
  const verdictNow = verdict === "changed" || verdict === "same" || verdict === "unknown" || verdict === "failed" ? verdict : null;
  useEffect(() => {
    if (selection && verdictNow) setVerdict(selection, queryId, verdictNow);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- selection is rebuilt each render; its parts are the deps
  }, [setId, algorithm, queryId, verdictNow]);
  // ... and fill in the other queries one at a time while this page is open.
  useEffect(() => {
    if (!setId || !algorithm) return;
    return startPlanChangeProbe({ setId, algorithm }, queryId);
  }, [setId, algorithm, queryId]);
  const origDiff = useMemo(
    () => (shown && originalPlan ? diffPlans(shown.plan, originalPlan.plan) : null),
    [shown, originalPlan],
  );
  const mvDiff = useMemo(
    () => (shown && originalPlan ? diffPlans(originalPlan.plan, shown.plan) : null),
    [shown, originalPlan],
  );

  const costDelta = shown && originalPlan ? costChange(originalPlan.plan["Total Cost"], shown.plan["Total Cost"]) : null;
  const m = chosen?.measured;
  const measuredDelta = m?.baseline_s && m.with_mvs_s ? (m.with_mvs_s - m.baseline_s) / m.baseline_s : null;
  const createTotal = shown?.mvs.reduce((a, v) => a + v.create_seconds, 0) ?? 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-4 border-b border-zinc-200 px-4 py-2 text-xs dark:border-zinc-800">
        <QueryPicker queryId={queryId} suffix="/compare" marks={planChanges} />
        <label className="flex items-center gap-2">
          Experiment
          <select
            value={setId ?? ""}
            onChange={(e) => pickExperiment(e.target.value)}
            disabled={!experiments.length}
            className="max-w-xs rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
          >
            {experiments.map((id) => (
              <option key={id} value={id} className="text-black">
                {id === "_root" ? "latest run" : id}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Algorithm
          <select
            value={algorithm ?? ""}
            onChange={(e) => {
              setAlgorithm(e.target.value);
              setFellBack(false);
              if (setId) saveCompareSelection({ setId, algorithm: e.target.value });
            }}
            disabled={!algorithms.length}
            className="rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
          >
            {algorithms.map((s) => (
              <option key={s.algorithm} value={s.algorithm} className="text-black">
                {s.algorithm} ({s.node_ids.length} MVs)
              </option>
            ))}
          </select>
        </label>
        {chosen && (verdict === "changed" || verdict === "same" || verdict === "failed") && (
          <span
            className={`rounded px-1.5 py-0.5 font-medium text-white ${
              verdict === "changed" ? "bg-violet-600" : verdict === "same" ? "bg-amber-600" : "bg-red-600"
            }`}
          >
            {verdict === "changed" ? "Join order changed" : verdict === "same" ? "Join order unchanged" : "Rewrite failed"}
          </span>
        )}
        {fellBack && (
          <span className="text-[11px] text-amber-600" title="Your chosen experiment/algorithm selected no MVs for this query, so another one is shown. Your choice is kept and applies again on queries that have it.">
            Your chosen experiment/algorithm has no MVs for this query
          </span>
        )}
        {sets && sets.length === 0 && <span className="text-zinc-500">No experiment selected MVs for this query.</span>}
        {shown && (
          <>
            <span>
              <span className="text-zinc-500">Estimated cost </span>
              <span className="tabular-nums">
                {originalPlan?.plan["Total Cost"].toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "–"} →{" "}
                {shown.plan["Total Cost"].toLocaleString(undefined, { maximumFractionDigits: 0 })} {pct(costDelta)}
              </span>
            </span>
            <span>
              <span className="text-zinc-500" title="Query time recorded by the experiment run itself">
                Recorded in run{" "}
              </span>
              <span className="tabular-nums">
                {m && (m.baseline_s || m.with_mvs_s) ? (
                  <>
                    {fmtSeconds(m.baseline_s)} → {fmtSeconds(m.with_mvs_s)} {pct(measuredDelta)}
                  </>
                ) : (
                  "not recorded"
                )}
              </span>
            </span>
            <span className="tabular-nums">
              <span className="text-zinc-500">MV build </span>
              {fmtSeconds(createTotal)} · {shown.mvs.length} MV{shown.mvs.length > 1 ? "s" : ""}
            </span>
            <span title="Single EXPLAIN ANALYZE run each; the original runs first, so cache effects can favor the rewrite. Measure again to compare warm runs.">
              <span className="text-zinc-500">Execution time </span>
              <span className="tabular-nums">
                {originalPlan?.analyzed && shown.analyzed ? (
                  <>
                    {fmtMs(originalPlan.execution_time_ms)} → {fmtMs(shown.execution_time_ms)}{" "}
                    {pct(
                      originalPlan.execution_time_ms
                        ? ((shown.execution_time_ms ?? 0) - originalPlan.execution_time_ms) / originalPlan.execution_time_ms
                        : null,
                    )}
                  </>
                ) : (
                  <span className="text-zinc-500">not measured</span>
                )}
              </span>
            </span>
            <button
              onClick={() => void measure()}
              disabled={measuring || loading}
              className="ml-auto rounded border border-violet-500 px-2 py-0.5 disabled:opacity-50"
              title="Runs EXPLAIN ANALYZE on both queries (executes them in a read-only transaction; up to 2 min each)"
            >
              {measuring ? "Measuring…" : "Measure execution time"}
            </button>
            <button onClick={() => void run({ force: true })} disabled={measuring} className="rounded border px-2 py-0.5 disabled:opacity-50">
              Re-run{shown.cached ? " (cached)" : ""}
            </button>
          </>
        )}
      </div>

      {needsConfirm !== null && (
        <div className="border-b border-amber-400 bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          These MVs are estimated at {fmtBytes(needsConfirm)} and may take minutes to build in a scratch schema
          (rolled back afterwards).{" "}
          <button onClick={() => void run({ confirm: true })} className="ml-2 rounded border border-amber-600 px-2 py-0.5">
            Run anyway
          </button>
        </div>
      )}
      {error && <p className="border-b border-red-300 bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}

      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,2fr)_minmax(0,3fr)]">
        <section className="flex min-h-0 flex-col border-b border-zinc-200 dark:border-zinc-800">
          <Heads left="Original query" right={`Rewritten query${chosen ? ` (${chosen.algorithm})` : ""}`} />
          <div className="min-h-0 flex-1">
            {sql !== null && shown ? (
              <SqlDiff original={sql} modified={shown.rewritten_sql} />
            ) : (
              <p className="p-4 text-xs text-zinc-500">
                {sql === null ? "Loading query…" : loading ? "Building MVs in a scratch schema…" : "Choose an algorithm."}
              </p>
            )}
          </div>
        </section>

        <section className="flex min-h-0 flex-col">
          <Heads
            left={`Original plan${originalPlan?.analyzed ? ` · exec ${fmtMs(originalPlan.execution_time_ms)} · planning ${fmtMs(originalPlan.planning_time_ms)}` : ""}`}
            right={`Plan with MVs${shown?.analyzed ? ` · exec ${fmtMs(shown.execution_time_ms)} · planning ${fmtMs(shown.planning_time_ms)}` : ""}`}
          />
          {shown && originalPlan && mvDiff && (
            <p
              className={`mx-3 mb-1 rounded px-2 py-0.5 text-[11px] ${
                verdict === "changed"
                  ? "bg-violet-600/15 text-violet-800 dark:text-violet-200"
                  : "bg-amber-500/20 text-amber-900 dark:text-amber-200"
              }`}
            >
              {verdict === "changed" ? (
                <>
                  <b>The join order differs from the original</b> (tables are first scanned in a different order;{" "}
                  {planChangeSummary(mvDiff)}).
                  {shownOrder && (
                    <>
                      {" "}Original: {shownOrder.original.join(" → ")}. With MVs: {shownOrder.rewritten.join(" → ")}.
                    </>
                  )}
                </>
              ) : (
                <>
                  <b>The join order is the same as the original.</b>{" "}
                  {shown.mvs.every((v) => !v.used_in_plan)
                    ? "The planner does not use the selected MVs for this query."
                    : "The MVs only replace parts of the plan with scans of the MV; tables are still reached in the same order."}
                </>
              )}
            </p>
          )}
          <p className="px-3 pb-1 text-[11px] text-zinc-500">
            <span className="rounded bg-violet-600 px-1 text-white">MV</span> = node materialized by the selected MVs
            (dashed = inside it, replaced by a scan of the MV in the right plan).
            {!originalMarks && originalPlan && snapshot && " Exact marks unavailable (the live plan differs from the stored one); showing structural differences instead."}
          </p>
          <div className="grid min-h-0 flex-1 grid-cols-2 divide-x divide-zinc-200 dark:divide-zinc-800">
            <div className="min-w-0">
              {originalPlan ? (
                <PlanGraph
                  plan={originalPlan.plan}
                  // Exact MV marks when node ids map; otherwise fall back to the structural diff.
                  diff={originalMarks ? null : origDiff}
                  mvMarks={originalMarks}
                  wording={ORIGINAL_WORDING}
                  selectedId={null}
                  onSelect={() => undefined}
                />
              ) : (
                <p className="p-4 text-xs text-zinc-500">Planning…</p>
              )}
            </div>
            <div className="min-w-0">
              {shown ? (
                <PlanGraph
                  plan={shown.plan}
                  diff={mvDiff}
                  mvMarks={mvScanMarks}
                  wording={MV_WORDING}
                  selectedId={null}
                  onSelect={() => undefined}
                />
              ) : (
                <p className="p-4 text-xs text-zinc-500">
                  {loading
                    ? "Building MVs in a scratch schema and planning… (can take a while for large MVs)"
                    : error
                      ? "The plan with MVs could not be computed (see the error above)."
                      : needsConfirm !== null
                        ? "Waiting for confirmation (see above)."
                        : !sets?.length && sets
                          ? "No MV selection to compare."
                          : "–"}
                </p>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

/** "2 new, 2 changed, 7 removed nodes" for the rewritten plan relative to the original. */
function planChangeSummary(diff: PlanDiff): string {
  const counts = { new: 0, changed: 0, moved: 0 };
  diff.nodes.forEach((d) => {
    if (d.status !== "same") counts[d.status]++;
  });
  const parts = [
    counts.new && `${counts.new} new`,
    counts.changed && `${counts.changed} changed`,
    counts.moved && `${counts.moved} moved`,
    diff.removed.length && `${diff.removed.length} removed`,
  ].filter(Boolean);
  return parts.length ? `${parts.join(", ")} nodes` : "the plan structure differs";
}

function Heads({ left, right }: { left: string; right: string }) {
  return (
    <div className="grid grid-cols-2 text-xs font-semibold">
      <div className="px-3 py-1">{left}</div>
      <div className="border-l border-zinc-200 px-3 py-1 dark:border-zinc-800">{right}</div>
    </div>
  );
}
