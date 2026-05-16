-- 019_positions_current_comparison_fields.sql
-- Phase 12C.2: improve positions current-vs-entry comparison using persisted
-- read-only app state only.
--
-- Recreates dashboard_positions_latest additively with appended current-state
-- analytical fields for positions. This view remains intentionally separate
-- from dashboard_watchlist_latest and does not alter pipeline behavior,
-- signals, readiness logic, valuation logic, alerts, or data-quality logic.
--
-- No provider calls, pipeline execution, or analytical recalculation occur in
-- this phase. The view joins only to already-persisted latest views/tables.

drop view if exists dashboard_positions_latest cascade;

create view dashboard_positions_latest
with (security_invoker = true) as
select
  pos.id,
  pos.user_id,
  pos.company_id,
  c.ticker,
  c.name,
  pos.entry_date,
  pos.quantity,
  pos.average_entry_price,
  pos.currency,
  pos.fees,
  pos.notes,
  pos.status,
  pos.closed_at,
  p.price_date,
  p.close as current_price,
  p.currency as price_currency,
  case
    when pos.status = 'active'
      and p.close is not null
      and p.currency is not null
      and p.currency = pos.currency
      then (pos.quantity * pos.average_entry_price) + coalesce(pos.fees, 0)
    else null
  end as cost_basis,
  case
    when pos.status = 'active'
      and p.close is not null
      and p.currency is not null
      and p.currency = pos.currency
      then pos.quantity * p.close
    else null
  end as current_value,
  case
    when pos.status = 'active'
      and p.close is not null
      and p.currency is not null
      and p.currency = pos.currency
      then (pos.quantity * p.close)
         - ((pos.quantity * pos.average_entry_price) + coalesce(pos.fees, 0))
    else null
  end as unrealized_gain_loss,
  case
    when pos.status = 'active'
      and p.close is not null
      and p.currency is not null
      and p.currency = pos.currency
      and ((pos.quantity * pos.average_entry_price) + coalesce(pos.fees, 0)) > 0
      then (
        (
          (pos.quantity * p.close)
          - ((pos.quantity * pos.average_entry_price) + coalesce(pos.fees, 0))
        )
        / ((pos.quantity * pos.average_entry_price) + coalesce(pos.fees, 0))
      )
    else null
  end as unrealized_return_pct,
  signal_snap.final_signal as current_signal,
  readiness_snap.readiness_status as current_readiness_status,
  dq_snap.data_quality_status as current_data_quality_status,
  quality_snap.final_quality_score as current_quality_score,
  valuation_snap.iv_p25 as current_valuation_low,
  valuation_snap.iv_p50 as current_valuation_mid,
  valuation_snap.iv_p75 as current_valuation_high,
  valuation_snap.margin_of_safety_conservative as current_margin_of_safety,
  valuation_snap.uncertainty_category as current_uncertainty_category
from positions pos
join companies c on c.id = pos.company_id
left join latest_price_eod p on p.company_id = pos.company_id
left join latest_signal_runs signal_snap on signal_snap.company_id = pos.company_id
left join analysis_readiness_latest readiness_snap on readiness_snap.company_id = pos.company_id
left join latest_company_data_quality_snapshots dq_snap on dq_snap.company_id = pos.company_id
left join latest_qualitative_scores quality_snap on quality_snap.company_id = pos.company_id
left join (
  select
    company_id,
    iv_p25,
    iv_p50,
    iv_p75,
    margin_of_safety_conservative,
    assumptions->'diagnostics'->>'uncertainty_category' as uncertainty_category
  from latest_valuation_runs
) valuation_snap on valuation_snap.company_id = pos.company_id
order by
  case pos.status
    when 'active' then 0
    else 1
  end,
  pos.entry_date desc,
  pos.created_at desc;

revoke all on dashboard_positions_latest from public, anon, authenticated;
grant select on dashboard_positions_latest to authenticated, service_role;
