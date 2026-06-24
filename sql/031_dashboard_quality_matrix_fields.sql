-- 031_dashboard_quality_matrix_fields.sql
-- Read-only dashboard projection for research-quality grouping.
--
-- This migration does NOT change readiness, valuation, signal logic, signal
-- labels, thresholds, providers, or dashboard suppression behavior. It only
-- appends compact quality-matrix summary fields for display.

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
  end                               as signal_display_state,
  case
    when ar.can_run_valuation is false and ar.can_run_signal is false
      then 'blocks_both'
    when coalesce(v.assumptions->'diagnostics'->>'valuation_sanity_status', '') in ('unreliable', 'model_failure')
      then 'blocks_valuation'
    when ar.can_run_valuation is false
      then 'blocks_valuation'
    when ar.can_run_signal is false
      then 'blocks_signal'
    when coalesce(v.assumptions->'diagnostics'->>'valuation_sanity_status', '') = 'high_uncertainty'
      or ar.readiness_status in ('partial_analysis', 'provider_limited')
      or coalesce(array_length(dq.data_quality_warning_codes, 1), 0) > 0
      then 'confidence_limited'
    else 'informational'
  end                               as quality_matrix_max_severity,
  case
    when ar.can_run_valuation is false and ar.can_run_signal is false
      then array['signal', 'valuation']::text[]
    when coalesce(v.assumptions->'diagnostics'->>'valuation_sanity_status', '') in ('unreliable', 'model_failure')
      or ar.can_run_valuation is false
      then array['valuation']::text[]
    when ar.can_run_signal is false
      then array['signal']::text[]
    else array[]::text[]
  end                               as quality_matrix_blocking_domains,
  case
    when ar.can_run_valuation is false and ar.can_run_signal is false then (
      select coalesce(array_agg(code order by source_rank, code), array[]::text[])
      from (
        select code, min(source_rank) as source_rank
        from (
          select unnest(coalesce(ar.readiness_reason_codes, array[]::text[])) as code, 1 as source_rank
          union all
          select unnest(coalesce(dq.data_quality_warning_codes, array[]::text[])) as code, 2 as source_rank
        ) raw_codes
        where code is not null and code <> ''
        group by code
        order by min(source_rank), code
        limit 5
      ) ranked_codes
    )
    when coalesce(v.assumptions->'diagnostics'->>'valuation_sanity_status', '') in ('unreliable', 'model_failure') then (
      select coalesce(array_agg(code order by code), array[]::text[])
      from (
        select code
        from jsonb_array_elements_text(
          coalesce(v.assumptions->'diagnostics'->'valuation_sanity_reason_codes', '[]'::jsonb)
        ) as reason_codes(code)
        where code is not null and code <> ''
        group by code
        order by code
        limit 5
      ) ranked_codes
    )
    when ar.can_run_valuation is false or ar.can_run_signal is false then (
      select coalesce(array_agg(code order by source_rank, code), array[]::text[])
      from (
        select code, min(source_rank) as source_rank
        from (
          select unnest(coalesce(ar.readiness_reason_codes, array[]::text[])) as code, 1 as source_rank
          union all
          select unnest(coalesce(dq.data_quality_warning_codes, array[]::text[])) as code, 2 as source_rank
        ) raw_codes
        where code is not null and code <> ''
        group by code
        order by min(source_rank), code
        limit 5
      ) ranked_codes
    )
    when coalesce(v.assumptions->'diagnostics'->>'valuation_sanity_status', '') = 'high_uncertainty'
      or ar.readiness_status in ('partial_analysis', 'provider_limited')
      or coalesce(array_length(dq.data_quality_warning_codes, 1), 0) > 0
    then (
      select coalesce(array_agg(code order by source_rank, code), array[]::text[])
      from (
        select code, min(source_rank) as source_rank
        from (
          select code, 1 as source_rank
          from jsonb_array_elements_text(
            coalesce(v.assumptions->'diagnostics'->'valuation_sanity_reason_codes', '[]'::jsonb)
          ) as valuation_codes(code)
          union all
          select unnest(coalesce(ar.readiness_reason_codes, array[]::text[])) as code, 2 as source_rank
          union all
          select unnest(coalesce(dq.data_quality_warning_codes, array[]::text[])) as code, 3 as source_rank
        ) raw_codes
        where code is not null and code <> ''
        group by code
        order by min(source_rank), code
        limit 5
      ) ranked_codes
    )
    else array[]::text[]
  end                               as quality_matrix_primary_codes
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
