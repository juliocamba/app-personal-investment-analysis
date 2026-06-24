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
  stored_final_signal: string | null;
  signal_display_state: string | null;
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
  // Read-only research-quality grouping from dashboard quality matrix projection
  quality_matrix_max_severity: string | null;
  quality_matrix_blocking_domains: string[] | null;
  quality_matrix_primary_codes: string[] | null;
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
  current_signal: string | null;
  current_readiness_status: string | null;
  current_data_quality_status: string | null;
  current_quality_score: number | null;
  current_valuation_low: number | null;
  current_valuation_mid: number | null;
  current_valuation_high: number | null;
  current_margin_of_safety: number | null;
  current_uncertainty_category: string | null;
}

// ---------------------------------------------------------------------------
// position_entry_profiles table (018_position_entry_profiles.sql)
// ---------------------------------------------------------------------------
export interface PositionEntryProfileRow {
  id: string;
  position_id: string;
  user_id: string;
  snapshot_taken_at: string;
  thesis_summary: string | null;
  why_bought: string | null;
  key_risks: string | null;
  target_price: number | null;
  target_price_currency: string | null;
  expected_holding_period: string | null;
  confidence_level: "low" | "medium" | "high" | null;
  catalysts: string | null;
  invalidation_criteria: string | null;
  entry_price: number | null;
  entry_price_date: string | null;
  entry_price_currency: string | null;
  entry_signal: string | null;
  entry_readiness_status: string | null;
  entry_data_quality_status: string | null;
  entry_quality_score: number | null;
  entry_current_price: number | null;
  entry_valuation_low: number | null;
  entry_valuation_mid: number | null;
  entry_valuation_high: number | null;
  entry_margin_of_safety: number | null;
  entry_uncertainty_category: string | null;
  entry_snapshot_details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PositionReviewAlertRow {
  id: string;
  position_id: string;
  user_id: string;
  company_id: string;
  alert_type:
    | "target_price_reached"
    | "signal_deterioration"
    | "readiness_deterioration"
    | "data_quality_deterioration";
  severity: "info" | "warning" | "critical";
  status: "open" | "snoozed" | "dismissed" | "resolved";
  title: string;
  message: string;
  details: Record<string, unknown>;
  dedupe_key: string;
  triggered_at: string;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  dismissed_at: string | null;
  dismissed_reason: string | null;
  snoozed_until: string | null;
  created_at: string;
  updated_at: string;
}

export type PositionReviewAlertLifecycleStatus = "open" | "snoozed" | "dismissed";

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

export interface PositionEntryProfileInput {
  thesis_summary?: string | null;
  why_bought?: string | null;
  key_risks?: string | null;
  target_price?: number | null;
  target_price_currency?: string | null;
  expected_holding_period?: string | null;
  confidence_level?: "low" | "medium" | "high" | null;
  catalysts?: string | null;
  invalidation_criteria?: string | null;
}

export interface PortfolioBreakdownCount {
  signal?: string;
  confidence_level?: string;
  count: number;
}

export interface PortfolioExposureItem {
  ticker?: string;
  name?: string;
  sector?: string;
  country?: string;
  current_value: number;
  weight_pct: number | null;
}

export interface PortfolioPositionRow {
  id: string;
  user_id: string;
  company_id: string;
  ticker: string;
  name: string;
  sector: string | null;
  country: string | null;
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
  current_signal: string | null;
  current_readiness_status: string | null;
  current_data_quality_status: string | null;
  current_quality_score: number | null;
  current_valuation_low: number | null;
  current_valuation_mid: number | null;
  current_valuation_high: number | null;
  current_margin_of_safety: number | null;
  current_uncertainty_category: string | null;
  thesis_confidence_level: "low" | "medium" | "high" | null;
  open_review_alert_count: number;
  highest_open_review_alert_severity: "info" | "warning" | "critical" | null;
  missing_current_price: boolean;
  currency_mismatch: boolean;
  value_computable: boolean;
  position_weight_pct: number | null;
}

export interface PortfolioSummaryRow {
  active_position_count: number;
  closed_position_count: number;
  active_positions_with_price: number;
  active_positions_missing_price: number;
  active_positions_currency_mismatch: number;
  computable_total_cost_basis: number;
  computable_total_market_value: number;
  computable_total_unrealized_gain_loss: number;
  computable_total_unrealized_return_pct: number | null;
  open_review_alert_count: number;
  critical_data_quality_count: number;
  positions_by_signal: PortfolioBreakdownCount[];
  positions_by_thesis_confidence: PortfolioBreakdownCount[];
  company_concentration: PortfolioExposureItem[];
  sector_exposure: PortfolioExposureItem[];
  geography_exposure: PortfolioExposureItem[];
}

export interface PortfolioPositionFxEurRow extends PortfolioPositionRow {
  normalized_cost_basis_eur: number | null;
  normalized_current_value_eur: number | null;
  normalized_unrealized_gain_loss_eur: number | null;
  normalized_position_weight_pct: number | null;
}

export interface PortfolioSummaryFxEurRow {
  normalized_total_cost_basis_eur: number;
  normalized_total_market_value_eur: number;
  normalized_total_unrealized_gain_loss_eur: number;
  normalized_total_unrealized_return_pct: number | null;
  positions_missing_fx_rate: number;
  positions_fx_normalized_count: number;
}

export interface SignalBacktestBucketSummaryRow {
  final_signal: string;
  horizon_days: number;
  observation_count: number;
  covered_observation_count: number;
  average_return: number | null;
  median_return: number | null;
  hit_rate: number | null;
  coverage_pct: number | null;
}

export interface SignalBacktestHorizonSummaryRow {
  horizon_days: number;
  observation_count: number;
  covered_observation_count: number;
  average_return: number | null;
  median_return: number | null;
  hit_rate: number | null;
  coverage_pct: number | null;
}

export interface SignalBacktestSegmentSummaryRow {
  final_signal: string;
  horizon_days: number;
  observation_count: number;
  covered_observation_count: number;
  average_return: number | null;
  median_return: number | null;
  hit_rate: number | null;
  coverage_pct: number | null;
  readiness_status_at_signal?: string;
  data_quality_status_at_signal?: string;
  sector_at_signal?: string;
}

export interface SignalBacktestStabilityRow {
  signal_bucket: string;
  observation_count: number;
  transition_count: number;
  flip_count: number;
  stable_transition_count: number;
  flip_rate: number | null;
  stability_pct: number | null;
  average_days_to_next_signal: number | null;
}

export interface SignalBacktestCoverageRow {
  signal_run_id: string;
  readiness_status_at_signal: string | null;
  data_quality_status_at_signal: string | null;
  sector_at_signal: string | null;
  has_price_30d: boolean;
  has_price_90d: boolean;
  has_price_180d: boolean;
  has_price_365d: boolean;
}

export interface SignalBacktestInterpretationSummaryRow {
  total_observations: number;
  evaluatable_observations: number;
  historical_coverage_pct: number | null;
  earliest_signal_date: string | null;
  latest_signal_date: string | null;
  signal_history_days: number | null;
  dataset_maturity: "LOW" | "MEDIUM" | "HIGH";
}
