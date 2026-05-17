-- 026_signal_backtest_interpretation_summary.sql
-- Phase 12F.4: top-level descriptive interpretation summary for historical
-- signal validation.
--
-- Adds a read-only summary view over already persisted backtest observations.
-- This view is descriptive only:
--   - it does not change backtest methodology
--   - it does not change live signal generation
--   - it does not simulate a strategy
--   - it does not make future-performance claims

drop view if exists signal_backtest_interpretation_summary cascade;

create view signal_backtest_interpretation_summary
with (security_invoker = true) as
with base as (
  select
    count(*) as total_observations,
    count(*) filter (
      where has_price_30d
         or has_price_90d
         or has_price_180d
         or has_price_365d
    ) as evaluatable_observations,
    (
      avg(case when has_price_30d then 1.0 else 0.0 end)
      + avg(case when has_price_90d then 1.0 else 0.0 end)
      + avg(case when has_price_180d then 1.0 else 0.0 end)
      + avg(case when has_price_365d then 1.0 else 0.0 end)
    ) / 4.0 as historical_coverage_pct,
    min(signal_date) as earliest_signal_date,
    max(signal_date) as latest_signal_date
  from signal_backtest_observations
)
select
  total_observations,
  evaluatable_observations,
  historical_coverage_pct,
  earliest_signal_date,
  latest_signal_date,
  (latest_signal_date - earliest_signal_date) as signal_history_days,
  case
    when total_observations >= 300
      and historical_coverage_pct >= 0.75
      and coalesce((latest_signal_date - earliest_signal_date), 0) >= 365
      then 'HIGH'
    when total_observations < 100
      or historical_coverage_pct < 0.50
      or coalesce((latest_signal_date - earliest_signal_date), 0) < 180
      then 'LOW'
    else 'MEDIUM'
  end as dataset_maturity
from base;

revoke all on signal_backtest_interpretation_summary from public, anon, authenticated;
grant select on signal_backtest_interpretation_summary to authenticated, service_role;
