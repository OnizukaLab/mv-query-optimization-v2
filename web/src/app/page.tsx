"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getHealth, type Health } from "@/lib/api";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e: Error) => setError(e.message));
  }, []);

  const db = health?.database;
  return (
    <div className="p-8">
      <h1 className="text-xl font-semibold">Home</h1>
      <div className="mt-6 grid max-w-xl grid-cols-2 gap-4">
        <StatusCard label="API" ok={health ? true : error ? false : null} detail={error} />
        <StatusCard label="PostgreSQL" ok={health ? db! : null} detail={health?.detail} />
      </div>
      <Link href="/plan" className="mt-6 inline-block text-sm underline">
        Open Query Plan viewer →
      </Link>
    </div>
  );
}

function StatusCard({ label, ok, detail }: { label: string; ok: boolean | null; detail?: string | null }) {
  const color = ok === null ? "bg-zinc-400" : ok ? "bg-emerald-500" : "bg-red-500";
  return (
    <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className={`h-2 w-2 rounded-full ${color}`} />
        {label}
      </div>
      {detail && <p className="mt-2 text-xs text-zinc-500">{detail}</p>}
    </div>
  );
}
