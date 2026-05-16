-- 022_portfolio_dashboard_views.sql
-- Phase 12E.1: display-only portfolio dashboard foundation.
--
-- Adds two read-only views built only from already persisted state:
--   - dashboard_portfolio_positions
--   - dashboard_portfolio_summary
--
-- The portfolio dashboard is decision-support only. It does not trigger
-- provider/API calls, pipeline execution, recalculation, portfolio advice,
-- rebalancing, tax logic, or FX normalization.

drop view if exists dashboard_portfolio_summary cascade;
drop view if exists dashboard_portfolio_positions cascade;

create view dashboard_portfolio_positions
with (security_invoker = true) as
with open_alerts as (
  select
    pra.position_id,
    count(*) filter (where pra.status in ('open', 'snoozed')) as open_review_alert_count,
    case
      when bool_or(pra.status in ('open', 'snoozed') and pra.severity = 'critical') then 'critical'
      when bool_or(pra.status in ('open', 'snoozed') and pra.severity = 'warning') then 'warning'
      when bool_or(pra.status in ('open', 'snoozed') and pra.severity = 'info') then 'info'
      else null
    end as highest_open_review_alert_severity
  from position_review_alerts pra
  group by pra.position_id
),
portfolio_rows as (
  select
    pos.id,
    pos.user_id,
    pos.company_id,
    pos.ticker,
    pos.name,
    c.sector,
    c.country,
    pos.entry_date,
    pos.quantity,
    pos.average_entry_price,
    pos.currency,
    pos.fees,
    pos.notes,
    pos.status,
    pos.closed_at,
    pos.price_date,
    pos.current_price,
    pos.price_currency,
    pos.cost_basis,
    pos.current_value,
    pos.unrealized_gain_loss,
    pos.unrealized_return_pct,
    pos.current_signal,
    pos.current_readiness_status,
    pos.current_data_quality_status,
    pos.current_quality_score,
    pos.current_valuation_low,
    pos.current_valuation_mid,
    pos.current_valuation_high,
    pos.current_margin_of_safety,
    pos.current_uncertainty_category,
    profile.confidence_level as thesis_confidence_level,
    coalesce(alerts.open_review_alert_count, 0) as open_review_alert_count,
    alerts.highest_open_review_alert_severity,
    case
      when pos.status = 'active'
        and pos.current_price is null
        then true
      else false
    end as missing_current_price,
    case
      when pos.status = 'active'
        and pos.current_price is not null
        and pos.price_currency is not null
        and pos.price_currency <> pos.currency
        then true
      else false
    end as currency_mismatch,
    case
      when pos.status = 'active'
        and pos.current_price is not null
        and pos.price_currency is not null
        and pos.price_currency = pos.currency
        and pos.cost_basis is not null
        and pos.current_value is not null
        and pos.unrealized_gain_loss is not null
        then true
      else false
    end as value_computable
  from dashboard_positions_latest pos
  join companies c on c.id = pos.company_id
  left join position_entry_profiles profile on profile.position_id = pos.id
  left join open_alerts alerts on alerts.position_id = pos.id
)
select
  portfolio_rows.*,
  case
    when portfolio_rows.value_computable
      and sum(portfolio_rows.current_value)
        filter (where portfolio_rows.value_computable)
        over () > 0
      then portfolio_rows.current_value
        / sum(portfolio_rows.current_value)
            filter (where portfolio_rows.value_computable)
            over ()
    else null
  end as position_weight_pct
from portfolio_rows
order by
  case portfolio_rows.status
    when 'active' then 0
    else 1
  end,
  portfolio_rows.current_value desc nulls last,
  portfolio_rows.ticker asc;

