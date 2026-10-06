"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import BarChart from "@/components/charts/BarChart";
import Legend from "@/components/charts/Legend";
import LineChart from "@/components/charts/LineChart";
import StackedBars from "@/components/charts/StackedBars";
import {
  compareResultSet,
  listResultSets,
  type AlgorithmResult,
  type Comparison,
  type ResultSet,
} from "@/lib/api";
import { algorithmColor, PHASES, phaseColor } from "@/lib/colors";
import { fmtNumber, fmtSeconds } from "@/lib/format";

export default function ResultsPage() {
  const [sets, setSets] = useState<ResultSet[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listResultSets().then(setSets).catch((e: Error) => setError(e.message));
  }, []);

  const current = selected ?? sets?.[0]?.id ?? null;

  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    compareResultSet(current)
      .then((c) => !cancelled && (setLoaded(c), setError(null)))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [current]);

  // Ignore a response that belongs to a set we have since navigated away from.
  const data = loaded?.id === current ? loaded : null;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8 p-8">
      <header className="flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-semibold">Results</h1>
        {sets && (
          <select
            value={current ?? ""}
            onChange={(e) => setSelected(e.target.value)}
            className="max-w-xs rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700"
          >
            {sets.map((s) => (
              <option key={s.id} value={s.id} className="text-black">
                {s.name} — {s.algorithms.join(", ")}
              </option>
            ))}
          </select>
        )}
      </header>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {sets && sets.length === 0 && <p className="text-sm text-zinc-500">No results found under Output/.</p>}
      {data && <ComparisonView key={data.id} data={data} />}
    </div>
  );
}

/** Algorithms that ran the same workload and query count are comparable. */
const workloadKey = (a: AlgorithmResult) =>
  a.benchmark ? `${a.benchmark.workload_type ?? "unknown"} · ${a.benchmark.total_queries} queries` : "no benchmark";

/** Default to the largest comparable group, preferring the most recent on ties. */
function defaultSelection(algorithms: AlgorithmResult[]): string[] {
  const groups = new Map<string, AlgorithmResult[]>();
  algorithms.forEach((a) => groups.set(workloadKey(a), [...(groups.get(workloadKey(a)) ?? []), a]));
  const latest = (g: AlgorithmResult[]) => Math.max(...g.map((a) => Date.parse(a.summary?.timestamp ?? "") || 0));
  const [best] = [...groups.values()].sort((x, y) => y.length - x.length || latest(y) - latest(x));
  return best.map((a) => a.name);
}

