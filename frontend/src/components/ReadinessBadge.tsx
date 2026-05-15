import React from "react";
import { readinessLabel } from "../utils/readiness";

interface Props {
  status: string | null | undefined;
}

const STATUS_STYLES: Record<string, { background: string; color: string }> = {
  tracking_only:            { background: "#64748b", color: "#fff" },
  provider_limited:         { background: "#b45309", color: "#fff" },
  partial_analysis:         { background: "#1d4ed8", color: "#fff" },
  analysis_ready:           { background: "#16a34a", color: "#fff" },
  unsupported_for_analysis: { background: "#6b7280", color: "#fff" },
};

/**
 * Badge shown in the signal column when a row has can_run_signal = false.
 * Replaces SignalBadge for tracking-only or provider-limited companies.
 */
export function ReadinessBadge({ status }: Props) {
  const lower = status?.toLowerCase() ?? "";
  const style = STATUS_STYLES[lower] ?? { background: "#64748b", color: "#fff" };
  const label = readinessLabel(status);
  return (
    <span
      className="badge badge--readiness"
      style={style}
      data-testid="readiness-badge"
      title={`Readiness: ${label}`}
    >
      {label}
    </span>
  );
}
