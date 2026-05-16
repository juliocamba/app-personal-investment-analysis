-- 023_portfolio_dashboard_fx_normalized_views.sql
-- Phase 12E.2: optional EUR-normalized portfolio estimates.
--
-- Adds separate read-only FX-normalized portfolio views without modifying the
-- conservative 12E.1 baseline views.
--
-- These estimates:
--   - use only persisted fx_rates
--   - match FX by exact price_date only
--   - never normalize rows already flagged with currency_mismatch
--   - never estimate missing FX coverage
--   - remain display-only and decision-support only

drop view if exists dashboard_portfolio_summary_fx_eur cascade;
drop view if exists dashboard_portfolio_positions_fx_eur cascade;

create view dashboard_portfolio_positions_fx_eur
with (security_invoker = true) as
with eur_rates as (
  select
    rate_date,
    quote_currency,
    rate
  from fx_rates
  where base_currency = 'EUR'
    and provider = 'ECB'
)
select
  pos.*,
  case
    when pos.value_computable
      and not pos.currency_mismatch
      and pos.currency = 'EUR'
      then pos.cost_basis
    when pos.value_computable
      and not pos.currency_mismatch
      and pos.currency <> 'EUR'
      and fx.rate is not null
      then pos.cost_basis / fx.rate
    else null
  end as normalized_cost_basis_eur,
  case
    when pos.value_computable
      and not pos.currency_mismatch
      and pos.currency = 'EUR'
      then pos.current_value
    when pos.value_computable
      and not pos.currency_mismatch
      and pos.currency <> 'EUR'
      and fx.rate is not null
      then pos.current_value / fx.rate
    else null
  end as normalized_current_value_eur,
  case
    when pos.value_computable
      and not pos.currency_mismatch
      and pos.currency = 'EUR'
      then pos.unrealized_gain_loss
    when pos.value_computable
      and not pos.currency_mismatch
      and pos.currency <> 'EUR'
      and fx.rate is not null
      then pos.unrealized_gain_loss / fx.rate
    else null
  end as normalized_unrealized_gain_loss_eur,
  case
    when (
      case
        when pos.value_computable
          and not pos.currency_mismatch
          and pos.currency = 'EUR'
          then pos.current_value
        when pos.value_computable
          and not pos.currency_mismatch
          and pos.currency <> 'EUR'
          and fx.rate is not null
          then pos.current_value / fx.rate
        else null
      end
    ) is not null
      and sum(
        case
          when pos.value_computable
            and not pos.currency_mismatch
            and pos.currency = 'EUR'
            then pos.current_value
          when pos.value_computable
            and not pos.currency_mismatch
            and pos.currency <> 'EUR'
            and fx.rate is not null
            then pos.current_value / fx.rate
          else null
        end
      ) over () > 0
      then (
        case
          when pos.value_computable
            and not pos.currency_mismatch
            and pos.currency = 'EUR'
            then pos.current_value
          when pos.value_computable
            and not pos.currency_mismatch
            and pos.currency <> 'EUR'
            and fx.rate is not null
            then pos.current_value / fx.rate
          else null
        end
      ) / sum(
        case
          when pos.value_computable
            and not pos.currency_mismatch
            and pos.currency = 'EUR'
            then pos.current_value
          when pos.value_computable
            and not pos.currency_mismatch
            and pos.currency <> 'EUR'
            and fx.rate is not null
            then pos.current_value / fx.rate
          else null
        end
      ) over ()
    else null
  end as normalized_position_weight_pct
from dashboard_portfolio_positions pos
left join eur_rates fx
  on fx.rate_date = pos.price_date
 and fx.quote_currency = pos.currency
order by
  case pos.status
    when 'active' then 0
    else 1
  end,
  normalized_current_value_eur desc nulls last,
  pos.ticker asc;

create view dashboard_portfolio_summary_fx_eur
with (security_invoker = true) as
with positions as (
  select *
  from dashboard_portfolio_positions_fx_eur
)
select
  coalesce(sum(normalized_cost_basis_eur), 0::numeric) as normalized_total_cost_basis_eur,
  coalesce(sum(normalized_current_value_eur), 0::numeric) as normalized_total_market_value_eur,
  coalesce(sum(normalized_unrealized_gain_loss_eur), 0::numeric) as normalized_total_unrealized_gain_loss_eur,
  case
    when coalesce(sum(normalized_cost_basis_eur), 0::numeric) > 0
      then coalesce(sum(normalized_unrealized_gain_loss_eur), 0::numeric)
         / sum(normalized_cost_basis_eur)
    else null
  end as normalized_total_unrealized_return_pct,
  count(*) filter (
    where status = 'active'
      and value_computable
      and not currency_mismatch
      and currency <> 'EUR'
      and normalized_current_value_eur is null
  ) as positions_missing_fx_rate,
  count(*) filter (
    where status = 'active'
      and normalized_current_value_eur is not null
  ) as positions_fx_normalized_count
from positions;

revoke all on dashboard_portfolio_positions_fx_eur from public, anon, authenticated;
grant select on dashboard_portfolio_positions_fx_eur to authenticated, service_role;

revoke all on dashboard_portfolio_summary_fx_eur from public, anon, authenticated;
grant select on dashboard_portfolio_summary_fx_eur to authenticated, service_role;
