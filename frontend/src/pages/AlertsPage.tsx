import React, { useEffect, useState } from "react";
import type { AlertHistoryRow } from "../types";
import { fetchAlertHistory } from "../lib/api";
import { formatDateTime } from "../lib/formatters";

/** Badge for alert status values (sent / pending / failed). */
function StatusBadge({ status }: { status: string }) {
  const styleMap: Record<string, { background: string; color: string }> = {
    sent:    { background: "#16a34a", color: "#fff" },
    pending: { background: "#d97706", color: "#fff" },
    failed:  { background: "#dc2626", color: "#fff" },
  };
  const style = styleMap[status.toLowerCase()];
  return (
    <span
      className="badge"
      style={style ?? { background: "#94a3b8", color: "#fff" }}
    >
      {status}
    </span>
  );
}

/**
 * Alerts page — reads from `alert_history` ordered newest-first.
 *
 * RLS note: alert_history is scoped to the authenticated user's own alert
 * rules. Users can only see their own alerts.
 */
export function AlertsPage() {
  const [rows, setRows] = useState<AlertHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAlertHistory()
      .then((data) => {
        setRows(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="page-state" aria-live="polite" aria-busy="true">
        <div className="spinner" aria-label="Loading alert history…" />
        <p>Loading alert history…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-state page-state--error" role="alert">
        <p className="page-state__title">Failed to load alert history</p>
        <p className="page-state__detail">{error}</p>
        <p className="page-state__hint">
          If you have not configured any alert rules, this table will be empty.
          Alert delivery is configured by the backend operator.
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Alert History</h1>
        <span className="page__subtitle">{rows.length} recent alerts</span>
      </div>

      {rows.length === 0 ? (
        <div className="page-state" aria-live="polite">
          <p className="page-state__title">No alerts yet</p>
          <p className="page-state__detail">
            Alerts appear here after the pipeline runs with at least one alert
            rule configured in Supabase. Contact the operator if alert delivery
            appears disabled.
          </p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="alerts-table" aria-label="Alert history">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Title</th>
                <th scope="col">Channel</th>
                <th scope="col">Status</th>
                <th scope="col">Message</th>
                <th scope="col">Error</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="alerts-row">
                  <td className="alerts-row__date">
                    {formatDateTime(row.sent_at ?? row.created_at)}
                  </td>
                  <td className="alerts-row__title">{row.title}</td>
                  <td>
                    <span className="channel-tag">{row.channel}</span>
                  </td>
                  <td>
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="alerts-row__message">{row.message}</td>
                  <td className="alerts-row__error">
                    {row.error_message ? (
                      <span className="error-text">{row.error_message}</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
