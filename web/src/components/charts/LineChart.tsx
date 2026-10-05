"use client";

import { useState } from "react";

export interface Line {
  label: string;
  color: string;
  /** y per x category; null = no data */
  values: (number | null)[];
}

const W = 720;
const H = 260;
const M = { top: 12, right: 32, bottom: 32, left: 48 };

/** Lines (2px) with 8px ringed markers over shared x categories. Hover a marker for its value. */
export default function LineChart({
  categories,
  lines,
  format,
  yLabel,
}: {
  categories: string[];
  lines: Line[];
  format: (v: number) => string;
  yLabel: string;
}) {
  const [hover, setHover] = useState<{ line: Line; i: number } | null>(null);
  const all = lines.flatMap((l) => l.values.filter((v): v is number => v != null));
  const yMax = niceMax(Math.max(...all, 1e-9));
  const x = (i: number) =>
    M.left + (categories.length === 1 ? 0.5 : i / (categories.length - 1)) * (W - M.left - M.right);
  const y = (v: number) => M.top + (1 - v / yMax) * (H - M.top - M.bottom);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * yMax);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={yLabel}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} />
            <text x={M.left - 8} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)">
              {format(t)}
            </text>
          </g>
        ))}
        {categories.map((c, i) => (
          <text key={c} x={x(i)} y={H - 10} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
            {c}
          </text>
        ))}
        {lines.map((l) => {
          const pts = l.values.map((v, i) => (v == null ? null : ([x(i), y(v)] as const)));
          const path = pts
            .map((p, i) => (p ? `${pts[i - 1] ? "L" : "M"}${p[0]},${p[1]}` : ""))
            .join(" ");
          return (
            <g key={l.label} opacity={hover && hover.line !== l ? 0.35 : 1}>
              <path d={path} fill="none" stroke={l.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {pts.map(
                (p, i) =>
                  p && (
                    <g key={i} onMouseEnter={() => setHover({ line: l, i })} onMouseLeave={() => setHover(null)}>
                      <circle cx={p[0]} cy={p[1]} r={12} fill="transparent" />
                      <circle cx={p[0]} cy={p[1]} r={4} fill={l.color} stroke="var(--surface-1)" strokeWidth={2} />
                    </g>
                  ),
              )}
            </g>
          );
        })}
      </svg>
      <div className="h-4 text-xs text-[var(--text-secondary)]">
        {hover && hover.line.values[hover.i] != null && (
          <>
            <b>{hover.line.label}</b> · {categories[hover.i]}: {format(hover.line.values[hover.i]!)}
          </>
        )}
      </div>
    </div>
  );
}

function niceMax(v: number): number {
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}
