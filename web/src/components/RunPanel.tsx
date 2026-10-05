"use client";

import LogConsole from "./LogConsole";
import { PHASES } from "./ExperimentForm";
import type { JobSummary } from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  running: "bg-blue-500",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
  stopped: "bg-amber-500",
};

export default function RunPanel({
  summary,
  logs,
  error,
  onStop,
}: {
  summary: JobSummary | null;
  logs: string[];
  error: string | null;
  onStop: () => void;
}) {
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!summary) return <p className="text-sm text-zinc-500">Select or start an experiment.</p>;

  const p = summary.progress;
  const enabled = new Set(summary.request.phases);
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex items-center gap-3 text-sm">
        <span className={`h-2 w-2 rounded-full ${STATUS_STYLE[summary.status]}`} />
        <span className="font-medium capitalize">{summary.status}</span>
        <span className="text-zinc-500">
          {p.current_algorithm ?? "starting…"} · algorithm {Math.min(p.algorithms_done + 1, p.total_algorithms)}/
          {p.total_algorithms}
        </span>
        {summary.status === "running" && (
          <button
            onClick={onStop}
            className="ml-auto rounded-md border border-red-400 px-2 py-0.5 text-xs text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
          >
            Stop
          </button>
        )}
      </div>

      <div>
        <div className="h-2 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
          <div
            className="h-2 bg-blue-500 transition-[width] duration-500"
            style={{ width: `${p.progress}%` }}
          />
        </div>
        <div className="mt-1 text-right text-xs tabular-nums text-zinc-500">{p.progress.toFixed(1)}%</div>
      </div>

      <ol className="flex flex-wrap gap-2 text-xs">
        {PHASES.map(([key, label], i) => {
          const active = p.current_phase === key && summary.status === "running";
          const done = p.phase_step > i + 1 || (p.phase_progress[key] ?? 0) >= 100;
          return (
            <li
              key={key}
              className={`rounded-full border px-2 py-0.5 ${
                !enabled.has(key)
                  ? "border-dashed border-zinc-300 text-zinc-400 line-through dark:border-zinc-700"
                  : active
                    ? "border-blue-500 text-blue-600"
                    : done
                      ? "border-emerald-500 text-emerald-600"
                      : "border-zinc-300 text-zinc-500 dark:border-zinc-700"
              }`}
            >
              {label}
              {active && p.phase_progress[key] ? ` ${p.phase_progress[key].toFixed(0)}%` : ""}
            </li>
          );
        })}
      </ol>

      <div className="min-h-0 flex-1">
        <LogConsole lines={logs} />
      </div>
    </div>
  );
}
