"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import NodePanel from "./NodePanel";
import PlanGraph, { type DiffWording } from "./PlanGraph";
import {
  ApiError,
  fetchMvPlan,
  listMvSets,
  type MvPlan,
  type MvSet,
  type PlanResponse,
} from "@/lib/api";
import { fmtBytes, fmtSeconds } from "@/lib/format";
import { costChange, diffPlans, nodeById } from "@/lib/planDiff";

const CUSTOM = "custom";

// Stable references: a new object per render would rebuild the graph nodes every time.
const ORIGINAL_WORDING: DiffWording = { new: "replaced", moved: null };
const MV_WORDING: DiffWording = { moved: null };

type Selection = { side: "original" | "mv"; id: string } | null;

function pct(change: number | null) {
  if (change === null) return null;
  return (
    <span className={change < 0 ? "text-emerald-600" : "text-red-600"}>
      {change > 0 ? "+" : ""}
      {(change * 100).toFixed(0)}%
    </span>
  );
}

/** Original plan next to the plan after rewriting onto a set of MVs (created transiently). */
export default function MvCompare({
  queryId,
  originalPlan,
  customNodes,
  onCustomNodes,
}: {
  queryId: string;
  originalPlan: PlanResponse | null;
  customNodes: string[];
  onCustomNodes: (nodes: string[]) => void;
}) {
  const [sets, setSets] = useState<MvSet[] | null>(null);
  const [source, setSource] = useState<string>(customNodes.length ? CUSTOM : "");
  const [result, setResult] = useState<MvPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsConfirm, setNeedsConfirm] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState<Selection>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listMvSets(queryId)
      .then((s) => {
        setSets(s);
        // Default to the selection that materializes the most for this query (newest on ties).
        const richest = s.reduce((best, x, i) => (x.node_ids.length > (s[best]?.node_ids.length ?? 0) ? i : best), 0);
        setSource((cur) => cur || (s.length ? String(richest) : CUSTOM));
      })
      .catch((e: Error) => setError(e.message));
  }, [queryId]);

  const chosen: MvSet | null = source !== CUSTOM && sets ? (sets[Number(source)] ?? null) : null;
  const nodeIds = source === CUSTOM ? customNodes : (chosen?.node_ids ?? []);
  const nodeKey = nodeIds.join(",");

  const run = useCallback(
    async (opts: { confirm?: boolean; force?: boolean } = {}) => {
      if (!nodeKey) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setError(null);
      setNeedsConfirm(null);
      try {
        const r = await fetchMvPlan(
          queryId,
          { node_ids: nodeKey.split(","), confirm_large: opts.confirm, force: opts.force },
          ctrl.signal,
        );
        if (!ctrl.signal.aborted) setResult(r);
      } catch (e) {
        if (ctrl.signal.aborted) return;
        if (e instanceof ApiError && e.status === 409 && (e.detail as { code?: string })?.code === "large_mv") {
          setNeedsConfirm((e.detail as { size_bytes: number }).size_bytes);
        } else {
          setError((e as Error).message);
        }
      } finally {
        if (abortRef.current === ctrl) setLoading(false);
      }
    },
    [queryId, nodeKey],
  );

  // (Re)plan whenever the chosen MV set changes.
  useEffect(() => {
    if (!sets && source !== CUSTOM) return;
    if (!nodeKey) return;
    const t = setTimeout(() => void run(), 0);
    return () => clearTimeout(t);
  }, [nodeKey, sets, source, run]);

  const shown = result && result.node_ids.join(",") === nodeKey ? result : null;
  const mvDiff = useMemo(
    () => (shown && originalPlan ? diffPlans(originalPlan.plan, shown.plan) : null),
    [shown, originalPlan],
  );
  const origDiff = useMemo(
    () => (shown && originalPlan ? diffPlans(shown.plan, originalPlan.plan) : null),
    [shown, originalPlan],
  );

  const selectedNode =
    selection && (selection.side === "original" ? originalPlan?.plan : shown?.plan)
      ? nodeById((selection.side === "original" ? originalPlan : shown)!.plan, selection.id)
      : null;

  const costDelta = shown && originalPlan ? costChange(originalPlan.plan["Total Cost"], shown.plan["Total Cost"]) : null;
  const m = chosen?.measured;
  const measuredDelta = m?.baseline_s && m.with_mvs_s ? (m.with_mvs_s - m.baseline_s) / m.baseline_s : null;
  const createTotal = shown?.mvs.reduce((a, v) => a + v.create_seconds, 0) ?? 0;

  return (
    <div className="grid min-h-0 grid-cols-[1fr_320px]">
      <div className="flex min-h-0 min-w-0 flex-col">
        <div className="flex flex-wrap items-center gap-3 border-b border-zinc-200 px-3 py-2 text-xs dark:border-zinc-800">
          <label className="flex items-center gap-2">
            MV set
            <select
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setSelection(null);
              }}
              className="max-w-xs rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
            >
              {(sets ?? []).map((s, i) => (
                <option key={`${s.set_id}/${s.algorithm}`} value={String(i)} className="text-black">
                  {s.algorithm} · {s.set_id === "_root" ? "latest run" : s.set_id} ({s.node_ids.length} MVs)
                </option>
              ))}
              <option value={CUSTOM} className="text-black">
                Custom selection ({customNodes.length})
              </option>
            </select>
          </label>
          {source === CUSTOM && (
            <span className="flex flex-wrap items-center gap-1">
              {customNodes.length === 0 && (
                <span className="text-zinc-500">
                  Select a node in the Original view and choose “Materialize this node”.
                </span>
              )}
              {customNodes.map((n) => (
                <button
                  key={n}
                  onClick={() => onCustomNodes(customNodes.filter((x) => x !== n))}
                  className="rounded border border-zinc-300 px-1.5 py-0.5 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                  title="Remove"
                >
                  {n} ×
                </button>
              ))}
            </span>
          )}
          {shown && (
            <button onClick={() => void run({ force: true })} className="ml-auto rounded border px-2 py-0.5">
              Re-run{shown.cached ? " (cached)" : ""}
            </button>
          )}
        </div>

        {needsConfirm !== null && (
          <div className="border-b border-amber-400 bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
            These MVs are estimated at {fmtBytes(needsConfirm)} and may take minutes to build in a scratch
            schema (rolled back afterwards).{" "}
            <button onClick={() => void run({ confirm: true })} className="ml-2 rounded border border-amber-600 px-2 py-0.5">
              Run anyway
            </button>
          </div>
        )}
        {error && <p className="border-b border-red-300 bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
        {sets && sets.length === 0 && source !== CUSTOM && (
          <p className="p-3 text-xs text-zinc-500">No experiment selected MVs for this query.</p>
        )}

        {shown && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 border-b border-zinc-200 px-3 py-2 text-xs dark:border-zinc-800 md:grid-cols-4">
            <Metric label="Estimated cost">
              {originalPlan ? originalPlan.plan["Total Cost"].toLocaleString(undefined, { maximumFractionDigits: 0 }) : "–"} →{" "}
              {shown.plan["Total Cost"].toLocaleString(undefined, { maximumFractionDigits: 0 })} {pct(costDelta)}
            </Metric>
            <Metric label={chosen ? `Measured (${chosen.algorithm} run)` : "Measured"}>
              {m && (m.baseline_s || m.with_mvs_s) ? (
                <>
                  {fmtSeconds(m.baseline_s)} → {fmtSeconds(m.with_mvs_s)} {pct(measuredDelta)}
                </>
              ) : (
                <span className="text-zinc-500">not recorded</span>
              )}
            </Metric>
            <Metric label="MV build (scratch)">
              {fmtSeconds(createTotal)} · {shown.mvs.length} MV{shown.mvs.length > 1 ? "s" : ""}
            </Metric>
            <Metric label="MVs in plan">
              {shown.mvs.map((v) => (
                <span
                  key={v.node_id}
                  title={`${fmtBytes(v.est_size_bytes)} est. · built in ${fmtSeconds(v.create_seconds)}`}
                  className={`mr-1 inline-block rounded px-1 ${v.used_in_plan ? "bg-emerald-600/20" : "bg-amber-500/30"}`}
                >
                  {v.node_id}
                  {!v.used_in_plan && " (unused)"}
                </span>
              ))}
            </Metric>
          </div>
        )}

        <div className="grid min-h-0 flex-1 grid-cols-2 divide-x divide-zinc-200 dark:divide-zinc-800">
          <Pane title="Original" subtitle={originalPlan ? undefined : "plan not loaded"}>
            {originalPlan && (
              <PlanGraph
                plan={originalPlan.plan}
                diff={origDiff}
                wording={ORIGINAL_WORDING}
                selectedId={selection?.side === "original" ? selection.id : null}
                onSelect={(id) => setSelection(id ? { side: "original", id } : null)}
              />
            )}
          </Pane>
          <Pane title="With MVs" subtitle={loading ? "building MVs in a scratch schema…" : undefined}>
            {shown ? (
              <PlanGraph
                plan={shown.plan}
                diff={mvDiff}
                wording={MV_WORDING}
                selectedId={selection?.side === "mv" ? selection.id : null}
                onSelect={(id) => setSelection(id ? { side: "mv", id } : null)}
              />
            ) : (
              <p className="p-4 text-xs text-zinc-500">{loading ? "Planning…" : "Choose MVs to compare."}</p>
            )}
          </Pane>
        </div>

        {shown && (
          <details className="border-t border-zinc-200 px-3 py-2 text-xs dark:border-zinc-800">
            <summary className="cursor-pointer font-medium">Rewritten SQL</summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded bg-zinc-100 p-2 text-[11px] leading-4 dark:bg-zinc-900">
              {shown.rewritten_sql}
            </pre>
          </details>
        )}
      </div>

      <aside className="overflow-auto border-l border-zinc-200 dark:border-zinc-800">
        <NodePanel node={selectedNode} diff={null} />
      </aside>
    </div>
  );
}

function Pane({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-0 min-w-0 flex-col">
      <div className="px-3 py-1 text-xs font-semibold">
        {title}
        {subtitle && <span className="ml-2 font-normal text-zinc-500">{subtitle}</span>}
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-zinc-500">{label}</div>
      <div className="tabular-nums">{children}</div>
    </div>
  );
}
