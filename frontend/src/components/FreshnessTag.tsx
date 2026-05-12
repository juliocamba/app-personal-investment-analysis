import React from "react";

interface Props {
  flag: string | null;
}

/**
 * Badge for the `freshness_flag` column from `signal_runs`.
 * Stale data is highlighted amber; fresh data is shown in green.
 */
export function FreshnessTag({ flag }: Props) {
  if (!flag) return null;
  const lower = flag.toLowerCase();
  const isStale = lower.includes("stale") || lower === "old" || lower === "outdated";
  return (
    <span
      className={`freshness-tag ${isStale ? "freshness-tag--stale" : "freshness-tag--fresh"}`}
      title={isStale ? "Data may be outdated — re-run the pipeline to refresh." : "Data is current."}
    >
      {flag}
    </span>
  );
}
