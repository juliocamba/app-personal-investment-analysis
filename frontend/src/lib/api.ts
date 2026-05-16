/**
 * Supabase data-access functions for the Phase 8/9A dashboard.
 *
 * All queries go through the authenticated Supabase session (anon key +
 * Supabase Auth). No backend provider APIs are called from here.
 */
import { supabase } from "./supabase";
import type {
  AlertHistoryRow,
  CompanyOption,
  InactiveWatchlistRow,
  PositionDashboardRow,
  PositionEntryProfileInput,
  PositionEntryProfileRow,
  PositionInput,
  PositionReviewAlertLifecycleStatus,
  PositionRow,
  PositionReviewAlertRow,
  WatchlistAddRequest,
  WatchlistRow,
} from "../types";

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

// ---------------------------------------------------------------------------
// Phase 9B: Watchlist add requests
// ---------------------------------------------------------------------------

/**
 * Fetch the user's default watchlist UUID.
 * Returns the first watchlist by created_at for the authenticated user.
 * Used to attach add requests to the correct watchlist.
 */
export async function fetchMyDefaultWatchlistId(): Promise<string | null> {
  const { data, error } = await supabase
    .from("watchlists")
    .select("id")
    .order("created_at", { ascending: true })
    .limit(1);
  if (error) throw new Error(error.message);
  return data && data.length > 0 ? (data[0] as { id: string }).id : null;
}

/**
 * Fetch add requests for a specific watchlist, ordered newest-first.
 * RLS restricts this to the authenticated user's own requests.
 */
export async function fetchWatchlistAddRequests(
  watchlistId: string,
): Promise<WatchlistAddRequest[]> {
  const { data, error } = await supabase
    .from("watchlist_add_requests")
    .select("*")
    .eq("watchlist_id", watchlistId)
    .order("requested_at", { ascending: false })
    .limit(50);
  if (error) throw new Error(error.message);
  return (data ?? []) as WatchlistAddRequest[];
}

/**
 * Submit a new watchlist add request.
 * The backend pipeline validates, enriches, and approves/rejects the request.
 * The frontend never calls FMP or any provider API.
 */
export async function createWatchlistAddRequest(params: {
  watchlistId: string;
  requestedTicker: string;
  requestedExchange?: string;
}): Promise<WatchlistAddRequest> {
  const payload: Record<string, string> = {
    watchlist_id: params.watchlistId,
    requested_ticker: params.requestedTicker.toUpperCase().trim(),
  };
  if (params.requestedExchange && params.requestedExchange.trim()) {
    payload.requested_exchange = params.requestedExchange.toUpperCase().trim();
  }
  const { data, error } = await supabase
    .from("watchlist_add_requests")
    .insert(payload)
    .select()
    .single();
  if (error) throw new Error(error.message);
  return data as WatchlistAddRequest;
}

/**
 * Cancel a pending add request.
 * RLS only allows updating own pending requests to 'cancelled'.
 */
export async function cancelWatchlistAddRequest(requestId: string): Promise<void> {
  const { error } = await supabase
    .from("watchlist_add_requests")
    .update({ status: "cancelled" })
    .eq("id", requestId);
  if (error) throw new Error(error.message);
}

// ---------------------------------------------------------------------------
// Phase 12B.1: manual positions
// ---------------------------------------------------------------------------

export async function fetchCompaniesForPositions(): Promise<CompanyOption[]> {
  const { data, error } = await supabase
    .from("companies")
    .select("id, ticker, name, currency")
    .order("ticker");
  if (error) throw new Error(error.message);
  return (data ?? []) as CompanyOption[];
}

