-- 015_dashboard_data_quality_lane.sql
-- Phase 12A.5: expose latest persisted data-quality diagnostics in the dashboard
-- as a separate read-only lane.
--
-- This migration:
--   1. creates latest_company_data_quality_snapshots
--   2. recreates dashboard_watchlist_latest with appended data-quality columns
--
-- The new fields are diagnostic-only. They do not change readiness,
-- valuation, signal generation, alerts, or pipeline behavior.
--
-- Security model:
--   - security_invoker = true on both views
--   - authenticated: SELECT only
--   - service_role:  SELECT only
--   - anon/public:   no access
--
-- Idempotent where practical.

drop view if exists dashboard_watchlist_latest cascade;
drop view if exists latest_company_data_quality_snapshots cascade;

create view latest_company_data_quality_snapshots
with (security_invoker = true) as
select distinct on (dq.company_id)
  dq.company_id,
  dq.snapshot_date,
  case
    when coalesce(jsonb_array_length(dq.warning_codes), 0) = 0 then 'healthy'
    when dq.price_validation_status = 'critical'
      or dq.details->'fundamentals_provider_comparison'->>'discrepancy_level' = 'critical'
      then 'critical'
    when not (
      dq.warning_codes @> '["price_divergence_warning"]'::jsonb
      or dq.warning_codes @> '["price_divergence_critical"]'::jsonb
      or dq.warning_codes @> '["incomplete_statement_set"]'::jsonb
      or dq.warning_codes @> '["missing_key_fields"]'::jsonb
      or dq.warning_codes @> '["insufficient_period_coverage"]'::jsonb
      or dq.warning_codes @> '["fundamentals_provider_discrepancy"]'::jsonb
    ) then 'not_comparable'
    else 'warning'
  end as data_quality_status,
  coalesce(
    array(select jsonb_array_elements_text(dq.warning_codes)),
    array[]::text[]
  ) as data_quality_warning_codes,
  dq.price_validation_status,
  dq.details->'statement_completeness'->>'status'
    as statement_completeness_status,
  case
    when dq.details->'statement_completeness' is null then null
    when dq.warning_codes @> '["no_statements_available"]'::jsonb
      then 'No annual statements available'
    when dq.warning_codes @> '["missing_key_fields"]'::jsonb
      and dq.warning_codes @> '["incomplete_statement_set"]'::jsonb
      then 'Missing key fields and statement coverage gaps'
    when dq.warning_codes @> '["missing_key_fields"]'::jsonb
      and dq.warning_codes @> '["insufficient_period_coverage"]'::jsonb
      then 'Missing key fields and limited annual history'
    when dq.warning_codes @> '["incomplete_statement_set"]'::jsonb
      and dq.warning_codes @> '["insufficient_period_coverage"]'::jsonb
      then 'Incomplete statement set and limited annual history'
    when dq.warning_codes @> '["missing_key_fields"]'::jsonb
      then 'Missing key fields'
    when dq.warning_codes @> '["incomplete_statement_set"]'::jsonb
      then 'Incomplete statement set'
    when dq.warning_codes @> '["insufficient_period_coverage"]'::jsonb
      then 'Limited annual history'
    else 'Complete'
  end as statement_completeness_summary,
  dq.details->'fundamentals_provider_comparison'->>'discrepancy_level'
    as fundamentals_provider_comparison_status,
  case
    when dq.details->'fundamentals_provider_comparison' is null then null
    when dq.details->'fundamentals_provider_comparison'->>'discrepancy_level' = 'not_comparable'
      and coalesce(
        (dq.details->'fundamentals_provider_comparison'->>'overlapping_period_count')::int,
        0
      ) = 0
      then 'No overlapping FMP and SEC annual periods'
    when dq.details->'fundamentals_provider_comparison'->>'discrepancy_level' = 'not_comparable'
      then 'Overlap exists but comparable fields were unavailable'
    when dq.details->'fundamentals_provider_comparison'->>'discrepancy_level' = 'critical'
      then coalesce(
        (
          select 'Material differences in ' || string_agg(replace(field_name, '_', ' '), ', ' order by field_name)
          from jsonb_array_elements_text(
            coalesce(
              dq.details->'fundamentals_provider_comparison'->'discrepant_fields',
              '[]'::jsonb
            )
          ) as fields(field_name)
        ),
        'Material provider differences detected'
      )
    when dq.details->'fundamentals_provider_comparison'->>'discrepancy_level' = 'warning'
      then coalesce(
        (
          select 'Differences in ' || string_agg(replace(field_name, '_', ' '), ', ' order by field_name)
          from jsonb_array_elements_text(
            coalesce(
              dq.details->'fundamentals_provider_comparison'->'discrepant_fields',
              '[]'::jsonb
            )
          ) as fields(field_name)
        ),
        'Provider differences detected'
      )
    else 'FMP and SEC annual overlap broadly matches'
  end as fundamentals_provider_comparison_summary
