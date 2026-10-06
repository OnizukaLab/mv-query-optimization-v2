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

/** HTTP error carrying the status and FastAPI's `detail` (string or structured). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string" ? detail : (detail?.message ?? `Request failed (${res.status})`);
    throw new ApiError(message, res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const getHealth = () => request<Health>("/health");

export const fetchPlan = (sql: string, analyze: boolean, signal?: AbortSignal) =>
  request<PlanResponse>("/plans", {
    method: "POST",
    body: JSON.stringify({ sql, analyze, timeout_s: analyze ? 120 : 15 }),
    signal,
  });

export interface QueryInfo {
  id: string;
  family: number;
  tables: number;
}

export const listQueries = () => request<QueryInfo[]>("/queries");

export const getQuery = (id: string) =>
  request<{ id: string; sql: string }>(`/queries/${encodeURIComponent(id)}`);

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
  /** Result set (``Output/runs/<run_id>``) this experiment writes to; absent on jobs from before per-run directories. */
  run_id?: string;
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

/** Conditions a run was started with (absent for results written before per-run directories). */
export interface RunManifest {
  status: "running" | "completed" | "failed";
  created_at: number;
  finished_at: number | null;
  git_commit: string | null;
  /** `id` is a content hash of the query files: equal ids mean the same workload. */
  workload: { id: string; label: string; num_queries: number; query_selection_mode: string | null };
  params: { storage_limit_bytes?: number; insert_queries?: number; algorithms?: string[]; phases?: string[] };
}

export interface ResultSet {
  id: string;
  name: string;
  kind: "run" | "legacy";
  algorithms: string[];
  updated_at: number;
  manifest: RunManifest | null;
}

export interface GroupStats {
  total_queries: number;
  successful: number;
  failed: number;
  total_time: number;
  avg_time: number;
}

export interface AlgorithmResult {
  name: string;
  summary: {
    total_execution_time: number;
    phases: Record<string, number>;
    timestamp?: string;
  } | null;
  benchmark: {
    workload_type?: string;
    total_queries: number;
    successful: number;
    failed: number;
    total_time: number;
    avg_time_per_query: number;
    warmup_enabled?: boolean;
    group_results?: Record<string, GroupStats>;
  } | null;
  optimization: {
    num_selected_views?: number;
    total_storage_mb?: number;
    total_utility?: number;
    execution_time?: number;
  } | null;
  speedup_vs_baseline: number | null;
}

export interface Comparison {
  id: string;
  kind: "run" | "legacy";
  manifest: RunManifest | null;
  algorithms: AlgorithmResult[];
  baseline: string | null;
  warnings: string[];
}

export const listResultSets = () => request<ResultSet[]>("/results/sets");

export const compareResultSet = (id: string) =>
  request<Comparison>(`/results/sets/${encodeURIComponent(id)}/compare`);

export interface SelectedNodes {
  /** False when the stored result was made with a different node numbering than the current workload. */
  consistent: boolean;
  count: number;
  node_ids: string[];
  /** Nodes each query actually uses (query id -> node ids); a selected node is not used by every query containing it. */
  used: Record<string, string[]>;
}

/** MV-candidate node ids each algorithm of a result set selected, keyed by algorithm name. */
export const getSelectedNodes = (setId: string) =>
  request<Record<string, SelectedNodes>>(`/results/sets/${encodeURIComponent(setId)}/selected`);

export interface Snapshot {
  plan: PlanNode;
  shared_counts: Record<string, number>;
}

export const getSnapshot = (queryId: string) =>
  request<Snapshot>(`/queries/${encodeURIComponent(queryId)}/snapshot`);

export interface NodeDetails {
  node_id: string;
  kind: "leaf" | "non_leaf" | null;
  operator: string | null;
  table: string | null;
  alias: string | null;
  filter: string | null;
  children: string[] | null;
  cost: number | null;
  size_bytes: number;
  width: number | null;
  maintenance_cost: number;
  total_utility: number;
  queries: { id: string; occurrences: number; utility: number }[];
  mv_sql: string | null;
}

export const getNode = (nodeId: string) => request<NodeDetails>(`/nodes/${encodeURIComponent(nodeId)}`);

export interface MvSet {
  set_id: string;
  algorithm: string;
  node_ids: string[];
  updated_at: number;
  measured: { with_mvs_s: number | null; baseline_s: number | null };
}

export const listMvSets = (queryId: string) =>
  request<MvSet[]>(`/queries/${encodeURIComponent(queryId)}/mv-sets`);

export interface MvPlan {
  query_id: string;
  node_ids: string[];
  rewritten_sql: string;
  plan: PlanNode;
  analyzed: boolean;
  planning_time_ms: number | null;
  execution_time_ms: number | null;
  computed_at: number;
  cached: boolean;
  mvs: {
    node_id: string;
    create_seconds: number;
    est_size_bytes: number;
    referenced_in_sql: boolean;
    used_in_plan: boolean;
  }[];
}

export const fetchMvPlan = (
  queryId: string,
  body: { node_ids: string[]; analyze?: boolean; confirm_large?: boolean; force?: boolean },
  signal?: AbortSignal,
) =>
  request<MvPlan>(`/queries/${encodeURIComponent(queryId)}/mv-plan`, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });

export interface MvEstimate {
  node_id: string;
  rows: number | null;
  width: number | null;
  est_bytes: number;
  source: "planner" | "model";
}

export const getNodeEstimate = (nodeId: string) =>
  request<MvEstimate>(`/nodes/${encodeURIComponent(nodeId)}/estimate`);

export interface NodeWhatIf {
  node_id: string;
  analyzed: boolean;
  computed_at: number;
  cached: boolean;
  truncated: boolean;
  mv: { node_id: string; create_seconds: number; actual_size_bytes: number; est_size_bytes: number };
  total_cost_before: number;
  total_cost_after: number;
  queries: {
    query_id: string;
    cost_before: number;
    cost_after: number;
    time_before_ms: number | null;
    time_after_ms: number | null;
    uses_mv: boolean;
  }[];
}

export const runNodeWhatIf = (
  nodeId: string,
  body: { analyze?: boolean; confirm_large?: boolean; force?: boolean },
) =>
  request<NodeWhatIf>(`/nodes/${encodeURIComponent(nodeId)}/whatif`, {
    method: "POST",
    body: JSON.stringify(body),
  });
