/**
 * Shared TypeScript types for the Phase 8 frontend dashboard.
 *
 * These mirror the columns exposed by Supabase views and tables that the
 * frontend is allowed to read via the anon key + Supabase Auth session.
 */

// ---------------------------------------------------------------------------
// dashboard_watchlist_latest view (003 + 005_watchlist_management.sql)
// ---------------------------------------------------------------------------
export interface WatchlistRow {
  // Phase 9A: ID of the watchlist_companies row — used for soft-remove/reactivate.
  watchlist_membership_id: string;
  company_id: string;
  ticker: string;
  name: string;
  exchange: string | null;
  country: string | null;
  currency: string;
  sector: string | null;
  industry: string | null;
  price_date: string | null;
  current_price: number | null;
  market_cap: number | null;
  roic: number | null;
  fcf_yield: number | null;
  net_debt_to_ebitda: number | null;
  news_sentiment_7d: number | null;
  final_quality_score: number | null;
  iv_p25: number | null;
  iv_p50: number | null;
  iv_p75: number | null;
  margin_of_safety_conservative: number | null;
  uncertainty_width: number | null;
  p_buy: number | null;
  p_buy_adjusted: number | null;
  p_sell: number | null;
  final_signal: string | null;
  red_flags: string[] | null;
  explanation: string | null;
  freshness_flag: string | null;
  // Phase 10C: provider readiness fields from company_analysis_readiness
  readiness_status: string | null;
  provider_mix: string | null;
  readiness_reason_codes: string[] | null;
  can_run_valuation: boolean | null;
  can_run_signal: boolean | null;
  // Phase 11A.5: valuation diagnostic fields from valuation_runs.assumptions->diagnostics
  mos_basis: string | null;
  scenario_count: number | null;
  uncertainty_category: string | null;
  distribution_collapsed: boolean | null;
  // Phase 12A.5: data-quality diagnostics lane from latest company_data_quality_snapshots
  data_quality_status: string | null;
  data_quality_warning_codes: string[] | null;
  price_validation_status: string | null;
  statement_completeness_status: string | null;
  statement_completeness_summary: string | null;
  fundamentals_provider_comparison_status: string | null;
  fundamentals_provider_comparison_summary: string | null;
}

// ---------------------------------------------------------------------------
// alert_history table
// ---------------------------------------------------------------------------
export interface AlertHistoryRow {
  id: string;
  alert_rule_id: string | null;
  company_id: string | null;
  channel: string;
  title: string;
  message: string;
  dedupe_key: string;
  sent_at: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// dashboard_watchlist_inactive view (005_watchlist_management.sql)
// ---------------------------------------------------------------------------
export interface InactiveWatchlistRow {
  watchlist_membership_id: string;
  company_id: string;
  ticker: string;
  name: string;
  exchange: string | null;
  country: string | null;
  currency: string;
  sector: string | null;
  removed_at: string | null;
}

// ---------------------------------------------------------------------------
// UI filter / sort state
// ---------------------------------------------------------------------------
// Valid values mirror the SQL CHECK constraint on signal_runs.final_signal:
//   strong_buy | buy | hold | sell | strong_sell | insufficient_data
// The frontend uppercases the stored value before comparison.
export type SignalFilter = "ALL" | "BUY" | "STRONG_BUY" | "SELL" | "STRONG_SELL" | "HOLD" | "INSUFFICIENT_DATA" | "TRACKING_ONLY";

export type SortKey =
  | "ticker"
  | "p_buy_adjusted"
  | "margin_of_safety_conservative"
  | "final_quality_score"
  | "final_signal";

// ---------------------------------------------------------------------------
// watchlist_add_requests table (006_watchlist_add_requests.sql)
// ---------------------------------------------------------------------------
export interface WatchlistAddRequest {
  id: string;
  user_id: string;
  watchlist_id: string;
  requested_ticker: string;
  requested_exchange: string | null;
  status: "pending" | "approved" | "rejected" | "failed" | "cancelled";
  company_id: string | null;
  error_code: string | null;
  error_message: string | null;
  requested_at: string;
  processed_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// companies table (frontend-readable subset for positions UI)
// ---------------------------------------------------------------------------
export interface CompanyOption {
  id: string;
  ticker: string;
  name: string;
  currency: string;
}

// ---------------------------------------------------------------------------
// positions table (016_positions.sql)
// ---------------------------------------------------------------------------
export interface PositionRow {
  id: string;
  user_id: string;
  company_id: string;
  entry_date: string;
  quantity: number;
  average_entry_price: number;
  currency: string;
  fees: number | null;
  notes: string | null;
  status: "active" | "closed";
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// dashboard_positions_latest view (017_positions_display_metrics.sql)
// ---------------------------------------------------------------------------
export interface PositionDashboardRow {
  id: string;
  user_id: string;
  company_id: string;
  ticker: string;
  name: string;
  entry_date: string;
  quantity: number;
  average_entry_price: number;
  currency: string;
  fees: number | null;
  notes: string | null;
  status: "active" | "closed";
  closed_at: string | null;
  price_date: string | null;
  current_price: number | null;
  price_currency: string | null;
  cost_basis: number | null;
  current_value: number | null;
  unrealized_gain_loss: number | null;
  unrealized_return_pct: number | null;
}

export interface PositionInput {
  company_id: string;
  entry_date: string;
  quantity: number;
  average_entry_price: number;
  currency: string;
  fees?: number | null;
  notes?: string | null;
  status: "active" | "closed";
  closed_at?: string | null;
}
