"use client";

import { useEffect, useState } from "react";
import {
  experimentEventsUrl,
  getExperiment,
  getExperimentLogs,
  type JobSummary,
} from "./api";

const MAX_LINES = 5000;

/**
 * Follows one experiment: live via SSE while it runs, plain fetch once finished.
 * EventSource reconnects on its own and resumes through Last-Event-ID.
 * State is not reset when ``jobId`` changes: mount the consumer with ``key={jobId}``.
 */
export function useExperimentStream(jobId: string | null) {
  const [summary, setSummary] = useState<JobSummary | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;

    let es: EventSource | null = null;
    let cancelled = false;

    (async () => {
      try {
        const s = await getExperiment(jobId);
        if (cancelled) return;
        setSummary(s);
        if (s.status !== "running") {
          const lines = await getExperimentLogs(jobId);
          if (!cancelled) setLogs(lines.slice(-MAX_LINES));
          return;
        }
        es = new EventSource(experimentEventsUrl(jobId));
        es.addEventListener("log", (e) => {
          const line = JSON.parse((e as MessageEvent).data) as string;
          setLogs((prev) => [...prev.slice(-(MAX_LINES - 1)), line]);
        });
        es.addEventListener("progress", (e) => {
          setSummary(JSON.parse((e as MessageEvent).data) as JobSummary);
        });
        es.addEventListener("done", () => es?.close());
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();

    return () => {
      cancelled = true;
      es?.close();
    };
  }, [jobId]);

  return { summary, logs, error };
}
