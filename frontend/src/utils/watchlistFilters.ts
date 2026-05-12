import type { SignalFilter, SortKey, WatchlistRow } from "../types";

export function filterRows(
  rows: WatchlistRow[],
  signal: SignalFilter,
  search: string,
): WatchlistRow[] {
  let result = rows;

  if (signal !== "ALL") {
    result = result.filter(
      (r) => (r.final_signal ?? "").toUpperCase() === signal,
    );
  }

  const q = search.trim().toLowerCase();
  if (q) {
    result = result.filter(
      (r) =>
        r.ticker.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q),
    );
  }

  return result;
}

export function sortRows(
  rows: WatchlistRow[],
  key: SortKey,
  asc: boolean,
): WatchlistRow[] {
  const copy = [...rows];
  copy.sort((a, b) => {
    let va: string | number | null;
    let vb: string | number | null;

    if (key === "ticker" || key === "final_signal") {
      va = (a[key] ?? "").toUpperCase();
      vb = (b[key] ?? "").toUpperCase();
    } else {
      va = a[key] ?? null;
      vb = b[key] ?? null;
    }

    // Nulls always last regardless of direction.
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;

    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
    return asc ? cmp : -cmp;
  });
  return copy;
}
