-- 017_positions_display_metrics.sql
-- Phase 12B.2: display-only current value and unrealized P&L for positions.
--
-- Adds a read-only dashboard_positions_latest view for manual positions.
-- This view is intentionally separate from dashboard_watchlist_latest and does
-- not alter pipeline behavior, signals, readiness, valuation, alerts, or
-- data-quality diagnostics.
--
-- No FX conversion is performed in this phase. Computed metrics are populated
-- only when:
--   - the position is active
--   - a latest stored price exists
--   - the latest price currency matches the position currency

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
  end as unrealized_return_pct
from positions pos
join companies c on c.id = pos.company_id
left join latest_price_eod p on p.company_id = pos.company_id
order by
  case pos.status
    when 'active' then 0
    else 1
  end,
  pos.entry_date desc,
  pos.created_at desc;

revoke all on dashboard_positions_latest from public, anon, authenticated;
grant select on dashboard_positions_latest to authenticated, service_role;