export async function fetchPositions(): Promise<PositionDashboardRow[]> {
  const { data, error } = await supabase
    .from("dashboard_positions_latest")
    .select("*")
    .order("status")
    .order("entry_date", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as PositionDashboardRow[];
}

export async function fetchPositionEntryProfiles(): Promise<PositionEntryProfileRow[]> {
  const { data, error } = await supabase
    .from("position_entry_profiles")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as PositionEntryProfileRow[];
}

export async function fetchPositionReviewAlerts(): Promise<PositionReviewAlertRow[]> {
  const { data, error } = await supabase
    .from("position_review_alerts")
    .select("*")
    .in("status", ["open", "snoozed"])
    .order("triggered_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as PositionReviewAlertRow[];
}

export async function updatePositionReviewAlertLifecycle(
  alertId: string,
  input: {
    status: Exclude<PositionReviewAlertLifecycleStatus, "open">;
    dismissed_reason?: string | null;
    snoozed_until?: string | null;
  },
): Promise<PositionReviewAlertRow> {
  const payload =
    input.status === "dismissed"
      ? {
        status: "dismissed" as const,
        dismissed_at: new Date().toISOString(),
        dismissed_reason: input.dismissed_reason?.trim() || "dismissed_in_ui",
        snoozed_until: null,
      }
      : {
        status: "snoozed" as const,
        dismissed_at: null,
        dismissed_reason: null,
        snoozed_until: input.snoozed_until ?? null,
      };

  const { data, error } = await supabase
    .from("position_review_alerts")
    .update(payload)
    .eq("id", alertId)
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return data as PositionReviewAlertRow;
}

export async function savePositionEntryProfile(
  positionId: string,
  input: PositionEntryProfileInput,
): Promise<PositionEntryProfileRow> {
  const thesisPayload = {
    thesis_summary: input.thesis_summary?.trim() || null,
    why_bought: input.why_bought?.trim() || null,
    key_risks: input.key_risks?.trim() || null,
    target_price: input.target_price ?? null,
    target_price_currency: input.target_price_currency?.trim().toUpperCase() || null,
    expected_holding_period: input.expected_holding_period?.trim() || null,
    confidence_level: input.confidence_level ?? null,
    catalysts: input.catalysts?.trim() || null,
    invalidation_criteria: input.invalidation_criteria?.trim() || null,
  };

  const { data: existing, error: existingError } = await supabase
    .from("position_entry_profiles")
    .select("id")
    .eq("position_id", positionId)
    .maybeSingle();
  if (existingError) throw new Error(existingError.message);

  if (existing) {
    const { data, error } = await supabase
      .from("position_entry_profiles")
      .update(thesisPayload)
      .eq("position_id", positionId)
      .select("*")
      .single();
    if (error) throw new Error(error.message);
    return data as PositionEntryProfileRow;
  }

  const { data, error } = await supabase
    .from("position_entry_profiles")
    .insert({
      position_id: positionId,
      ...thesisPayload,
    })
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return data as PositionEntryProfileRow;
}

export async function createPosition(input: PositionInput): Promise<PositionRow> {
  const { data, error } = await supabase
    .from("positions")
    .insert({
      company_id: input.company_id,
      entry_date: input.entry_date,
      quantity: input.quantity,
      average_entry_price: input.average_entry_price,
      currency: input.currency.trim().toUpperCase(),
      fees: input.fees ?? null,
      notes: input.notes?.trim() || null,
      status: input.status,
      closed_at: input.closed_at ?? null,
    })
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return data as PositionRow;
}

export async function updatePosition(
  positionId: string,
  input: PositionInput,
): Promise<PositionRow> {
  const { data, error } = await supabase
    .from("positions")
    .update({
      company_id: input.company_id,
      entry_date: input.entry_date,
      quantity: input.quantity,
      average_entry_price: input.average_entry_price,
      currency: input.currency.trim().toUpperCase(),
      fees: input.fees ?? null,
      notes: input.notes?.trim() || null,
      status: input.status,
      closed_at: input.closed_at ?? null,
    })
    .eq("id", positionId)
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return data as PositionRow;
}

export async function closePosition(positionId: string): Promise<PositionRow> {
  const { data, error } = await supabase
    .from("positions")
    .update({
      status: "closed",
      closed_at: new Date().toISOString(),
    })
    .eq("id", positionId)
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return data as PositionRow;
}

