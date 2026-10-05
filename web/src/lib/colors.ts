// Categorical slots are CSS variables (light/dark) defined in globals.css.
// Color follows the algorithm, never its rank, so filtering never repaints survivors.
const FIXED: Record<string, number> = {
  normal: 1,
  bigsubs: 2,
  frequency: 3,
  utility: 4,
  utility_capacity: 5,
};

export function algorithmColor(name: string, all: string[]): string {
  if (name === "none") return "var(--series-baseline)";
  if (FIXED[name]) return `var(--series-${FIXED[name]})`;
  // unknown algorithms take the remaining slots in stable (sorted) order
  const others = all.filter((n) => n !== "none" && !FIXED[n]).sort();
  return `var(--series-${Math.min(6 + others.indexOf(name), 8)})`;
}

export const PHASES = [
  ["optimization", "ILP optimization"],
  ["sql_generation", "SQL generation"],
  ["mv_creation", "MV creation"],
  ["query_rewriting", "Query rewriting"],
  ["benchmark", "Benchmark"],
] as const;

export const phaseColor = (index: number) => `var(--phase-${index + 1})`;
