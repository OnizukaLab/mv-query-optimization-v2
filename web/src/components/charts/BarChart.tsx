"use client";

import { useState } from "react";
import { fmtSeconds } from "@/lib/format";

export interface Bar {
  label: string;
  value: number;
  color: string;
  note?: string;
}

/** Horizontal bars growing from one baseline; value labelled at the tip. */
export default function BarChart({ bars, unit = fmtSeconds }: { bars: Bar[]; unit?: (v: number) => string }) {
  const [hover, setHover] = useState<string | null>(null);
  const max = Math.max(...bars.map((b) => b.value), 1e-9);
  return (
    <div className="flex flex-col gap-2">
      {bars.map((b) => (
        <div
          key={b.label}
          className="grid grid-cols-[8rem_1fr] items-center gap-3"
          onMouseEnter={() => setHover(b.label)}
          onMouseLeave={() => setHover(null)}
          title={b.note}
        >
          <span className="truncate text-xs text-[var(--text-secondary)]">{b.label}</span>
          <div className="flex h-8 items-center gap-2">
            <div
              className="h-5 rounded-r-[4px] transition-opacity"
              style={{
                width: `max(2px, calc(${(b.value / max) * 100}% - 4.5rem))`,
                background: b.color,
                opacity: hover && hover !== b.label ? 0.45 : 1,
              }}
            />
            <span className="text-xs tabular-nums">{unit(b.value)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