from company_data_quality_snapshots dq
order by dq.company_id, dq.snapshot_date desc, dq.updated_at desc, dq.created_at desc;

create view dashboard_watchlist_latest with (security_invoker = true) as
select distinct on (c.id)
  wc.id                             as watchlist_membership_id,
  c.id                              as company_id,
  c.ticker,
  c.name,
  c.exchange,
  c.country,
  c.currency,
  c.sector,
  c.industry,
  p.price_date,
  p.close                           as current_price,
  p.market_cap,
  r.roic,
  r.fcf_yield,
  r.net_debt_to_ebitda,
  r.news_sentiment_7d,
  q.final_quality_score,
  v.iv_p25,
  v.iv_p50,
  v.iv_p75,
  v.margin_of_safety_conservative,
  v.uncertainty_width,
  s.p_buy,
  s.p_buy_adjusted,
  s.p_sell,
  s.final_signal,
  s.red_flags,
  s.explanation,
  s.freshness_flag,
  ar.readiness_status,
  ar.provider_mix,
  ar.readiness_reason_codes,
  ar.can_run_valuation,
  ar.can_run_signal,
  v.assumptions->'diagnostics'->>'mos_basis'
                                        as mos_basis,
  (v.assumptions->'diagnostics'->>'scenario_count')::int
                                        as scenario_count,
  v.assumptions->'diagnostics'->>'uncertainty_category'
                                        as uncertainty_category,
  (v.assumptions->'diagnostics'->'warnings') @> '["distribution_collapsed"]'::jsonb
                                        as distribution_collapsed,
  coalesce(dq.data_quality_status, 'no_diagnostics')
                                        as data_quality_status,
  dq.data_quality_warning_codes,
  dq.price_validation_status,
  dq.statement_completeness_status,
  dq.statement_completeness_summary,
  dq.fundamentals_provider_comparison_status,
  dq.fundamentals_provider_comparison_summary
from companies c
join  watchlist_companies                   wc on wc.company_id  = c.id
join  watchlists                            wl on wl.id          = wc.watchlist_id
left join latest_price_eod                  p  on p.company_id   = c.id
left join latest_ratios_factors             r  on r.company_id   = c.id
left join latest_qualitative_scores         q  on q.company_id   = c.id
left join latest_valuation_runs             v  on v.company_id   = c.id
left join latest_signal_runs                s  on s.company_id   = c.id
left join analysis_readiness_latest         ar on ar.company_id  = c.id
left join latest_company_data_quality_snapshots dq on dq.company_id = c.id
where wc.active = true
order by c.id;

revoke all    on latest_company_data_quality_snapshots from public, anon, authenticated;
grant  select on latest_company_data_quality_snapshots to authenticated, service_role;

revoke all    on dashboard_watchlist_latest from public, anon, authenticated;
grant  select on dashboard_watchlist_latest to authenticated, service_role;
