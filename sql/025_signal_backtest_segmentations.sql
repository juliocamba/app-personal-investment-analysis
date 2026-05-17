-- 025_signal_backtest_segmentations.sql
-- Phase 12F.2: descriptive signal-validation segmentation and stability views.
--
-- Adds read-only research views over already persisted historical validation
-- observations. These views are descriptive only:
--   - no live model changes
--   - no strategy simulation
--   - no threshold tuning
--   - no performance claims
--
-- Stability analysis is derived from chronological signal transitions only.
-- No future prices, provider calls, or recalculation of analytical lanes occur.

drop view if exists backtest_signal_by_readiness cascade;
drop view if exists backtest_signal_by_data_quality cascade;
drop view if exists backtest_signal_by_sector cascade;
drop view if exists backtest_signal_stability cascade;

create view backtest_signal_by_readiness
with (security_invoker = true) as
with horizon_rows as (
  select
    coalesce(readiness_status_at_signal, 'unknown') as readiness_status_at_signal,
    final_signal,
    30 as horizon_days,
    return_30d as forward_return,
    has_price_30d as has_price
  from signal_backtest_observations
  union all
  select
    coalesce(readiness_status_at_signal, 'unknown'),
    final_signal,
    90,
    return_90d,
    has_price_90d
  from signal_backtest_observations
  union all
  select
    coalesce(readiness_status_at_signal, 'unknown'),
    final_signal,
    180,
    return_180d,
    has_price_180d
  from signal_backtest_observations
  union all
  select
    coalesce(readiness_status_at_signal, 'unknown'),
    final_signal,
    365,
    return_365d,
    has_price_365d
  from signal_backtest_observations
)
select
  readiness_status_at_signal,
  final_signal,
  horizon_days,
  count(*) as observation_count,
  count(*) filter (where has_price) as covered_observation_count,
  avg(forward_return) filter (where has_price) as average_return,
  percentile_cont(0.5) within group (order by forward_return)
    filter (where has_price) as median_return,
  avg(case when has_price and forward_return > 0 then 1.0 else 0.0 end)
    filter (where has_price) as hit_rate,
  avg(case when has_price then 1.0 else 0.0 end) as coverage_pct
from horizon_rows
group by readiness_status_at_signal, final_signal, horizon_days
order by readiness_status_at_signal, final_signal, horizon_days;

create view backtest_signal_by_data_quality
with (security_invoker = true) as
with horizon_rows as (
  select
    coalesce(data_quality_status_at_signal, 'unknown') as data_quality_status_at_signal,
    final_signal,
    30 as horizon_days,
    return_30d as forward_return,
    has_price_30d as has_price
  from signal_backtest_observations
  union all
  select
    coalesce(data_quality_status_at_signal, 'unknown'),
    final_signal,
    90,
    return_90d,
    has_price_90d
  from signal_backtest_observations
  union all
  select
    coalesce(data_quality_status_at_signal, 'unknown'),
    final_signal,
    180,
    return_180d,
    has_price_180d
  from signal_backtest_observations
  union all
  select
    coalesce(data_quality_status_at_signal, 'unknown'),
    final_signal,
    365,
    return_365d,
    has_price_365d
  from signal_backtest_observations
)
select
  data_quality_status_at_signal,
  final_signal,
  horizon_days,
  count(*) as observation_count,
  count(*) filter (where has_price) as covered_observation_count,
  avg(forward_return) filter (where has_price) as average_return,
  percentile_cont(0.5) within group (order by forward_return)
    filter (where has_price) as median_return,
  avg(case when has_price and forward_return > 0 then 1.0 else 0.0 end)
    filter (where has_price) as hit_rate,
  avg(case when has_price then 1.0 else 0.0 end) as coverage_pct
from horizon_rows
group by data_quality_status_at_signal, final_signal, horizon_days
order by data_quality_status_at_signal, final_signal, horizon_days;

create view backtest_signal_by_sector
with (security_invoker = true) as
with horizon_rows as (
  select
    coalesce(sector_at_signal, 'unknown') as sector_at_signal,
    final_signal,
    30 as horizon_days,
    return_30d as forward_return,
    has_price_30d as has_price
  from signal_backtest_observations
  union all
  select
    coalesce(sector_at_signal, 'unknown'),
    final_signal,
    90,
    return_90d,
    has_price_90d
  from signal_backtest_observations
  union all
  select
    coalesce(sector_at_signal, 'unknown'),
    final_signal,
    180,
    return_180d,
    has_price_180d
  from signal_backtest_observations
  union all
  select
    coalesce(sector_at_signal, 'unknown'),
    final_signal,
    365,
    return_365d,
    has_price_365d
  from signal_backtest_observations
)
select
  sector_at_signal,
  final_signal,
  horizon_days,
  count(*) as observation_count,
  count(*) filter (where has_price) as covered_observation_count,
  avg(forward_return) filter (where has_price) as average_return,
  percentile_cont(0.5) within group (order by forward_return)
    filter (where has_price) as median_return,
  avg(case when has_price and forward_return > 0 then 1.0 else 0.0 end)
    filter (where has_price) as hit_rate,
  avg(case when has_price then 1.0 else 0.0 end) as coverage_pct
from horizon_rows
group by sector_at_signal, final_signal, horizon_days
order by sector_at_signal, final_signal, horizon_days;

create view backtest_signal_stability
with (security_invoker = true) as
with ordered_signals as (
  select
    signal_run_id,
    company_id,
    signal_date,
    final_signal,
    lead(final_signal) over (
      partition by company_id
      order by signal_date, signal_run_id
    ) as next_signal,
    lead(signal_date) over (
      partition by company_id
      order by signal_date, signal_run_id
    ) as next_signal_date
  from signal_backtest_observations
)
select
  final_signal as signal_bucket,
  count(*) as observation_count,
  count(*) filter (where next_signal is not null) as transition_count,
  count(*) filter (where next_signal is not null and next_signal <> final_signal) as flip_count,
  count(*) filter (where next_signal is not null and next_signal = final_signal) as stable_transition_count,
  avg(case when next_signal is not null and next_signal <> final_signal then 1.0 else 0.0 end)
    filter (where next_signal is not null) as flip_rate,
  avg(case when next_signal is not null and next_signal = final_signal then 1.0 else 0.0 end)
    filter (where next_signal is not null) as stability_pct,
  avg((next_signal_date - signal_date)::numeric)
    filter (where next_signal is not null) as average_days_to_next_signal
from ordered_signals
group by final_signal
order by
  case final_signal
    when 'strong_buy' then 1
    when 'buy' then 2
    when 'hold' then 3
    when 'sell' then 4
    when 'strong_sell' then 5
    else 6
  end;

revoke all on backtest_signal_by_readiness from public, anon, authenticated;
grant select on backtest_signal_by_readiness to authenticated, service_role;

revoke all on backtest_signal_by_data_quality from public, anon, authenticated;
grant select on backtest_signal_by_data_quality to authenticated, service_role;

revoke all on backtest_signal_by_sector from public, anon, authenticated;
grant select on backtest_signal_by_sector to authenticated, service_role;

revoke all on backtest_signal_stability from public, anon, authenticated;
grant select on backtest_signal_stability to authenticated, service_role;
