import type { PlanNode } from "@/lib/plan";
import NodeDetails from "./NodeDetails";
import { costChange, type NodeDiff, type PlanDiff } from "@/lib/planDiff";

const FIELDS = [
  "Relation Name",
  "Alias",
  "Index Name",
  "Join Type",
  "Hash Cond",
  "Merge Cond",
  "Join Filter",
  "Index Cond",
  "Filter",
  "Startup Cost",
  "Total Cost",
  "Plan Rows",
  "Plan Width",
  "Actual Rows",
  "Actual Loops",
  "Actual Total Time",
] as const;

function fmt(v: unknown): string {
  return typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v);
}

export default function NodePanel({
  node,
  nodeDiff,
  diff,
  candidateId,
  candidateNote,
  queryId,
  whatIfNodes,
  onWhatIf,
}: {
  node: PlanNode | null;
  nodeDiff?: NodeDiff;
  diff: PlanDiff | null;
  /** workload node id (MV candidate) of the selected node, when known */
  candidateId?: string | null;
  /** why candidate info is unavailable, when it is */
  candidateNote?: string | null;
  queryId?: string;
  whatIfNodes?: string[];
  onWhatIf?: (nodeId: string) => void;
}) {
  if (!node) {
    return (
      <div className="p-4 text-xs text-zinc-500">
        <p>Click a node to inspect it.</p>
        {diff && <DiffSummary diff={diff} />}
      </div>
    );
  }
  const change = costChange(nodeDiff?.prevCost, node["Total Cost"]);
  return (
    <div className="p-4 text-xs">
      <h2 className="text-sm font-semibold">{node["Node Type"]}</h2>
      {nodeDiff && (
        <p className="mt-1 text-zinc-500">
          {nodeDiff.status === "new" ? "New in this plan" : nodeDiff.status === "moved" ? "Moved vs baseline" : "Same position as baseline"}
          {change !== null && Math.abs(change) >= 0.01 && ` · cost ${nodeDiff.prevCost!.toFixed(0)} → ${node["Total Cost"].toFixed(0)}`}
        </p>
      )}
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        {FIELDS.filter((k) => node[k] !== undefined).map((k) => (
          <div key={k} className="contents">
            <dt className="text-zinc-500">{k}</dt>
            <dd className="break-words font-mono tabular-nums">{fmt(node[k])}</dd>
          </div>
        ))}
      </dl>
      {candidateId ? (
        <NodeDetails
          key={candidateId}
          nodeId={candidateId}
          currentQueryId={queryId}
          inWhatIf={whatIfNodes?.includes(candidateId)}
          onWhatIf={onWhatIf}
        />
      ) : (
        candidateNote && <p className="mt-4 text-[11px] text-zinc-500">{candidateNote}</p>
      )}
    </div>
  );
}

function DiffSummary({ diff }: { diff: PlanDiff }) {
  const counts = { same: 0, moved: 0, new: 0 };
  diff.nodes.forEach((d) => counts[d.status]++);
  return (
    <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
      <div className="font-medium text-zinc-700 dark:text-zinc-300">Changes vs baseline</div>
      <p className="mt-1">
        {counts.same} unchanged · {counts.moved} moved · {counts.new} new · {diff.removed.length} removed
      </p>
      {diff.removed.length > 0 && (
        <ul className="mt-2 list-disc pl-4">
          {diff.removed.map((n, i) => (
            <li key={i}>
              {n["Node Type"]}
              {n["Relation Name"] ? ` on ${n["Relation Name"]}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
