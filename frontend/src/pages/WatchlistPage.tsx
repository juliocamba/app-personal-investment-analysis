import React, { useCallback, useEffect, useMemo, useState } from "react";
import type { InactiveWatchlistRow, SignalFilter, SortKey, WatchlistAddRequest, WatchlistRow } from "../types";
import {
  cancelWatchlistAddRequest,
  createWatchlistAddRequest,
  fetchInactiveWatchlist,
  fetchMyDefaultWatchlistId,
  fetchWatchlist,
  fetchWatchlistAddRequests,
  reactivateWatchlistCompany,
  removeFromWatchlist,
} from "../lib/api";
import { CompanyRow } from "../components/CompanyRow";
import { FilterBar } from "../components/FilterBar";
import { filterRows, sortRows } from "../utils/watchlistFilters";

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

/**
 * Main watchlist page. Reads from `dashboard_watchlist_latest` via
 * `fetchWatchlist()` and renders a filterable, sortable table.
 */
export function WatchlistPage() {
  const [rows, setRows] = useState<WatchlistRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  // Phase 9A: removal state
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  // Phase 9A: removed-companies section
  const [showRemoved, setShowRemoved] = useState(false);
  const [removedRows, setRemovedRows] = useState<InactiveWatchlistRow[]>([]);
  const [loadingRemoved, setLoadingRemoved] = useState(false);
  const [reactivatingId, setReactivatingId] = useState<string | null>(null);

  // Phase 9B: add-request state
  const [watchlistId, setWatchlistId] = useState<string | null>(null);
  const [addRequests, setAddRequests] = useState<WatchlistAddRequest[]>([]);
  const [requestTicker, setRequestTicker] = useState("");
  const [requestExchange, setRequestExchange] = useState("");
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  // Filter / sort state
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("ticker");
  const [sortAsc, setSortAsc] = useState(true);
  const [tickerSearch, setTickerSearch] = useState("");

  useEffect(() => {
    fetchWatchlist()
      .then((data) => {
        setRows(data);
        setLastFetched(new Date());
        setLoading(false);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setLoading(false);
      });
  }, []);

  // Phase 9B: load default watchlist ID and recent add requests once on mount.
  useEffect(() => {
    fetchMyDefaultWatchlistId()
      .then((wid) => {
        setWatchlistId(wid);
        if (wid) {
          return fetchWatchlistAddRequests(wid).then(setAddRequests);
        }
      })
      .catch(() => { /* non-critical */ });
  }, []);

  // Phase 9A: soft-remove a company from the active watchlist.
  const handleRemove = useCallback(
    (membershipId: string, ticker: string) => {
      if (
        !window.confirm(
          `Remove ${ticker} from the active watchlist?\n\nAll historical data is preserved and the company can be reactivated at any time.`,
        )
      ) {
        return;
      }
      setRemovingId(membershipId);
      setRemoveError(null);
      removeFromWatchlist(membershipId)
        .then(() => {
          setRows((prev) =>
            prev.filter((r) => r.watchlist_membership_id !== membershipId),
          );
          // Invalidate the cached removed list so it refreshes on next open.
          setRemovedRows([]);
        })
        .catch((err: unknown) => {
          setRemoveError(err instanceof Error ? err.message : "Failed to remove company.");
        })
        .finally(() => {
          setRemovingId(null);
        });
    },
    [],
  );

  // Phase 9A: load inactive companies when the section is first opened.
  const handleToggleRemoved = useCallback(() => {
    const next = !showRemoved;
    setShowRemoved(next);
    if (next && removedRows.length === 0) {
      setLoadingRemoved(true);
      fetchInactiveWatchlist()
        .then(setRemovedRows)
        .catch(() => { /* non-critical: ignored */ })
        .finally(() => setLoadingRemoved(false));
    }
  }, [showRemoved, removedRows.length]);

  // Phase 9A: reactivate a removed company.
  const handleReactivate = useCallback(
    (membershipId: string, ticker: string) => {
      setReactivatingId(membershipId);
      reactivateWatchlistCompany(membershipId)
        .then(() => {
          setRemovedRows((prev) =>
            prev.filter((r) => r.watchlist_membership_id !== membershipId),
          );
          // Reload the active list so the reactivated company appears.
          return fetchWatchlist();
        })
        .then((data) => {
          setRows(data);
          setLastFetched(new Date());
        })
        .catch((err: unknown) => {
          setRemoveError(
            `Failed to reactivate ${ticker}: ${err instanceof Error ? err.message : String(err)}`,
          );
        })
        .finally(() => {
          setReactivatingId(null);
        });
    },
    [],
  );

  const displayed = useMemo(() => {
    const filtered = filterRows(rows, signalFilter, tickerSearch);
    return sortRows(filtered, sortKey, sortAsc);
  }, [rows, signalFilter, tickerSearch, sortKey, sortAsc]);

  if (loading) {
    return (
      <div className="page-state" aria-live="polite" aria-busy="true">
        <div className="spinner" aria-label="Loading watchlist…" />
        <p>Loading watchlist…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-state page-state--error" role="alert">
        <p className="page-state__title">Failed to load watchlist</p>
        <p className="page-state__detail">{error}</p>
        <p className="page-state__hint">
          Check that <code>VITE_SUPABASE_URL</code> and{" "}
          <code>VITE_SUPABASE_ANON_KEY</code> are set and that you are signed
          in.
        </p>
      </div>
    );
  }

  if (rows.length === 0 && !loading) {
    return (
      <div className="page">
        <div className="page__header">
          <h1 className="page__title">Watchlist</h1>
        </div>
        <div className="page-state" aria-live="polite">
          <p className="page-state__title">No active companies in watchlist</p>
          <p className="page-state__detail">
            All companies have been removed. Use the section below to reactivate
            a company, or add new ones via Supabase.
          </p>
        </div>

        {removeError && <p className="remove-error" role="alert">{removeError}</p>}

        {/* Phase 9A: removed companies section — shown even when active list is empty */}
        <div className="removed-section">
          <button className="removed-section__toggle" onClick={handleToggleRemoved}>
            {showRemoved ? "▲ Hide removed companies" : "▼ Show removed companies"}
          </button>

          {showRemoved && (
            <>
              <p className="removed-section__title">Removed companies</p>
              {loadingRemoved && <p className="removed-section__empty">Loading…</p>}
              {!loadingRemoved && removedRows.length === 0 && (
                <p className="removed-section__empty">No removed companies.</p>
              )}
              {!loadingRemoved && removedRows.length > 0 && (
                <table className="removed-table" aria-label="Removed companies">
                  <thead>
                    <tr>
                      <th scope="col">Ticker</th>
                      <th scope="col">Company</th>
                      <th scope="col">Sector</th>
                      <th scope="col">Removed</th>
                      <th scope="col" aria-label="Reactivate"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {removedRows.map((r) => (
                      <tr key={r.watchlist_membership_id}>
                        <td><strong>{r.ticker}</strong></td>
                        <td>{r.name}</td>
                        <td>{r.sector ?? "—"}</td>
                        <td>
                          {r.removed_at
                            ? new Date(r.removed_at).toLocaleDateString()
                            : "—"}
                        </td>
                        <td>
                          <button
                            className="btn-reactivate"
                            disabled={reactivatingId === r.watchlist_membership_id}
                            onClick={() =>
                              handleReactivate(r.watchlist_membership_id, r.ticker)
                            }
                          >
                            {reactivatingId === r.watchlist_membership_id
                              ? "Reactivating…"
                              : "Reactivate"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Watchlist</h1>
        {lastFetched && (
          <span className="page__subtitle">
            Loaded at {lastFetched.toLocaleTimeString()}
          </span>
        )}
      </div>

      <FilterBar
        filter={signalFilter}
        onFilterChange={setSignalFilter}
        sortKey={sortKey}
        onSortKeyChange={setSortKey}
        sortAsc={sortAsc}
        onSortAscChange={setSortAsc}
        tickerSearch={tickerSearch}
        onTickerSearchChange={setTickerSearch}
        totalCount={rows.length}
        filteredCount={displayed.length}
      />

      {displayed.length === 0 ? (
        <div className="page-state" aria-live="polite">
          <p className="page-state__title">No matching companies</p>
          <p className="page-state__detail">
            Try adjusting the signal filter or search term.
          </p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="watchlist-table" aria-label="Company watchlist">
            <thead>
              <tr>
                <th scope="col">Ticker</th>
                <th scope="col">Company</th>
                <th scope="col">Signal</th>
                <th scope="col">Price</th>
                <th scope="col" title="Probability of buy (adjusted)">p_buy_adj</th>
                <th scope="col" title="Probability of sell">p_sell</th>
                <th scope="col" title="Final quality score (0–100)">Quality</th>
                <th scope="col" title="Intrinsic value P25–P75 range">IV Range</th>
                <th scope="col" title="Margin of safety (conservative)">MoS</th>
                <th scope="col">Freshness</th>
                <th scope="col" aria-label="Row actions"></th>
              </tr>
            </thead>
            <tbody>
              {displayed.map((row) => (
                <CompanyRow
                  key={row.company_id}
                  row={row}
                  onRemove={handleRemove}
                  isRemoving={removingId === row.watchlist_membership_id}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {removeError && <p className="remove-error" role="alert">{removeError}</p>}

      {/* Phase 9A: removed companies section */}
      <div className="removed-section">
        <button className="removed-section__toggle" onClick={handleToggleRemoved}>
          {showRemoved ? "▲ Hide removed companies" : "▼ Show removed companies"}
        </button>

        {showRemoved && (
          <>
            <p className="removed-section__title">Removed companies</p>
            {loadingRemoved && <p className="removed-section__empty">Loading…</p>}
            {!loadingRemoved && removedRows.length === 0 && (
              <p className="removed-section__empty">No removed companies.</p>
            )}
            {!loadingRemoved && removedRows.length > 0 && (
              <table className="removed-table" aria-label="Removed companies">
                <thead>
                  <tr>
                    <th scope="col">Ticker</th>
                    <th scope="col">Company</th>
                    <th scope="col">Sector</th>
                    <th scope="col">Removed</th>
                    <th scope="col" aria-label="Reactivate"></th>
                  </tr>
                </thead>
                <tbody>
                  {removedRows.map((r) => (
                    <tr key={r.watchlist_membership_id}>
                      <td><strong>{r.ticker}</strong></td>
                      <td>{r.name}</td>
                      <td>{r.sector ?? "—"}</td>
                      <td>
                        {r.removed_at
                          ? new Date(r.removed_at).toLocaleDateString()
                          : "—"}
                      </td>
                      <td>
                        <button
                          className="btn-reactivate"
                          disabled={reactivatingId === r.watchlist_membership_id}
                          onClick={() =>
                            handleReactivate(r.watchlist_membership_id, r.ticker)
                          }
                        >
                          {reactivatingId === r.watchlist_membership_id
                            ? "Reactivating…"
                            : "Reactivate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>

      <p className="page__footer-note">
        All values are model outputs from the daily pipeline. Not financial
        advice. Intrinsic value ranges are estimates only.
      </p>
    </div>
  );
}
