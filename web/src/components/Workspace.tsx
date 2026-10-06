"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Editor from "@monaco-editor/react";
import MvCompare from "./MvCompare";
import NodePanel from "./NodePanel";
import PlanGraph from "./PlanGraph";
import {
  fetchPlan,
  getQuery,
  getSnapshot,
  listQueries,
  type PlanResponse,
  type QueryInfo,
  type Snapshot,
} from "@/lib/api";
import { mapNodeIds } from "@/lib/nodeIds";
import { diffPlans, nodeById } from "@/lib/planDiff";
import { useDarkMode } from "@/lib/useDarkMode";

type Compare = "baseline" | "previous" | "off";

const PLAYGROUND_SQL = `SELECT t.title, mi.info
FROM title AS t, movie_info AS mi
WHERE t.id = mi.movie_id
  AND t.id < 100;`;

const LIVE_DELAY_MS = 600;

/**
 * Edit SQL, see its plan. With a queryId it works on that JOB query; without one it is a
 * free-form playground. Edits re-explain automatically (never with ANALYZE) and the plan is
 * diffed against a baseline so the effect of a rewrite is visible.
 */
export default function Workspace({
  queryId,
  focusNodeId,
  initialMode = "plan",
}: {
  queryId?: string;
  focusNodeId?: string;
  initialMode?: "plan" | "mv";
}) {
  const dark = useDarkMode();
  const [sql, setSql] = useState<string | null>(queryId ? null : PLAYGROUND_SQL);
  const [original, setOriginal] = useState<string | null>(queryId ? null : PLAYGROUND_SQL);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [queries, setQueries] = useState<QueryInfo[]>([]);

  const [current, setCurrent] = useState<PlanResponse | null>(null);
  const [previous, setPrevious] = useState<PlanResponse | null>(null);
  const [baseline, setBaseline] = useState<PlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [live, setLive] = useState(true);
  const [analyze, setAnalyze] = useState(false);
  const [compare, setCompare] = useState<Compare>("baseline");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [mode, setMode] = useState<"plan" | "mv">(initialMode);
  const [originalPlan, setOriginalPlan] = useState<PlanResponse | null>(null);
  const [customNodes, setCustomNodes] = useState<string[]>([]);

  const currentRef = useRef<PlanResponse | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const originalRef = useRef<string | null>(queryId ? null : PLAYGROUND_SQL);

  useEffect(() => {
    listQueries().then(setQueries).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!queryId) return;
    getQuery(queryId)
      .then((q) => {
        originalRef.current = q.sql;
        setSql(q.sql);
        setOriginal(q.sql);
      })
      .catch((e: Error) => setLoadError(e.message));
  }, [queryId]);

  useEffect(() => {
    if (!queryId) return;
    getSnapshot(queryId).then(setSnapshot).catch(() => undefined);
  }, [queryId]);

  const run = useCallback(async (text: string, withAnalyze: boolean) => {
    abortRef.current?.abort(); // a newer edit supersedes the in-flight request
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    try {
      const result = await fetchPlan(text, withAnalyze, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setPrevious(currentRef.current);
      currentRef.current = result;
      setCurrent(result);
      setBaseline((b) => b ?? result); // first plan is the reference point
      if (text === originalRef.current) setOriginalPlan(result);
      setError(null);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError((e as Error).message);
    } finally {
      if (abortRef.current === ctrl) setLoading(false);
    }
  }, []);

  // Live re-explain, debounced; also performs the initial explain once the SQL is known.
  useEffect(() => {
    if (sql === null || !live) return;
    const t = setTimeout(() => void run(sql, false), LIVE_DELAY_MS);
    return () => clearTimeout(t);
  }, [sql, live, run]);

  const view = mode === "mv" && queryId && sql === original ? "mv" : "plan";
  const toggleWhatIf = (nodeId: string) => {
    setCustomNodes((cur) => (cur.includes(nodeId) ? cur.filter((n) => n !== nodeId) : [...cur, nodeId]));
    setMode("mv");
  };

  const reference = compare === "baseline" ? baseline : compare === "previous" ? previous : null;
  const diff = useMemo(
    () => (reference && current ? diffPlans(reference.plan, current.plan) : null),
    [reference, current],
  );
  const edited = original !== null && sql !== original;

  // Node ids (MV candidates) are only meaningful for the unmodified query whose live plan
  // still has the stored plan's shape.
  const nodeIds = useMemo(
    () => (!edited && current && snapshot ? mapNodeIds(current.plan, snapshot.plan) : null),
    [edited, current, snapshot],
  );
  const sharedBy = useMemo(() => {
    if (!nodeIds || !snapshot) return null;
    return new Map([...nodeIds].map(([id, nid]) => [id, snapshot.shared_counts[nid] ?? 1]));
  }, [nodeIds, snapshot]);
  const focusedId = useMemo(
    () => (nodeIds && focusNodeId ? ([...nodeIds].find(([, nid]) => nid === focusNodeId)?.[0] ?? null) : null),
    [nodeIds, focusNodeId],
  );
  const activeId = selectedId ?? focusedId;
  const selectedNode = current && activeId !== null ? nodeById(current.plan, activeId) : null;
  const candidateNote = !queryId
    ? "MV candidate info is available for JOB workload queries."
    : edited
      ? "The SQL was edited, so this plan no longer maps to the workload's MV candidates. Reset to see them."
      : !snapshot || !current
        ? null
        : nodeIds
          ? null
          : "The live plan differs from the stored plan, so node ids cannot be matched.";

  const idx = queries.findIndex((q) => q.id === queryId);
  const prevQ = idx > 0 ? queries[idx - 1] : null;
  const nextQ = idx >= 0 && idx < queries.length - 1 ? queries[idx + 1] : null;
  const costDelta =
    baseline && current && baseline !== current
      ? (current.plan["Total Cost"] - baseline.plan["Total Cost"]) / baseline.plan["Total Cost"]
      : null;

  if (loadError) return <p className="p-6 text-sm text-red-600">{loadError}</p>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-200 px-4 py-2 text-sm dark:border-zinc-800">
        <Link href="/queries" className="text-zinc-500 hover:underline">
          Queries
        </Link>
        <span className="font-semibold">{queryId ?? "Playground"}</span>
        {queryId && (
          <span className="flex gap-1">
            {prevQ ? <Link href={`/queries/${prevQ.id}`} className="rounded border px-1.5 text-xs" title={prevQ.id}>←</Link> : null}
            {nextQ ? <Link href={`/queries/${nextQ.id}`} className="rounded border px-1.5 text-xs" title={nextQ.id}>→</Link> : null}
          </span>
        )}
        {edited && <span className="rounded bg-amber-500 px-1.5 text-xs text-white">edited</span>}

        <span className="ml-2 flex overflow-hidden rounded-md border border-zinc-300 text-xs dark:border-zinc-700">
          {(["plan", "mv"] as const).map((m) => (
            <button
              key={m}
              disabled={m === "mv" && (!queryId || edited)}
              onClick={() => setMode(m)}
              title={m === "mv" ? (queryId ? (edited ? "Reset the SQL to compare with MVs" : undefined) : "Available for JOB queries") : undefined}
              className={`px-2 py-1 disabled:opacity-40 ${
                view === m ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : ""
              }`}
            >
              {m === "plan" ? "Plan" : "With MVs"}
            </button>
          ))}
        </span>

        <label className="ml-2 flex items-center gap-1 text-xs">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
          Live
        </label>
        <label className="flex items-center gap-1 text-xs" title="Executes the query (read-only transaction)">
          <input type="checkbox" checked={analyze} onChange={(e) => setAnalyze(e.target.checked)} />
          ANALYZE
        </label>
        <button
          onClick={() => sql !== null && void run(sql, analyze)}
          disabled={loading || sql === null}
          className="rounded-md bg-zinc-900 px-3 py-1 text-xs text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {loading ? "Running…" : "Explain"}
        </button>
        {edited && (
          <button onClick={() => setSql(original)} className="rounded-md border px-2 py-1 text-xs">
            Reset to original
          </button>
        )}

        <div className="ml-auto flex items-center gap-3 text-xs">
          {current && (
            <span className="tabular-nums text-zinc-500">
              cost {current.plan["Total Cost"].toLocaleString(undefined, { maximumFractionDigits: 0 })}
              {costDelta !== null && (
                <span className={costDelta < 0 ? "text-emerald-600" : "text-red-600"}>
                  {" "}
                  ({costDelta > 0 ? "+" : ""}
                  {(costDelta * 100).toFixed(0)}% vs baseline)
                </span>
              )}
              {current.planning_time_ms != null && ` · planning ${current.planning_time_ms.toFixed(1)} ms`}
              {current.execution_time_ms != null && ` · exec ${current.execution_time_ms.toFixed(1)} ms`}
            </span>
          )}
          <select
            value={compare}
            onChange={(e) => setCompare(e.target.value as Compare)}
            className="rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
          >
            <option value="baseline" className="text-black">Compare: baseline</option>
            <option value="previous" className="text-black">Compare: previous</option>
            <option value="off" className="text-black">Compare: off</option>
          </select>
          <button
            onClick={() => current && setBaseline(current)}
            disabled={!current}
            className="rounded border px-2 py-0.5 disabled:opacity-40"
            title="Use the current plan as the baseline"
          >
            Pin as baseline
          </button>
        </div>
      </div>

      <div className={`grid min-h-0 flex-1 ${view === "mv" ? "grid-cols-[minmax(240px,22%)_1fr]" : "grid-cols-[minmax(280px,26%)_1fr_280px]"}`}>
        <div className="border-r border-zinc-200 dark:border-zinc-800">
          {sql !== null ? (
            <Editor
              language="sql"
              value={sql}
              onChange={(v) => setSql(v ?? "")}
              theme={dark ? "vs-dark" : "light"}
              options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: "on", scrollBeyondLastLine: false }}
            />
          ) : (
            <p className="p-4 text-sm text-zinc-500">Loading query…</p>
          )}
        </div>

        {view === "mv" && queryId ? (
          <MvCompare
            queryId={queryId}
            originalPlan={originalPlan}
            customNodes={customNodes}
            onCustomNodes={setCustomNodes}
          />
        ) : (
          <>
        <div className="relative min-w-0">
          {error && (
            <pre className="absolute inset-x-0 top-0 z-10 max-h-40 overflow-auto whitespace-pre-wrap bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </pre>
          )}
          {current ? (
            <div className={loading ? "h-full opacity-60 transition-opacity" : "h-full"}>
              <PlanGraph
                plan={current.plan}
                diff={diff}
                selectedId={activeId}
                sharedBy={sharedBy}
                onSelect={(id) => setSelectedId(id)}
              />
            </div>
          ) : (
            !error && <p className="p-6 text-sm text-zinc-500">{loading ? "Planning…" : "No plan yet."}</p>
          )}
        </div>

        <aside className="overflow-auto border-l border-zinc-200 dark:border-zinc-800">
          <NodePanel
            node={selectedNode}
            nodeDiff={activeId !== null ? diff?.nodes.get(activeId) : undefined}
            diff={diff}
            candidateId={activeId !== null ? nodeIds?.get(activeId) : null}
            candidateNote={activeId !== null ? candidateNote : null}
            queryId={queryId}
            whatIfNodes={customNodes}
            onWhatIf={toggleWhatIf}
          />
        </aside>
          </>
        )}
      </div>
    </div>
  );
}
