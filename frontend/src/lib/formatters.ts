/**
 * Pure display-formatting helpers.
 * These contain no business logic — they only format values for human reading.
 */

/** Format a price number as a currency string. Returns "—" for null/undefined. */
export function formatPrice(value: number | null | undefined, currency = "USD"): string {
  if (value == null) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return value.toFixed(2);
  }
}

/**
 * Format a ratio stored as 0–1 as a percentage string.
 * e.g. 0.253 → "25.3%"
 */
export function formatPct(value: number | null | undefined, decimals = 1): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Format a plain numeric value. Returns "—" for null/undefined. */
export function formatNum(value: number | null | undefined, decimals = 2): string {
  if (value == null) return "—";
  return value.toFixed(decimals);
}

/** Format a large market-cap number as a compact string (e.g. $1.2T, $45.3B). */
export function formatMarketCap(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  return `$${value.toFixed(0)}`;
}

/** Format an ISO timestamp as a readable local date string. */
export function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return "—";
  try {
    return new Date(isoString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return isoString;
  }
}

/** Format an ISO timestamp as date + time. */
export function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return "—";
  try {
    return new Date(isoString).toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}
