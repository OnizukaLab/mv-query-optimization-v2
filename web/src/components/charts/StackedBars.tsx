"use client";

import { useState } from "react";
import { fmtSeconds } from "@/lib/format";

export interface Segment {
  key: string;
  label: string;
  color: string;
}

export interface StackRow {
  label: string;
  values: Record<string, number>;
}

/** Horizontal stacked bars (shared scale) with 2px surface gaps between segments. */
export default function StackedBars({ rows, segments }: { rows: StackRow[]; segments: Segment[] }) {
  const [hover, setHover] = useState<{ row: string; seg: Segment; value: number } | null>(null);
  const totals = rows.map((r) => segments.reduce((a, s) => a + (r.values[s.key] ?? 0), 0));
  const max = Math.max(...totals, 1e-9);
  return (
    <div className="relative flex flex-col gap-2">
      {rows.map((r, i) => (
        <div key={r.label} className="grid grid-cols-[8rem_1fr] items-center gap-3">
          <span className="truncate text-xs text-[var(--text-secondary)]">{r.label}</span>
          <div className="flex h-8 items-center gap-2">
            <div className="flex h-5 gap-[2px]" style={{ width: `calc(${(totals[i] / max) * 100}% - 4.5rem)` }}>
              {segments.map((s) => {
                const v = r.values[s.key] ?? 0;
                if (v <= 0) return null;
                return (
                  <div
                    key={s.key}
                    className="min-w-[2px] first:rounded-l-[4px] last:rounded-r-[4px]"
                    style={{ flexGrow: v, flexBasis: 0, background: s.color }}
                    onMouseEnter={() => setHover({ row: r.label, seg: s, value: v })}
                    onMouseLeave={() => setHover(null)}
                  />
                );
              })}
            </div>
            <span className="text-xs tabular-nums">{fmtSeconds(totals[i])}</span>
          </div>
        </div>
      ))}
      <div className="h-4 text-xs text-[var(--text-secondary)]">
        {hover && (
          <>
            <b>{hover.row}</b> · {hover.seg.label}: {fmtSeconds(hover.value)}
          </>
        )}
      </div>
    </div>
  );
}
