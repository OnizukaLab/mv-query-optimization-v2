import type { PlanNode } from "./plan";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export interface PlanResponse {
  plan: PlanNode;
  planning_time_ms: number | null;
  execution_time_ms: number | null;
  analyzed: boolean;
}

export interface Health {
  api: string;
  database: boolean;
  detail: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const getHealth = () => request<Health>("/health");

export const fetchPlan = (sql: string, analyze: boolean) =>
  request<PlanResponse>("/plans", {
    method: "POST",
    body: JSON.stringify({ sql, analyze }),
  });

export type JobStatus = "running" | "completed" | "failed" | "stopped";

export interface ExperimentRequest {
  algorithms: string[];
  phases: string[];
  storage_limit_mb: number;
  insert_queries: number;
  workload_type: string;
  verbose: boolean;
}

export interface JobProgress {
  progress: number;
  current_algorithm: string | null;
  algorithms_done: number;
  total_algorithms: number;
  current_phase: string | null;
  phase_step: number;
  phase_progress: Record<string, number>;
}

export interface JobSummary {
  id: string;
  status: JobStatus;
  started_at: number;
  finished_at: number | null;
  return_code: number | null;
  request: ExperimentRequest;
  progress: JobProgress;
  log_lines: number;
}

export const startExperiment = (req: ExperimentRequest) =>
  request<JobSummary>("/experiments", { method: "POST", body: JSON.stringify(req) });

export const listExperiments = () => request<JobSummary[]>("/experiments");

export const getExperiment = (id: string) => request<JobSummary>(`/experiments/${id}`);

export const stopExperiment = (id: string) =>
  request<JobSummary>(`/experiments/${id}/stop`, { method: "POST" });

export async function getExperimentLogs(id: string): Promise<string[]> {
  const res = await fetch(`${API_URL}/experiments/${id}/logs`);
  if (!res.ok) throw new Error(`Failed to load logs (${res.status})`);
  const text = await res.text();
  return text ? text.split("\n") : [];
}

export const experimentEventsUrl = (id: string) => `${API_URL}/experiments/${id}/events`;
