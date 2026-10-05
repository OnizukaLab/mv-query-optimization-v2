"use client";

import { useEffect, useRef } from "react";

export default function LogConsole({ lines }: { lines: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div
      ref={ref}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      }}
      className="h-full overflow-auto rounded-md bg-zinc-950 p-3 font-mono text-xs leading-5 text-zinc-300"
    >
      {lines.length === 0 ? (
        <span className="text-zinc-500">No output yet.</span>
      ) : (
        lines.map((l, i) => (
          <div
            key={i}
            className={`whitespace-pre-wrap break-all ${
              /\b(ERROR|Traceback)\b/.test(l) ? "text-red-400" : /\bWARNING\b/.test(l) ? "text-amber-400" : ""
            }`}
          >
            {l}
          </div>
        ))
      )}
    </div>
  );
}
