import React from "react";

interface Props {
  severity: string | null | undefined;
  primaryCodes?: string[] | null;
}

const QUALITY_LABELS: Record<string, string> = {
  blocks_both: "Fully blocked",
  blocks_valuation: "Valuation blocked",
  blocks_signal: "Signal blocked",
  confidence_limited: "Confidence limited",
  informational: "Analysis available",
};

const QUALITY_CLASSES: Record<string, string> = {
  blocks_both: "research-quality-badge research-quality-badge--blocked",
  blocks_valuation: "research-quality-badge research-quality-badge--valuation",
  blocks_signal: "research-quality-badge research-quality-badge--signal",
  confidence_limited: "research-quality-badge research-quality-badge--limited",
  informational: "research-quality-badge research-quality-badge--available",
};

export function formatQualityCode(code: string): string {
  return code.replace(/_/g, " ");
}

export function researchQualityLabel(severity: string | null | undefined): string {
  const key = severity?.toLowerCase() ?? "informational";
  return QUALITY_LABELS[key] ?? "Analysis available";
}

export function ResearchQualityBadge({ severity, primaryCodes }: Props) {
  const key = severity?.toLowerCase() ?? "informational";
  const label = researchQualityLabel(key);
  const title =
    primaryCodes && primaryCodes.length > 0
      ? `${label}: ${primaryCodes.map(formatQualityCode).join(", ")}`
      : label;
  return (
    <span
      className={QUALITY_CLASSES[key] ?? QUALITY_CLASSES.informational}
      data-testid="research-quality-badge"
      title={title}
    >
      {label}
    </span>
  );
}
