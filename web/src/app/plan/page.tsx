"use client";

import { useState } from "react";
import Editor from "@monaco-editor/react";
import PlanGraph from "@/components/PlanGraph";
import { fetchPlan, type PlanResponse } from "@/lib/api";

const INITIAL_SQL = `SELECT t.title, mi.info
FROM title t
JOIN movie_info mi ON mi.movie_id = t.id
WHERE t.id < 100;`;

export default function PlanPage() {
  const [sql, setSql] = useState(INITIAL_SQL);
  const [analyze, setAnalyze] = useState(false);
  const [result, setResult] = useState<PlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setResult(await fetchPlan(sql, analyze));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-4 border-b border-zinc-200 px-4 py-2 dark:border-zinc-800">
        <h1 className="text-sm font-semibold">Query Plan</h1>
        <button
          onClick={run}
          disabled={loading}
          className="rounded-md bg-zinc-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {loading ? "Running…" : "Explain"}
        </button>
        <label className="flex items-center gap-1 text-sm text-zinc-600 dark:text-zinc-400">
          <input type="checkbox" checked={analyze} onChange={(e) => setAnalyze(e.target.checked)} />
          ANALYZE (executes query, read-only)
        </label>
        {result && (
          <span className="ml-auto text-xs tabular-nums text-zinc-500">
            planning {result.planning_time_ms?.toFixed(2)} ms
            {result.execution_time_ms != null && ` · execution ${result.execution_time_ms.toFixed(2)} ms`}
          </span>
        )}
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-2">
        <div className="border-r border-zinc-200 dark:border-zinc-800">
          <Editor
            language="sql"
            value={sql}
            onChange={(v) => setSql(v ?? "")}
            theme="vs-dark"
            options={{ minimap: { enabled: false }, fontSize: 13 }}
          />
        </div>
        <div className="relative">
          {error && (
            <pre className="absolute inset-x-0 top-0 z-10 whitespace-pre-wrap bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </pre>
          )}
          {result ? (
            <PlanGraph plan={result.plan} />
          ) : (
            <p className="p-6 text-sm text-zinc-500">Run Explain to see the plan.</p>
          )}
        </div>
      </div>
    </div>
  );
}
