"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { lastQuery, loadQueries } from "@/lib/queryList";

const ITEMS = [
  { href: "/", label: "Home" },
  { href: "/experiments", label: "Experiments" },
  { href: "/queries", label: "Queries", sub: true },
  { href: "/overview", label: "Plan overview" },
  { href: "/playground", label: "Playground" },
  { href: "/results", label: "Results" },
  { href: "/settings", label: "Settings" },
];

const linkClass = (active: boolean, extra: string) =>
  `rounded-md ${extra} ${
    active
      ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
  }`;

export default function Sidebar() {
  const pathname = usePathname();
  // Explorer/Compare need a query: the one on screen, else the last one visited, else the first.
  const onQuery = /^\/queries\/([^/]+)/.exec(pathname)?.[1];
  const [fallback, setFallback] = useState<string | null>(null);
  useEffect(() => {
    if (onQuery) return;
    // Async on purpose: state is set from the promise, not synchronously in the effect.
    Promise.resolve(lastQuery())
      .then((last) => last ?? loadQueries().then((qs) => qs[0]?.id ?? null))
      .then(setFallback)
      .catch(() => undefined);
  }, [onQuery]);
  const queryId = onQuery ?? fallback;
  const base = queryId ? `/queries/${queryId}` : "/queries";

  const subItems = [
    { href: "/queries", label: "All queries", active: pathname === "/queries" },
    { href: base, label: "Explorer", active: pathname === base || (!!onQuery && !pathname.endsWith("/compare")) },
    { href: `${base}/compare`, label: "Compare", active: pathname.endsWith("/compare") },
  ];

  return (
    <nav className="flex w-52 shrink-0 flex-col gap-1 border-r border-zinc-200 p-3 dark:border-zinc-800">
      <div className="px-3 py-2 text-sm font-semibold">MV Optimization</div>
      {ITEMS.map(({ href, label, sub }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        if (!sub) {
          return (
            <Link key={href} href={href} className={linkClass(active, "px-3 py-2 text-sm")}>
              {label}
            </Link>
          );
        }
        return (
          <div key={href} className="flex flex-col gap-0.5">
            <span
              className={`px-3 py-2 text-sm ${active ? "font-medium text-zinc-900 dark:text-zinc-100" : "text-zinc-600 dark:text-zinc-400"}`}
            >
              {label}
            </span>
            {subItems.map((it) => (
              <Link
                key={it.label}
                href={it.href}
                className={linkClass(it.active, "ml-3 px-3 py-1.5 text-xs")}
                title={it.label === "All queries" ? undefined : queryId ? `Query ${queryId}` : undefined}
              >
                {it.label}
                {it.label !== "All queries" && queryId && (
                  <span className="ml-1.5 opacity-60">{queryId}</span>
                )}
              </Link>
            ))}
          </div>
        );
      })}
    </nav>
  );
}
