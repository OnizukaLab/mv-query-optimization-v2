"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Home" },
  { href: "/experiments", label: "Experiments" },
  { href: "/plan", label: "Query Plan" },
  { href: "/results", label: "Results" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <nav className="flex w-52 shrink-0 flex-col gap-1 border-r border-zinc-200 p-3 dark:border-zinc-800">
      <div className="px-3 py-2 text-sm font-semibold">MV Optimization</div>
      {ITEMS.map(({ href, label }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`rounded-md px-3 py-2 text-sm ${
              active
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
