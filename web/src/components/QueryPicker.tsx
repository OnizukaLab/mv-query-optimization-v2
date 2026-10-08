"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { QueryInfo } from "@/lib/api";
import type { ChangeVerdict } from "@/lib/planChanges";
import { loadQueries } from "@/lib/queryList";

/** Compact per-query marker: whether the rewrite changed the join order. */
const MARKS: Record<ChangeVerdict | "pending", { glyph: string; className: string; label: string }> = {
  changed: { glyph: "●", className: "text-violet-500", label: "join order changed" },
  same: { glyph: "○", className: "text-zinc-400", label: "join order unchanged" },
  none: { glyph: "·", className: "text-zinc-300 dark:text-zinc-700", label: "no MV selected for this query" },
  unknown: { glyph: "?", className: "text-amber-500", label: "needs a large MV (open the query to confirm)" },
  failed: { glyph: "✕", className: "text-red-500", label: "rewrite failed" },
  pending: { glyph: "…", className: "text-zinc-400", label: "checking" },
};

/**
 * Query switcher: searchable list plus previous/next arrows. Navigation keeps the current
 * sub-page (`suffix`, e.g. "/compare"), so switching queries never drops you back to Explorer.
 */
export default function QueryPicker({
  queryId,
  suffix = "",
  marks,
}: {
  queryId: string;
  suffix?: string;
  /** Per-query verdict for the selected experiment/algorithm; undefined while still being computed. */
  marks?: (queryId: string) => ChangeVerdict | undefined;
}) {
  const router = useRouter();
  const [queries, setQueries] = useState<QueryInfo[]>([]);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [cursor, setCursor] = useState(0);
  const [changedOnly, setChangedOnly] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadQueries().then(setQueries).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const href = (id: string) => `/queries/${encodeURIComponent(id)}${suffix}`;
  const idx = queries.findIndex((q) => q.id === queryId);
  const prevQ = idx > 0 ? queries[idx - 1] : null;
  const nextQ = idx >= 0 && idx < queries.length - 1 ? queries[idx + 1] : null;

  const matches = useMemo(() => {
    const f = filter.trim().toLowerCase();
    // "17" lists the whole family 17 (17a, 17b, ...); "17a" narrows to prefix matches.
    return queries.filter((q) => (!f || q.id.startsWith(f)) && (!changedOnly || marks?.(q.id) === "changed"));
  }, [queries, filter, changedOnly, marks]);

  const markOf = (id: string) => MARKS[marks?.(id) ?? "pending"];
  const counts = marks
    ? queries.reduce(
        (c, q) => {
          const v = marks(q.id);
          if (v === "changed") c.changed++;
          else if (v === undefined) c.pending++;
          return c;
        },
        { changed: 0, pending: 0 },
      )
    : null;

  const choose = (id: string) => {
    setOpen(false);
    setFilter("");
    router.push(href(id));
  };

  return (
    <span className="flex items-center gap-1">
      <span ref={rootRef} className="relative">
        <button
          onClick={() => {
            setOpen((o) => !o);
            setCursor(0);
          }}
          className="flex items-center gap-1 rounded border border-zinc-300 px-2 py-0.5 text-sm font-semibold dark:border-zinc-700"
          title="Choose a query"
        >
          {queryId}
          {marks && (
            <span className={`text-xs ${markOf(queryId).className}`} title={markOf(queryId).label}>
              {markOf(queryId).glyph}
            </span>
          )}
          <span className="text-xs text-zinc-500">▾</span>
        </button>
        {open && (
          <div className="absolute left-0 top-full z-30 mt-1 w-64 rounded-md border border-zinc-300 bg-white p-2 text-sm shadow-lg dark:border-zinc-700 dark:bg-zinc-950">
            <input
              autoFocus
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setCursor(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setCursor((c) => Math.min(c + 1, matches.length - 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setCursor((c) => Math.max(c - 1, 0));
                } else if (e.key === "Enter" && matches[cursor]) {
                  choose(matches[cursor].id);
                } else if (e.key === "Escape") {
                  setOpen(false);
                }
              }}
              placeholder="Search id (e.g. 17 or 17a)"
              className="w-full rounded border border-zinc-300 bg-transparent px-2 py-1 text-xs dark:border-zinc-700"
            />
            {marks && counts && (
              <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} />
                  changed only
                </label>
                <span>
                  {counts.changed} changed{counts.pending > 0 && ` · ${counts.pending} checking`}
                </span>
              </div>
            )}
            <ul className="mt-2 max-h-72 overflow-auto">
              {matches.map((q, i) => (
                <li key={q.id}>
                  <button
                    onClick={() => choose(q.id)}
                    onMouseEnter={() => setCursor(i)}
                    ref={(el) => {
                      if (el && i === cursor) el.scrollIntoView({ block: "nearest" });
                    }}
                    className={`flex w-full items-center justify-between rounded px-2 py-1 text-left ${
                      i === cursor ? "bg-zinc-100 dark:bg-zinc-900" : ""
                    } ${q.id === queryId ? "font-semibold" : ""}`}
                  >
                    {q.id}
                    <span className="flex items-center gap-2 text-xs text-zinc-500">
                      {q.tables}
                      {marks && (
                        <span className={`w-3 text-center ${markOf(q.id).className}`} title={markOf(q.id).label}>
                          {markOf(q.id).glyph}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
              {queries.length > 0 && matches.length === 0 && (
                <li className="px-2 py-1 text-xs text-zinc-500">No matching queries.</li>
              )}
            </ul>
            {marks && (
              <p className="mt-2 border-t border-zinc-200 pt-1 text-[10px] text-zinc-500 dark:border-zinc-800">
                <span className="text-violet-500">●</span> join order changed · ○ same · ? large MV · ✕ failed · … checking
              </p>
            )}
          </div>
        )}
      </span>
      {prevQ ? (
        <Link href={href(prevQ.id)} className="rounded border px-1.5 text-xs" title={prevQ.id}>
          ←
        </Link>
      ) : null}
      {nextQ ? (
        <Link href={href(nextQ.id)} className="rounded border px-1.5 text-xs" title={nextQ.id}>
          →
        </Link>
      ) : null}
    </span>
  );
}
