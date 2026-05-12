import React from "react";

interface Props {
  flags: string[] | null;
}

/**
 * Renders the `red_flags` array from `signal_runs`.
 * Shows a dash when no flags are present.
 */
export function RedFlagList({ flags }: Props) {
  if (!flags || flags.length === 0) {
    return <span className="text-muted">None</span>;
  }
  return (
    <ul className="red-flag-list" aria-label="Red flags">
      {flags.map((f, i) => (
        <li key={i} className="red-flag-list__item">
          ⚠ {f}
        </li>
      ))}
    </ul>
  );
}
