-- 030_dashboard_signal_display_state.sql
-- Phase 12G Slice 3C: expose a display-state layer for current-state signal
-- interpretation while preserving raw persisted signal history.
--
-- This migration does NOT change signal thresholds, signal labels, valuation
-- math, readiness taxonomy, or any persisted historical rows. It only adds
-- diagnostic projection fields to the dashboard watchlist view.

create or replace view dashboard_watchlist_latest with (security_invoker = true) as
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
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else v.iv_p25
  end                               as iv_p25,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else v.iv_p50
  end                               as iv_p50,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else v.iv_p75
  end                               as iv_p75,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else v.margin_of_safety_conservative
  end                               as margin_of_safety_conservative,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else v.uncertainty_width
  end                               as uncertainty_width,
  case
    when ar.can_run_signal is false then null
    else s.p_buy
  end                               as p_buy,
  case
    when ar.can_run_signal is false then null
    else s.p_buy_adjusted
  end                               as p_buy_adjusted,
  case
    when ar.can_run_signal is false then null
    else s.p_sell
  end                               as p_sell,
  case
    when ar.can_run_signal is false then null
    else s.final_signal
  end                               as final_signal,
  case
    when ar.can_run_signal is false then null
    else s.red_flags
  end                               as red_flags,
  case
    when ar.can_run_signal is false then null
    else s.explanation
  end                               as explanation,
  case
    when ar.can_run_signal is false then null
    else s.freshness_flag
  end                               as freshness_flag,
  ar.readiness_status,
  ar.provider_mix,
  ar.readiness_reason_codes,
  ar.can_run_valuation,
  ar.can_run_signal,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else v.assumptions->'diagnostics'->>'mos_basis'
  end                               as mos_basis,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else (v.assumptions->'diagnostics'->>'scenario_count')::int
  end                               as scenario_count,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else v.assumptions->'diagnostics'->>'uncertainty_category'
  end                               as uncertainty_category,
  case
    when ar.can_run_valuation is false
      or coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)
    then null
    else (v.assumptions->'diagnostics'->'warnings') @> '["distribution_collapsed"]'::jsonb
  end                               as distribution_collapsed,
  coalesce(dq.data_quality_status, 'no_diagnostics')
                                        as data_quality_status,
  dq.data_quality_warning_codes,
  dq.price_validation_status,
  dq.statement_completeness_status,
  dq.statement_completeness_summary,
  dq.fundamentals_provider_comparison_status,
  dq.fundamentals_provider_comparison_summary,
  s.final_signal                    as stored_final_signal,
  case
    when ar.can_run_signal is false then
      case when s.final_signal is null then 'no_signal' else 'readiness_suppressed' end
    when s.final_signal is null then 'no_signal'
    else 'analytical_signal'
  end                               as signal_display_state
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

revoke all    on dashboard_watchlist_latest from public, anon, authenticated;
grant  select on dashboard_watchlist_latest to authenticated, service_role;