create view dashboard_portfolio_summary
with (security_invoker = true) as
with positions as (
  select *
  from dashboard_portfolio_positions
),
totals as (
  select
    count(*) filter (where status = 'active') as active_position_count,
    count(*) filter (where status = 'closed') as closed_position_count,
    count(*) filter (
      where status = 'active'
        and current_price is not null
    ) as active_positions_with_price,
    count(*) filter (where missing_current_price) as active_positions_missing_price,
    count(*) filter (where currency_mismatch) as active_positions_currency_mismatch,
    coalesce(sum(cost_basis) filter (where value_computable), 0::numeric) as computable_total_cost_basis,
    coalesce(sum(current_value) filter (where value_computable), 0::numeric) as computable_total_market_value,
    coalesce(sum(unrealized_gain_loss) filter (where value_computable), 0::numeric) as computable_total_unrealized_gain_loss,
    case
      when coalesce(sum(cost_basis) filter (where value_computable), 0::numeric) > 0
        then
          coalesce(sum(unrealized_gain_loss) filter (where value_computable), 0::numeric)
          / sum(cost_basis) filter (where value_computable)
      else null
    end as computable_total_unrealized_return_pct,
    coalesce(sum(open_review_alert_count) filter (where status = 'active'), 0::bigint) as open_review_alert_count,
    count(*) filter (
      where status = 'active'
        and current_data_quality_status = 'critical'
    ) as critical_data_quality_count,
    coalesce(sum(current_value) filter (where value_computable), 0::numeric) as computable_market_value_base
  from positions
)
select
  totals.*,
  coalesce(
    (
      select jsonb_agg(
        jsonb_build_object(
          'signal', signal_group.signal,
          'count', signal_group.position_count
        )
        order by signal_group.signal
      )
      from (
        select
          coalesce(current_signal, 'unknown') as signal,
          count(*) as position_count
        from positions
        where status = 'active'
        group by coalesce(current_signal, 'unknown')
      ) as signal_group
    ),
    '[]'::jsonb
  ) as positions_by_signal,
  coalesce(
    (
      select jsonb_agg(
        jsonb_build_object(
          'confidence_level', confidence_group.confidence_level,
          'count', confidence_group.position_count
        )
        order by confidence_group.confidence_level
      )
      from (
        select
          coalesce(thesis_confidence_level, 'unknown') as confidence_level,
          count(*) as position_count
        from positions
        where status = 'active'
        group by coalesce(thesis_confidence_level, 'unknown')
      ) as confidence_group
    ),
    '[]'::jsonb
  ) as positions_by_thesis_confidence,
  coalesce(
    (
      select jsonb_agg(
        jsonb_build_object(
          'ticker', concentration.ticker,
          'name', concentration.name,
          'current_value', concentration.current_value,
          'weight_pct', concentration.weight_pct
        )
        order by concentration.current_value desc, concentration.ticker
      )
      from (
        select
          ticker,
          name,
          current_value,
          position_weight_pct as weight_pct
        from positions
        where value_computable
      ) as concentration
    ),
    '[]'::jsonb
  ) as company_concentration,
  coalesce(
    (
      select jsonb_agg(
        jsonb_build_object(
          'sector', sector_group.sector,
          'current_value', sector_group.current_value,
          'weight_pct', sector_group.weight_pct
        )
        order by sector_group.current_value desc, sector_group.sector
      )
      from (
        select
          coalesce(sector, 'Unknown') as sector,
          sum(current_value) as current_value,
          case
            when totals.computable_market_value_base > 0
              then sum(current_value) / totals.computable_market_value_base
            else null
          end as weight_pct
        from positions
        cross join totals
        where value_computable
        group by coalesce(sector, 'Unknown'), totals.computable_market_value_base
      ) as sector_group
    ),
    '[]'::jsonb
  ) as sector_exposure,
  coalesce(
    (
      select jsonb_agg(
        jsonb_build_object(
          'country', geography_group.country,
          'current_value', geography_group.current_value,
          'weight_pct', geography_group.weight_pct
        )
        order by geography_group.current_value desc, geography_group.country
      )
      from (
        select
          coalesce(country, 'Unknown') as country,
          sum(current_value) as current_value,
          case
            when totals.computable_market_value_base > 0
              then sum(current_value) / totals.computable_market_value_base
            else null
          end as weight_pct
        from positions
        cross join totals
        where value_computable
        group by coalesce(country, 'Unknown'), totals.computable_market_value_base
      ) as geography_group
    ),
    '[]'::jsonb
  ) as geography_exposure
from totals;

revoke all on dashboard_portfolio_positions from public, anon, authenticated;
grant select on dashboard_portfolio_positions to authenticated, service_role;

revoke all on dashboard_portfolio_summary from public, anon, authenticated;
grant select on dashboard_portfolio_summary to authenticated, service_role;