function ComparisonView({ data }: { data: Comparison }) {
  const allNames = data.algorithms.map((a) => a.name);
  // Colors stay tied to the algorithm even when the selection changes.
  const color = (n: string) => algorithmColor(n, allNames);

  const [picked, setPicked] = useState<string[] | null>(null);
  const selection = picked ?? defaultSelection(data.algorithms);
  const toggle = (n: string) =>
    setPicked(selection.includes(n) ? selection.filter((x) => x !== n) : [...selection, n]);

  const shown = data.algorithms.filter((a) => selection.includes(a.name));
  const warnings = comparabilityWarnings(shown);

  const withBench = shown.filter((a) => a.benchmark);
  const byTime = [...withBench].sort((a, b) => a.benchmark!.total_time - b.benchmark!.total_time);

  const groupKeys = new Set<string>();
  shown.forEach((a) => Object.keys(a.benchmark?.group_results ?? {}).forEach((k) => groupKeys.add(k)));
  const groups = [...groupKeys].sort((a, b) => parseFloat(a) - parseFloat(b));

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {data.algorithms.map((a) => {
          const on = selection.includes(a.name);
          return (
            <button
              key={a.name}
              onClick={() => toggle(a.name)}
              title={workloadKey(a)}
              className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
                on ? "border-zinc-500" : "border-zinc-300 text-zinc-400 dark:border-zinc-700"
              }`}
            >
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ background: on ? color(a.name) : "transparent", outline: `1px solid ${color(a.name)}` }}
              />
              {a.name}
              <span className="text-zinc-500">{workloadKey(a)}</span>
            </button>
          );
        })}
      </div>

      <Link
        href={`/overview?set=${encodeURIComponent(data.id)}&algo=${encodeURIComponent(selection.filter((n) => n !== "none").join(","))}`}
        className="w-fit text-xs text-blue-600 underline"
      >
        Show the selected nodes on the plan overview →
      </Link>

      {warnings.length > 0 && (
        <div className="rounded-md border border-amber-400 bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <div className="mb-1 font-medium">Results may not be directly comparable</div>
          <ul className="list-disc pl-4">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">Summary</h2>
        <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-zinc-100 text-zinc-500 dark:bg-zinc-900">
              <tr>
                {["Algorithm", "Query time", "Avg / query", `Speedup vs ${data.baseline ?? "baseline"}`, "MVs", "Storage", "Optimize", "Pipeline", "Failed"].map(
                  (h, i) => (
                    <th key={h} className={`px-3 py-2 ${i > 0 ? "text-right" : ""}`}>
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {shown.map((a) => (
                <tr key={a.name} className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className="px-3 py-2">
                    <span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color(a.name) }} />
                    {a.name}
                  </td>
                  <Num>{fmtSeconds(a.benchmark?.total_time)}</Num>
                  <Num>{a.benchmark ? `${a.benchmark.avg_time_per_query.toFixed(3)} s` : "–"}</Num>
                  <Num>{a.speedup_vs_baseline != null ? `${a.speedup_vs_baseline.toFixed(2)}×` : "n/a"}</Num>
                  <Num>{fmtNumber(a.optimization?.num_selected_views)}</Num>
                  <Num>{a.optimization?.total_storage_mb != null ? `${fmtNumber(a.optimization.total_storage_mb, 1)} MB` : "–"}</Num>
                  <Num>{fmtSeconds(a.summary?.phases.optimization ?? a.optimization?.execution_time)}</Num>
                  <Num>{fmtSeconds(a.summary?.total_execution_time)}</Num>
                  <Num>{a.benchmark ? fmtNumber(a.benchmark.failed) : "–"}</Num>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          Query time excludes cache warm-up. Speedup is shown only when the baseline ran the same workload
          and query count.
        </p>
      </section>

      {byTime.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold">Query execution time</h2>
          <BarChart
            bars={byTime.map((a) => ({
              label: a.name,
              value: a.benchmark!.total_time,
              color: color(a.name),
              note: `${a.benchmark!.total_queries} queries · ${a.benchmark!.workload_type ?? "unknown workload"}`,
            }))}
          />
        </section>
      )}

      {shown.some((a) => a.summary) && (
        <section>
          <h2 className="mb-3 text-sm font-semibold">Pipeline time by phase</h2>
          <div className="mb-3">
            <Legend items={PHASES.map(([, label], i) => ({ label, color: phaseColor(i) }))} />
          </div>
          <StackedBars
            segments={PHASES.map(([key, label], i) => ({ key, label, color: phaseColor(i) }))}
            rows={shown
              .filter((a) => a.summary)
              .map((a) => ({ label: a.name, values: a.summary!.phases }))}
          />
        </section>
      )}

      {groups.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold">Average query time by variability group</h2>
          <p className="mb-3 text-xs text-zinc-500">RedBench groups queries by variability percentile.</p>
          <div className="mb-3">
            <Legend items={withBench.map((a) => ({ label: a.name, color: color(a.name) }))} />
          </div>
          <LineChart
            categories={groups}
            yLabel="Average query time by variability group"
            format={(v) => `${v.toFixed(v < 1 ? 2 : 1)} s`}
            lines={withBench
              .filter((a) => a.benchmark!.group_results && Object.keys(a.benchmark!.group_results).length)
              .map((a) => ({
                label: a.name,
                color: color(a.name),
                values: groups.map((g) => a.benchmark!.group_results![g]?.avg_time ?? null),
              }))}
          />
        </section>
      )}
    </>
  );
}

function comparabilityWarnings(algos: AlgorithmResult[]): string[] {
  const benches = algos.filter((a) => a.benchmark);
  const warnings: string[] = [];
  if (new Set(benches.map(workloadKey)).size > 1)
    warnings.push(`Selected algorithms ran different workloads (${benches.map((a) => `${a.name}: ${workloadKey(a)}`).join("; ")})`);
  benches.filter((a) => a.benchmark!.failed > 0).forEach((a) => warnings.push(`${a.name}: ${a.benchmark!.failed} queries failed`));
  return warnings;
}

function Num({ children }: { children: React.ReactNode }) {
  return <td className="px-3 py-2 text-right">{children}</td>;
}
