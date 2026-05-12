import React from "react";

/**
 * Persistent disclaimer banner shown on all dashboard pages.
 * Required by the project brief: "Private research tool. Not financial advice."
 */
export function Disclaimer() {
  return (
    <div className="disclaimer" role="note" aria-label="Disclaimer">
      🔒 Private research tool — not financial advice. All data is stored and
      calculated internally. Do not redistribute.
    </div>
  );
}
