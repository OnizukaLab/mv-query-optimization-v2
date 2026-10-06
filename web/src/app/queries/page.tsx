"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listQueries, type QueryInfo } from "@/lib/api";

export default function QueriesPage() {
  const [queries, setQueries] = useState<QueryInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    listQueries().then(setQueries).catch((e: Error) => setError(e.message));
  }, []);

  const families = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const map = new Map<number, QueryInfo[]>();
    (queries ?? [])
      .filter((q) => !f || q.id.includes(f))
      .forEach((q) => map.set(q.family, [...(map.get(q.family) ?? []), q]));
    return [...map.entries()];
  }, [queries, filter]);

  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-semibold">Queries</h1>
        <span className="text-sm text-zinc-500">JOB workload{queries ? ` · ${queries.length} queries` : ""}</span>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by id (e.g. 17)"
          className="ml-auto rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700"
        />
      </div>
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      <div className="mt-6 flex flex-col gap-2">
        {families.map(([family, items]) => (
          <div key={family} className="flex items-center gap-3">
            <span className="w-8 text-right text-xs tabular-nums text-zinc-500">{family}</span>
            <div className="flex flex-wrap gap-2">
              {items.map((q) => (
                <Link
                  key={q.id}
                  href={`/queries/${q.id}`}
                  title={`${q.tables} tables`}
                  className="rounded-md border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                >
                  {q.id}
                  <span className="ml-1.5 text-xs text-zinc-500">{q.tables}</span>
                </Link>
              ))}
            </div>
          </div>
        ))}
        {queries && families.length === 0 && <p className="text-sm text-zinc-500">No matching queries.</p>}
      </div>
      <p className="mt-6 text-xs text-zinc-500">The small number is the table count of the query.</p>
    </div>
  );
}
