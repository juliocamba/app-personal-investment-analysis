import React from "react";

interface Props {
  signal: string | null;
}

const SIGNAL_STYLES: Record<string, { background: string; color: string }> = {
  BUY:         { background: "#16a34a", color: "#fff" },
  STRONG_BUY:  { background: "#15803d", color: "#fff" },
  SELL:        { background: "#dc2626", color: "#fff" },
  STRONG_SELL: { background: "#b91c1c", color: "#fff" },
  HOLD:        { background: "#d97706", color: "#fff" },
  INSUFFICIENT_DATA: { background: "#94a3b8", color: "#fff" },
};

/**
 * Coloured badge for the `final_signal` value from `signal_runs`.
 */
export function SignalBadge({ signal }: Props) {
  if (!signal) {
    return <span className="badge badge--unknown">—</span>;
  }
  const upper = signal.toUpperCase();
  const style = SIGNAL_STYLES[upper];
  if (style) {
    return (
      <span className="badge" style={style} data-testid="signal-badge">
        {upper}
      </span>
    );
  }
  return (
    <span className="badge badge--unknown" data-testid="signal-badge">
      {upper}
    </span>
  );
}
