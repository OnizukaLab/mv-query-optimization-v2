"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Editor from "@monaco-editor/react";
import NodePanel from "./NodePanel";
import PlanGraph from "./PlanGraph";
import { fetchPlan, getQuery, listQueries, type PlanResponse, type QueryInfo } from "@/lib/api";
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
export default function Workspace({ queryId }: { queryId?: string }) {
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

  const currentRef = useRef<PlanResponse | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listQueries().then(setQueries).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!queryId) return;
    getQuery(queryId)
      .then((q) => {
        setSql(q.sql);
        setOriginal(q.sql);
      })
      .catch((e: Error) => setLoadError(e.message));
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

  const reference = compare === "baseline" ? baseline : compare === "previous" ? previous : null;
  const diff = useMemo(
    () => (reference && current ? diffPlans(reference.plan, current.plan) : null),
    [reference, current],
  );
  const selectedNode = current && selectedId !== null ? nodeById(current.plan, selectedId) : null;

  const idx = queries.findIndex((q) => q.id === queryId);
  const prevQ = idx > 0 ? queries[idx - 1] : null;
  const nextQ = idx >= 0 && idx < queries.length - 1 ? queries[idx + 1] : null;
  const edited = original !== null && sql !== original;
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

        <label className="ml-4 flex items-center gap-1 text-xs">
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

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(280px,26%)_1fr_280px]">
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

        <div className="relative min-w-0">
          {error && (
            <pre className="absolute inset-x-0 top-0 z-10 max-h-40 overflow-auto whitespace-pre-wrap bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </pre>
          )}
          {current ? (
            <div className={loading ? "h-full opacity-60 transition-opacity" : "h-full"}>
              <PlanGraph plan={current.plan} diff={diff} selectedId={selectedId} onSelect={(id) => setSelectedId(id)} />
            </div>
          ) : (
            !error && <p className="p-6 text-sm text-zinc-500">{loading ? "Planning…" : "No plan yet."}</p>
          )}
        </div>

        <aside className="overflow-auto border-l border-zinc-200 dark:border-zinc-800">
          <NodePanel
            node={selectedNode}
            nodeDiff={selectedId !== null ? diff?.nodes.get(selectedId) : undefined}
            diff={diff}
          />
        </aside>
      </div>
    </div>
  );
}
