export function fmtSeconds(s: number | null | undefined): string {
  if (s == null) return "–";
  if (s < 1) return `${s.toFixed(2)} s`;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`;
}

export const fmtNumber = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });

export function fmtBytes(b: number | null | undefined): string {
  if (b == null) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = b;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toLocaleString(undefined, { maximumFractionDigits: v < 10 && i > 0 ? 1 : 0 })} ${units[i]}`;
}
