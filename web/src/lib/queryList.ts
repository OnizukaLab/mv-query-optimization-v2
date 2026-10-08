import { listQueries, type QueryInfo } from "./api";

const LAST_QUERY_KEY = "mv.lastQuery";

let cached: Promise<QueryInfo[]> | null = null;

/** The workload's queries, fetched once per page load and shared by every picker. */
export function loadQueries(): Promise<QueryInfo[]> {
  cached ??= listQueries().catch((e: Error) => {
    cached = null; // let the next caller retry
    throw e;
  });
  return cached;
}

export function rememberQuery(id: string): void {
  try {
    localStorage.setItem(LAST_QUERY_KEY, id);
  } catch {
    // storage unavailable (private mode etc.): the convenience just doesn't persist
  }
}

export function lastQuery(): string | null {
  try {
    return localStorage.getItem(LAST_QUERY_KEY);
  } catch {
    return null;
  }
}

const COMPARE_KEY = "mv.compareSelection";

/** The experiment/algorithm the user picked on the Compare page; kept while switching queries. */
export interface CompareSelection {
  setId: string;
  algorithm: string;
}

export function saveCompareSelection(sel: CompareSelection): void {
  try {
    localStorage.setItem(COMPARE_KEY, JSON.stringify(sel));
  } catch {
    // storage unavailable: the choice just won't survive a query switch
  }
}

export function loadCompareSelection(): CompareSelection | null {
  try {
    const raw = localStorage.getItem(COMPARE_KEY);
    const sel = raw ? (JSON.parse(raw) as Partial<CompareSelection>) : null;
    return sel && typeof sel.setId === "string" && typeof sel.algorithm === "string"
      ? { setId: sel.setId, algorithm: sel.algorithm }
      : null;
  } catch {
    return null;
  }
}
