"use client";

import { useState } from "react";
import Link from "next/link";
import { ApiError, runNodeWhatIf, type NodeWhatIf as Result } from "@/lib/api";
import { fmtBytes, fmtNumber } from "@/lib/format";

function Delta({ before, after }: { before: number | null; after: number | null }) {
  if (!before || after == null) return null;
  const d = (after - before) / before;
  return (
    <span className={d < 0 ? "text-emerald-600" : d > 0 ? "text-red-600" : ""}>
      {d > 0 ? "+" : ""}
      {(d * 100).toFixed(0)}%
    </span>
  );
}

/**
 * Verify a node as an MV on every query that contains it: the server builds it once in a
 * rolled-back scratch schema and compares each query's plan (and optionally runtime) before/after.
 */
export default function NodeWhatIf({ nodeId, currentQueryId }: { nodeId: string; currentQueryId?: string }) {
  const [analyze, setAnalyze] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmBytes, setConfirmBytes] = useState<number | null>(null);

  async function run(opts: { confirm?: boolean; force?: boolean } = {}) {
    setLoading(true);
    setError(null);
    setConfirmBytes(null);
    try {
      setResult(await runNodeWhatIf(nodeId, { analyze, confirm_large: opts.confirm, force: opts.force }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && (e.detail as { code?: string })?.code === "large_mv") {
        setConfirmBytes((e.detail as { size_bytes: number }).size_bytes);
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }

  const rows = result ? [...result.queries].sort((a, b) => a.cost_after - a.cost_before - (b.cost_after - b.cost_before)) : [];
  return (
    <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
      <h3 className="text-sm font-semibold">What-if: materialize this node</h3>
      <p className="mt-1 text-[11px] text-zinc-500">
        Builds the MV in a scratch schema (rolled back afterwards) and re-plans every query containing it.
      </p>
      <label className="mt-2 flex items-center gap-1.5">
        <input type="checkbox" checked={analyze} onChange={(e) => setAnalyze(e.target.checked)} />
        Measure actual time (executes queries, slow)
      </label>
      <button
        onClick={() => void run()}
        disabled={loading}
        className="mt-2 w-full rounded-md bg-zinc-900 px-2 py-1 text-xs text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {loading ? "Building MV and planning…" : result ? "Run again" : "Verify on sharing queries"}
      </button>

      {confirmBytes !== null && (
        <div className="mt-2 rounded border border-amber-400 bg-amber-50 p-2 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Estimated {fmtBytes(confirmBytes)}; building it may take minutes and temporary disk.
          <button onClick={() => void run({ confirm: true })} className="ml-2 rounded border border-amber-600 px-1.5">
            Run anyway
          </button>
        </div>
      )}
      {error && <p className="mt-2 text-red-600">{error}</p>}

      {result && (
        <div className="mt-3">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
            <div>
              <dt className="text-zinc-500">Total est. cost</dt>
              <dd className="tabular-nums">
                {fmtNumber(result.total_cost_before)} → {fmtNumber(result.total_cost_after)}{" "}
                <Delta before={result.total_cost_before} after={result.total_cost_after} />
              </dd>
            </div>
            <div>
              <dt className="text-zinc-500">MV build</dt>
              <dd className="tabular-nums">{result.mv.create_seconds.toFixed(1)} s</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Size (actual / planner)</dt>
              <dd className="tabular-nums">
                {fmtBytes(result.mv.actual_size_bytes)} / {fmtBytes(result.mv.est_size_bytes)}
              </dd>
            </div>
            <div>
              <dt className="text-zinc-500">Cost improves</dt>
              <dd className="tabular-nums">
                {result.queries.filter((q) => q.cost_after < q.cost_before).length} / {result.queries.length} queries
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-[11px] text-zinc-500">
            Planner costs after a rewrite can mislead (MV scans are often estimated at 1 row). Tick “Measure actual
            time” to confirm.{result.truncated && " Only the first queries were checked."}
            {result.cached && " (cached)"}
          </p>
          <button onClick={() => void run({ force: true })} className="mt-1 rounded border px-1.5 text-[11px]">
            Refresh
          </button>

          <table className="mt-2 w-full text-left text-[11px]">
            <thead className="text-zinc-500">
              <tr>
                <th className="py-1 font-normal">Query</th>
                <th className="py-1 text-right font-normal">Cost</th>
                {result.analyzed && <th className="py-1 text-right font-normal">Time (ms)</th>}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((q) => (
                <tr key={q.query_id} className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className="py-1">
                    <Link
                      href={`/queries/${q.query_id}?mode=mv&mv=${encodeURIComponent(nodeId)}`}
                      className={q.query_id === currentQueryId ? "font-semibold underline" : "hover:underline"}
                      title={q.uses_mv ? "Plan uses the MV" : "Planner did not use the MV"}
                    >
                      {q.query_id}
                      {!q.uses_mv && <span className="text-zinc-400"> ∅</span>}
                    </Link>
                  </td>
                  <td className="py-1 text-right">
                    {fmtNumber(q.cost_before)} → {fmtNumber(q.cost_after)} <Delta before={q.cost_before} after={q.cost_after} />
                  </td>
                  {result.analyzed && (
                    <td className="py-1 text-right">
                      {q.time_before_ms != null ? fmtNumber(q.time_before_ms, 0) : "–"} →{" "}
                      {q.time_after_ms != null ? fmtNumber(q.time_after_ms, 0) : "–"}{" "}
                      <Delta before={q.time_before_ms} after={q.time_after_ms} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[11px] text-zinc-500">∅ = the planner chose not to use the MV.</p>
        </div>
      )}
    </div>
  );
}
