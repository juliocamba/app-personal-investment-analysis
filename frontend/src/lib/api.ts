/**
 * Supabase data-access functions for the Phase 8/9A dashboard.
 *
 * All queries go through the authenticated Supabase session (anon key +
 * Supabase Auth). No backend provider APIs are called from here.
 */
import { supabase } from "./supabase";
import type { AlertHistoryRow, InactiveWatchlistRow, WatchlistRow } from "../types";

/**
 * Fetch all rows from the `dashboard_watchlist_latest` view, ordered by ticker.
 * Phase 9A: view now joins through watchlist_companies.active = true.
 */
export async function fetchWatchlist(): Promise<WatchlistRow[]> {
  const { data, error } = await supabase
    .from("dashboard_watchlist_latest")
    .select("*")
    .order("ticker");
  if (error) throw new Error(error.message);
  return (data ?? []) as WatchlistRow[];
}

/**
 * Fetch inactive (soft-removed) watchlist entries from `dashboard_watchlist_inactive`.
 * Used to populate the "Removed companies" section in the dashboard.
 */
export async function fetchInactiveWatchlist(): Promise<InactiveWatchlistRow[]> {
  const { data, error } = await supabase
    .from("dashboard_watchlist_inactive")
    .select("*")
    .order("removed_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as InactiveWatchlistRow[];
}

/**
 * Soft-remove a company from the active watchlist.
 *
 * Updates `watchlist_companies` row: active = false, removed_at = now().
 * Does NOT delete the company or any historical data.
 * RLS ensures users can only modify their own watchlist rows.
 *
 * @param membershipId  The `watchlist_companies.id` (watchlist_membership_id from view).
 */
export async function removeFromWatchlist(membershipId: string): Promise<void> {
  const { error } = await supabase
    .from("watchlist_companies")
    .update({ active: false, removed_at: new Date().toISOString() })
    .eq("id", membershipId);
  if (error) throw new Error(error.message);
}

/**
 * Reactivate a previously removed watchlist company.
 *
 * Updates `watchlist_companies` row: active = true, removed_at = null.
 * Historical data is preserved and will be included in the next pipeline run.
 * RLS ensures users can only modify their own watchlist rows.
 *
 * @param membershipId  The `watchlist_companies.id`.
 */
export async function reactivateWatchlistCompany(membershipId: string): Promise<void> {
  const { error } = await supabase
    .from("watchlist_companies")
    .update({ active: true, removed_at: null })
    .eq("id", membershipId);
  if (error) throw new Error(error.message);
}

/**
 * Fetch recent rows from `alert_history`, ordered newest-first.
 * RLS restricts this to the authenticated user's own alerts.
 */
export async function fetchAlertHistory(limit = 100): Promise<AlertHistoryRow[]> {
  const { data, error } = await supabase
    .from("alert_history")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return (data ?? []) as AlertHistoryRow[];
}

