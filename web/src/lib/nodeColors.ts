"use client";

import { useSyncExternalStore } from "react";

/**
 * Plan node styles. Related nodes share a hue and differ in `strength` (0..1: how
 * saturated the background and stripe are), so e.g. Hash Join is orange and Hash a pale orange.
 */
export const CATEGORIES = [
  { key: "nested_loop", label: "Nested Loop", color: "#e5484d", strength: 1 },
  { key: "hash_join", label: "Hash Join", color: "#eb6834", strength: 1 },
  { key: "hash", label: "Hash", color: "#eb6834", strength: 0.35 },
  { key: "merge_join", label: "Merge Join", color: "#d9a300", strength: 1 },
  { key: "seq_scan", label: "Seq Scan", color: "#2a78d6", strength: 1 },
  { key: "index_scan", label: "Index Scan", color: "#2a78d6", strength: 0.65 },
  { key: "index_only_scan", label: "Index Only Scan", color: "#2a78d6", strength: 0.4 },
  { key: "bitmap_scan", label: "Bitmap Scan", color: "#13a5b8", strength: 0.65 },
  { key: "other_scan", label: "Other Scan / Result", color: "#2a78d6", strength: 0.2 },
  { key: "aggregate", label: "Aggregate", color: "#1baf7a", strength: 1 },
  { key: "group", label: "Group / Unique / Window", color: "#1baf7a", strength: 0.4 },
  { key: "sort", label: "Sort", color: "#a0522d", strength: 1 },
  { key: "limit", label: "Limit", color: "#a0522d", strength: 0.4 },
  { key: "materialize", label: "Materialize", color: "#e87ba4", strength: 1 },
  { key: "memoize", label: "Memoize / CTE", color: "#e87ba4", strength: 0.4 },
  { key: "gather", label: "Gather", color: "#7c5cd6", strength: 1 },
  { key: "append", label: "Append / Merge", color: "#7c5cd6", strength: 0.4 },
  { key: "other", label: "Other", color: "#8a8984", strength: 0.5 },
] as const;

export type CategoryKey = (typeof CATEGORIES)[number]["key"];

export function categoryOf(nodeType: string): CategoryKey {
  if (nodeType === "Nested Loop") return "nested_loop";
  if (nodeType === "Hash Join") return "hash_join";
  if (nodeType === "Hash") return "hash";
  if (nodeType === "Merge Join") return "merge_join";
  if (nodeType === "Seq Scan") return "seq_scan";
  if (nodeType === "Index Scan") return "index_scan";
  if (nodeType === "Index Only Scan") return "index_only_scan";
  if (/^Bitmap/.test(nodeType)) return "bitmap_scan";
  if (/Scan|Result|Values/.test(nodeType)) return "other_scan";
  if (/Aggregate/.test(nodeType)) return "aggregate";
  if (/Group|Unique|WindowAgg|SetOp/.test(nodeType)) return "group";
  if (/Sort/.test(nodeType)) return "sort";
  if (nodeType === "Limit") return "limit";
  if (nodeType === "Materialize") return "materialize";
  if (/Memoize|CTE/.test(nodeType)) return "memoize";
  if (/Gather/.test(nodeType)) return "gather";
  if (/Append|Merge/.test(nodeType)) return "append";
  return "other";
}

/** One-line explanation of what each kind of node does, shown when zoomed in. */
export const DESCRIPTIONS: Record<CategoryKey, string> = {
  nested_loop: "For each outer row, scan the inner side",
  hash_join: "Probe a hash table built from the inner side",
  hash: "Builds the in-memory hash table for a Hash Join",
  merge_join: "Join two inputs already sorted on the join key",
  seq_scan: "Read every row of the table",
  index_scan: "Fetch matching rows through an index",
  index_only_scan: "Answer from the index alone, no table access",
  bitmap_scan: "Collect matching row locations, then read them in page order",
  other_scan: "Produce rows from a function, VALUES list or constant",
  aggregate: "Compute aggregates such as COUNT / MIN / MAX",
  group: "Group, de-duplicate or window sorted rows",
  sort: "Order rows by the given keys",
  limit: "Stop after N rows",
  materialize: "Cache the input so it can be re-read cheaply",
  memoize: "Cache results per parameter value / CTE result",
  gather: "Collect rows from parallel workers",
  append: "Concatenate or merge several inputs",
  other: "Other plan node",
};

const STRENGTH = Object.fromEntries(CATEGORIES.map((c) => [c.key, c.strength])) as Record<
  CategoryKey,
  number
>;

/** Card colors for a category: a stripe/border and a tinted background. */
export function categoryStyle(key: CategoryKey, color: string) {
  const s = STRENGTH[key];
  return {
    border: `color-mix(in srgb, ${color} ${Math.round(45 + 55 * s)}%, transparent)`,
    background: `color-mix(in srgb, ${color} ${Math.round(6 + 22 * s)}%, var(--background, white))`,
  };
}

export interface NodeColorSettings {
  enabled: boolean;
  colors: Record<CategoryKey, string>;
}

const STORAGE_KEY = "plan-node-colors-v2";
const DEFAULTS: NodeColorSettings = {
  enabled: true,
  colors: Object.fromEntries(CATEGORIES.map((c) => [c.key, c.color])) as Record<CategoryKey, string>,
};

let current = DEFAULTS;
let loaded = false;
const listeners = new Set<() => void>();

function load() {
  loaded = true;
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (raw) current = { enabled: raw.enabled !== false, colors: { ...DEFAULTS.colors, ...raw.colors } };
  } catch {
    // storage unavailable or corrupt: keep defaults
  }
}

function update(next: NodeColorSettings) {
  current = next;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // not persisted
  }
  listeners.forEach((l) => l());
}

export const setColorsEnabled = (enabled: boolean) => update({ ...current, enabled });
export const setCategoryColor = (key: CategoryKey, color: string) =>
  update({ ...current, colors: { ...current.colors, [key]: color } });
export const resetColors = () => update({ ...DEFAULTS, enabled: current.enabled });

export function useNodeColors(): NodeColorSettings {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => {
      if (!loaded) load();
      return current;
    },
    () => DEFAULTS,
  );
}
