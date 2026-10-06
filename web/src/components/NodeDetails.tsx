"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import NodeWhatIf from "./NodeWhatIf";
import { getNode, getNodeEstimate, type MvEstimate, type NodeDetails as Details } from "@/lib/api";
import { fmtBytes, fmtNumber } from "@/lib/format";

/** MV-candidate view of a plan node. Mount with key={nodeId} so state resets per node. */
export default function NodeDetails({
  nodeId,
  currentQueryId,
  inWhatIf,
  onWhatIf,
}: {
  nodeId: string;
  currentQueryId?: string;
  inWhatIf?: boolean;
  onWhatIf?: (nodeId: string) => void;
}) {
  const [d, setD] = useState<Details | null>(null);
  const [est, setEst] = useState<MvEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getNode(nodeId)
      .then((r) => !cancelled && setD(r))
      .catch((e: Error) => !cancelled && setError(e.message));
    getNodeEstimate(nodeId)
      .then((r) => !cancelled && setEst(r))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  if (error) return <p className="mt-4 text-xs text-red-600">{error}</p>;
  if (!d) return <p className="mt-4 text-xs text-zinc-500">Loading candidate…</p>;

  const target = d.table ? `${d.table}${d.alias ? ` AS ${d.alias}` : ""}` : d.children ? `join of ${d.children.join(", ")}` : "";
  return (
    <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
      <div className="flex items-baseline gap-2">
        <h3 className="text-sm font-semibold">MV candidate</h3>
        <code className="text-zinc-500">{d.node_id}</code>
      </div>
      {target && <p className="mt-1 break-words text-zinc-500">{target}</p>}

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
        <Stat label="Subtree cost" value={fmtNumber(d.cost, 0)} />
        <Stat label={est?.source === "planner" ? "Est. size (planner)" : "Est. size (model)"} value={fmtBytes(est?.est_bytes ?? d.size_bytes)} />
        <Stat label="Maintenance cost" value={fmtNumber(d.maintenance_cost, 1)} />
        <Stat label="Model utility (Σ)" value={fmtNumber(d.total_utility, 0)} />
      </dl>
      <p className="mt-1 text-[11px] text-zinc-500">
        Model values from the ILP inputs (planner cost units); a real what-if comes from running the MV.
      </p>

      <NodeWhatIf nodeId={nodeId} currentQueryId={currentQueryId} />
      {onWhatIf && (
        <button
          onClick={() => onWhatIf(nodeId)}
          className="mt-2 w-full rounded-md border border-zinc-400 px-2 py-1 text-xs hover:bg-zinc-100 dark:hover:bg-zinc-900"
        >
          {inWhatIf ? "Remove from this query's comparison" : "Compare plans for this query with this MV"}
        </button>
      )}

      <h3 className="mt-4 text-sm font-semibold">Shared by {d.queries.length} queries</h3>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {d.queries.map((q) => (
          <li key={q.id}>
            <Link
              href={`/queries/${q.id}?node=${encodeURIComponent(d.node_id)}`}
              title={`utility ${fmtNumber(q.utility, 0)}${q.occurrences > 1 ? ` · ${q.occurrences}× in query` : ""}`}
              className={`rounded border px-1.5 py-0.5 ${
                q.id === currentQueryId
                  ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                  : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
              }`}
            >
              {q.id}
              {q.occurrences > 1 && <sup className="ml-0.5">{q.occurrences}</sup>}
            </Link>
          </li>
        ))}
      </ul>

      {d.mv_sql && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-semibold">MV definition</summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded bg-zinc-100 p-2 text-[11px] leading-4 dark:bg-zinc-900">
            {d.mv_sql}
          </pre>
        </details>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="font-mono tabular-nums">{value}</dd>
    </div>
  );
}
