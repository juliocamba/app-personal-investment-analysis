-- 024_signal_backtest_observations.sql
-- Phase 12F.1: historical signal validation foundation.
--
-- Adds a separate research/backtest lane for validating persisted signal
-- outputs against later persisted price history. This infrastructure is
-- descriptive only:
--   - it does not change live signal generation
--   - it does not recalculate valuation, readiness, or data-quality logic
--   - it does not simulate a strategy or make performance claims
--
-- Point-in-time rule:
--   - observations are anchored on persisted signal_runs.signal_date
--   - forward outcomes are calculated by a separate backend refresh job using
--     only already stored data
--   - no lookahead assumptions or price imputation are allowed

create table if not exists signal_backtest_observations (
  signal_run_id                               uuid primary key
                                                   references signal_runs(id) on delete cascade,
  company_id                                  uuid not null
                                                   references companies(id) on delete cascade,
  signal_date                                 date not null,
  model_version                               text not null,
  final_signal                                text not null,
  p_buy                                       numeric,
  p_buy_adjusted                              numeric,
  p_sell                                      numeric,
  signal_price                                numeric,
  signal_price_currency                       text,
  readiness_status_at_signal                  text,
  data_quality_status_at_signal               text,
  sector_at_signal                            text,
  market_cap_at_signal                        numeric,
  valuation_mos_at_signal                     numeric,
  valuation_uncertainty_category_at_signal    text,
  return_30d                                  numeric,
  return_90d                                  numeric,
  return_180d                                 numeric,
  return_365d                                 numeric,
  price_30d                                   numeric,
  price_90d                                   numeric,
  price_180d                                  numeric,
  price_365d                                  numeric,
  price_date_30d                              date,
  price_date_90d                              date,
  price_date_180d                             date,
  price_date_365d                             date,
  has_price_30d                               boolean not null default false,
  has_price_90d                               boolean not null default false,
  has_price_180d                              boolean not null default false,
  has_price_365d                              boolean not null default false,
  coverage_gap_30d                            boolean not null default true,
  coverage_gap_90d                            boolean not null default true,
  coverage_gap_180d                           boolean not null default true,
  coverage_gap_365d                           boolean not null default true,
  created_at                                  timestamptz not null default now(),
  updated_at                                  timestamptz not null default now(),

  constraint signal_backtest_observations_final_signal_check check (
    final_signal in (
      'strong_buy',
      'buy',
      'hold',
      'sell',
      'strong_sell',
      'insufficient_data'
    )
  ),
  constraint signal_backtest_observations_30d_coverage_check check (
    (has_price_30d and not coverage_gap_30d)
    or ((not has_price_30d) and coverage_gap_30d)
  ),
  constraint signal_backtest_observations_90d_coverage_check check (
    (has_price_90d and not coverage_gap_90d)
    or ((not has_price_90d) and coverage_gap_90d)
  ),
  constraint signal_backtest_observations_180d_coverage_check check (
    (has_price_180d and not coverage_gap_180d)
    or ((not has_price_180d) and coverage_gap_180d)
  ),
  constraint signal_backtest_observations_365d_coverage_check check (
    (has_price_365d and not coverage_gap_365d)
    or ((not has_price_365d) and coverage_gap_365d)
  )
);

drop trigger if exists update_signal_backtest_observations_updated_at
  on signal_backtest_observations;
create trigger update_signal_backtest_observations_updated_at
  before update on signal_backtest_observations
  for each row execute function update_updated_at_column();

alter table signal_backtest_observations enable row level security;

drop policy if exists "authenticated read signal backtest observations"
  on signal_backtest_observations;
create policy "authenticated read signal backtest observations"
  on signal_backtest_observations
  for select to authenticated using (true);

revoke all on signal_backtest_observations from public, anon, authenticated;
grant select on signal_backtest_observations to authenticated;
grant select, insert, update, delete on signal_backtest_observations to service_role;

drop view if exists signal_backtest_summary_by_bucket cascade;
drop view if exists signal_backtest_summary_by_horizon cascade;

create view signal_backtest_summary_by_bucket
with (security_invoker = true) as
with horizon_rows as (
  select final_signal, 30 as horizon_days, return_30d as forward_return, has_price_30d as has_price
  from signal_backtest_observations
  union all
  select final_signal, 90 as horizon_days, return_90d as forward_return, has_price_90d as has_price
  from signal_backtest_observations
  union all
  select final_signal, 180 as horizon_days, return_180d as forward_return, has_price_180d as has_price
  from signal_backtest_observations
  union all
  select final_signal, 365 as horizon_days, return_365d as forward_return, has_price_365d as has_price
  from signal_backtest_observations
)
select
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
group by final_signal, horizon_days
order by
  case final_signal
    when 'strong_buy' then 1
    when 'buy' then 2
    when 'hold' then 3
    when 'sell' then 4
    when 'strong_sell' then 5
    else 6
  end,
  horizon_days;

create view signal_backtest_summary_by_horizon
with (security_invoker = true) as
with horizon_rows as (
  select 30 as horizon_days, return_30d as forward_return, has_price_30d as has_price
  from signal_backtest_observations
  union all
  select 90 as horizon_days, return_90d as forward_return, has_price_90d as has_price
  from signal_backtest_observations
  union all
  select 180 as horizon_days, return_180d as forward_return, has_price_180d as has_price
  from signal_backtest_observations
  union all
  select 365 as horizon_days, return_365d as forward_return, has_price_365d as has_price
  from signal_backtest_observations
)
select
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
group by horizon_days
order by horizon_days;

revoke all on signal_backtest_summary_by_bucket from public, anon, authenticated;
grant select on signal_backtest_summary_by_bucket to authenticated, service_role;

revoke all on signal_backtest_summary_by_horizon from public, anon, authenticated;
grant select on signal_backtest_summary_by_horizon to authenticated, service_role;
