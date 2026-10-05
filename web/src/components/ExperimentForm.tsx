"use client";

import { useState } from "react";
import type { ExperimentRequest } from "@/lib/api";

export const ALGORITHMS = [
  ["normal", "Normal"],
  ["bigsubs", "BigSubs"],
  ["frequency", "Frequency"],
  ["utility", "Utility"],
  ["utility_capacity", "Utility+Capacity"],
  ["none", "None (baseline)"],
] as const;

export const PHASES = [
  ["query_parsing", "Query parsing"],
  ["optimization", "ILP optimization"],
  ["sql_generation", "SQL generation"],
  ["mv_creation", "MV creation"],
  ["query_rewriting", "Query rewriting"],
  ["benchmark", "Benchmark"],
] as const;

const WORKLOADS = [
  ["redbench-job", "RedBench JOB (83 queries)"],
  ["redbench-ceb", "RedBench CEB"],
  ["redbench", "RedBench full (JOB + CEB)"],
  ["job", "JOB (113 queries)"],
  ["ceb-1a", "CEB 1a (3000 queries)"],
  ["ceb", "CEB (RedBench)"],
] as const;

const DEFAULTS: ExperimentRequest = {
  algorithms: ["normal", "bigsubs", "frequency"],
  phases: PHASES.map(([k]) => k),
  storage_limit_mb: 50,
  insert_queries: 1000,
  workload_type: "redbench-job",
  verbose: false,
};

function toggle(list: string[], key: string) {
  return list.includes(key) ? list.filter((k) => k !== key) : [...list, key];
}

const input =
  "w-full rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700";

export default function ExperimentForm({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (req: ExperimentRequest) => void;
}) {
  const [req, setReq] = useState<ExperimentRequest>(DEFAULTS);
  const valid = req.algorithms.length > 0 && req.phases.length > 0;

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        // keep algorithm/phase order canonical regardless of click order
        onSubmit({
          ...req,
          algorithms: ALGORITHMS.map(([k]) => k as string).filter((k) => req.algorithms.includes(k)),
          phases: PHASES.map(([k]) => k as string).filter((k) => req.phases.includes(k)),
        });
      }}
    >
      <Field label="Workload">
        <select
          className={input}
          value={req.workload_type}
          onChange={(e) => setReq({ ...req, workload_type: e.target.value })}
        >
          {WORKLOADS.map(([k, l]) => (
            <option key={k} value={k} className="text-black">
              {l}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Algorithms">
        <Checks
          items={ALGORITHMS}
          selected={req.algorithms}
          onToggle={(k) => setReq({ ...req, algorithms: toggle(req.algorithms, k) })}
        />
      </Field>

      <Field label="Phases">
        <Checks
          items={PHASES}
          selected={req.phases}
          onToggle={(k) => setReq({ ...req, phases: toggle(req.phases, k) })}
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Storage limit (MB)">
          <input
            type="number"
            min={1}
            className={input}
            value={req.storage_limit_mb}
            onChange={(e) => setReq({ ...req, storage_limit_mb: Number(e.target.value) })}
          />
        </Field>
        <Field label="Insert queries">
          <input
            type="number"
            min={0}
            step={100}
            className={input}
            value={req.insert_queries}
            onChange={(e) => setReq({ ...req, insert_queries: Number(e.target.value) })}
          />
        </Field>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={req.verbose}
          onChange={(e) => setReq({ ...req, verbose: e.target.checked })}
        />
        Verbose logging
      </label>

      <button
        type="submit"
        disabled={disabled || !valid}
        className="rounded-md bg-zinc-900 px-3 py-2 text-sm text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {disabled ? "Experiment running…" : "Run experiment"}
      </button>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-zinc-500">{label}</div>
      {children}
    </div>
  );
}

function Checks({
  items,
  selected,
  onToggle,
}: {
  items: readonly (readonly [string, string])[];
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-1">
      {items.map(([key, label]) => (
        <label key={key} className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={selected.includes(key)} onChange={() => onToggle(key)} />
          {label}
        </label>
      ))}
    </div>
  );
}
