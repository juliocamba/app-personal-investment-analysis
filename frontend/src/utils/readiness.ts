/**
 * Readiness display utilities for Phase 10C.4.
 *
 * Maps database readiness status codes and reason codes to user-friendly
 * labels. No business logic lives here — these are pure display helpers.
 */

/** Human-friendly labels for readiness_reason_codes from company_analysis_readiness. */
export const REASON_CODE_LABELS: Record<string, string> = {
  provider_limited: "Provider coverage limited",
  missing_min_statement_history: "Limited statement history",
  valuation_partial: "Partial valuation",
  valuation_ready: "Valuation ready",
  missing_supported_fundamentals_path: "Fundamentals not currently supported",
  non_us_fundamentals_not_supported: "Non-US fundamentals not currently supported",
};

/** Human-friendly labels for readiness_status values from company_analysis_readiness. */
export const READINESS_STATUS_LABELS: Record<string, string> = {
  analysis_ready: "Analysis ready",
  partial_analysis: "Partial analysis",
  tracking_only: "Tracking only",
  provider_limited: "Provider limited",
  unsupported_for_analysis: "Unsupported",
};

/**
 * Returns a user-friendly label for a readiness status code.
 * Falls back to the raw value if not mapped.
 */
export function readinessLabel(status: string | null | undefined): string {
  if (!status) return "Unknown";
  return READINESS_STATUS_LABELS[status.toLowerCase()] ?? status;
}

/**
 * Returns a user-friendly label for a readiness reason code.
 * Falls back to the raw code if not mapped.
 */
export function formatReasonCode(code: string): string {
  return REASON_CODE_LABELS[code] ?? code;
}
