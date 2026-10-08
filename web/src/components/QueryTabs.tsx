"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { rememberQuery } from "@/lib/queryList";

/** Sub-navigation shared by the pages under /queries/[id]. */
export default function QueryTabs({ queryId }: { queryId: string }) {
  const pathname = usePathname();
  useEffect(() => rememberQuery(queryId), [queryId]);
  const base = `/queries/${encodeURIComponent(queryId)}`;
  const tabs = [
    { href: base, label: "Explorer" },
    { href: `${base}/compare`, label: "Compare" },
  ];
  return (
    <div className="flex gap-1 border-b border-zinc-200 px-4 pt-2 text-sm dark:border-zinc-800">
      {tabs.map(({ href, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`-mb-px rounded-t-md border border-b-0 px-3 py-1 ${
              active
                ? "border-zinc-200 bg-white font-medium dark:border-zinc-800 dark:bg-zinc-950"
                : "border-transparent text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </div>
  );
}
