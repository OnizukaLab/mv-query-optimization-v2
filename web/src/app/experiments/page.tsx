"use client";

import { useCallback, useEffect, useState } from "react";
import ExperimentForm from "@/components/ExperimentForm";
import RunPanel from "@/components/RunPanel";
import {
  listExperiments,
  startExperiment,
  stopExperiment,
  type ExperimentRequest,
  type JobSummary,
} from "@/lib/api";
import { useExperimentStream } from "@/lib/useExperimentStream";

function fmtDuration(j: JobSummary) {
  const s = Math.round((j.finished_at ?? Date.now() / 1000) - j.started_at);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function LiveRun({ jobId, onStop }: { jobId: string | null; onStop: () => void }) {
  const { summary, logs, error } = useExperimentStream(jobId);
  return <RunPanel summary={summary} logs={logs} error={error} onStop={onStop} />;
}

export default function ExperimentsPage() {
  const [history, setHistory] = useState<JobSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setHistory(await listExperiments());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  // Poll the list so status changes (finish/stop) show up without a manual reload.
  useEffect(() => {
    const tick = () => void refresh();
    const first = setTimeout(tick, 0);
    const t = setInterval(tick, 3000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [refresh]);

  // Until the user picks one, show the running experiment (or the latest).
  const current = selected ?? (history.find((j) => j.status === "running") ?? history[0])?.id ?? null;

  const running = history.some((j) => j.status === "running");

  async function onSubmit(req: ExperimentRequest) {
    try {
      const job = await startExperiment(req);
      setSelected(job.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onStop() {
    if (!current) return;
    try {
      await stopExperiment(current);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="grid h-full grid-cols-[320px_1fr]">
      <aside className="overflow-auto border-r border-zinc-200 p-4 dark:border-zinc-800">
        <h1 className="mb-4 text-sm font-semibold">New experiment</h1>
        <ExperimentForm disabled={running} onSubmit={onSubmit} />
      </aside>

      <section className="flex min-h-0 flex-col gap-4 p-4">
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="min-h-0 flex-1">
          <LiveRun key={current} jobId={current} onStop={onStop} />
        </div>

        <div className="max-h-56 overflow-auto rounded-md border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-zinc-100 text-zinc-500 dark:bg-zinc-900">
              <tr>
                <th className="px-3 py-2">Started</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Algorithms</th>
                <th className="px-3 py-2">Workload</th>
                <th className="px-3 py-2">Storage</th>
                <th className="px-3 py-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-zinc-500">
                    No experiments yet.
                  </td>
                </tr>
              )}
              {history.map((j) => (
                <tr
                  key={j.id}
                  onClick={() => setSelected(j.id)}
                  className={`cursor-pointer border-t border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900 ${
                    j.id === current ? "bg-zinc-100 dark:bg-zinc-900" : ""
                  }`}
                >
                  <td className="px-3 py-2">{new Date(j.started_at * 1000).toLocaleString()}</td>
                  <td className="px-3 py-2 capitalize">{j.status}</td>
                  <td className="px-3 py-2">{j.request.algorithms.join(", ")}</td>
                  <td className="px-3 py-2">{j.request.workload_type}</td>
                  <td className="px-3 py-2">{j.request.storage_limit_mb} MB</td>
                  <td className="px-3 py-2 tabular-nums">{fmtDuration(j)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
