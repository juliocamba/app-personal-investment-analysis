-- 010_analysis_readiness_latest_view.sql
-- Phase 10C.3: current-state readiness snapshot table and views.
--
-- Additive: only adds a new table and view objects.
-- Safe to apply after 009_price_eod_metadata_and_precedence.sql.
-- Requires: 001–009 already applied.

-- ── 1. Create company_analysis_readiness ─────────────────────────────────────
-- One current-state row per company_id.  Written by the backend pipeline
-- after successful readiness classification.  Never written by authenticated
-- users or the frontend.  Replaces the previous snapshot on each pipeline run.

create table if not exists company_analysis_readiness (
  company_id             uuid        primary key
                                     references companies(id) on delete cascade,
  readiness_status       text        not null,
  provider_mix           text,
  readiness_reason_codes text[]      not null default '{}',
  can_run_valuation      boolean     not null,
  can_run_signal         boolean     not null,
  limiting_domain        text,
  readiness_updated_at   timestamptz not null,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),

  constraint check_readiness_status check (
    readiness_status in (
      'analysis_ready',
      'partial_analysis',
      'tracking_only',
      'provider_limited',
      'unsupported_for_analysis'
    )
  ),
  constraint check_limiting_domain check (
    limiting_domain is null
    or limiting_domain in ('profile', 'price', 'fundamentals')
  )
);

-- ── 2. updated_at trigger ─────────────────────────────────────────────────────
-- Reuses update_updated_at_column() defined in 003_views_and_functions.sql.

drop trigger if exists update_company_analysis_readiness_updated_at
  on company_analysis_readiness;

create trigger update_company_analysis_readiness_updated_at
  before update on company_analysis_readiness
  for each row execute function update_updated_at_column();

-- ── 3. RLS — authenticated read only, no anon/public ─────────────────────────
--
-- The backend service role bypasses RLS and writes snapshot rows.
-- Authenticated dashboard users may SELECT.
-- No INSERT/UPDATE/DELETE is granted to authenticated.
-- pipeline_run_events is not touched and remains backend-only.

alter table company_analysis_readiness enable row level security;

drop policy if exists "authenticated read company analysis readiness"
  on company_analysis_readiness;

create policy "authenticated read company analysis readiness"
  on company_analysis_readiness
  for select to authenticated using (true);

revoke all    on company_analysis_readiness from anon;
revoke all    on company_analysis_readiness from public;
grant  select on company_analysis_readiness to authenticated;

-- ── 4. analysis_readiness_latest view ────────────────────────────────────────
-- security_invoker = true: RLS on company_analysis_readiness is evaluated for
-- the calling role.  Authenticated users can read; anon/public cannot because
-- they have no SELECT policy on the base table.

create or replace view analysis_readiness_latest
  with (security_invoker = true) as
select
  company_id,
  readiness_status,
  provider_mix,
  readiness_reason_codes,
  can_run_valuation,
  can_run_signal,
  limiting_domain,
  readiness_updated_at
from company_analysis_readiness;

revoke all    on analysis_readiness_latest from anon;
revoke select on analysis_readiness_latest from public;
grant  select on analysis_readiness_latest to authenticated;

-- ── 5. Recreate dashboard_watchlist_latest with readiness fields ───────────────
--
-- Follows the drop-and-recreate pattern from 005_watchlist_management.sql and
-- 009_price_eod_metadata_and_precedence.sql because CREATE OR REPLACE VIEW
-- cannot add columns to an existing view.
--
-- CASCADE is safe: no dependent objects exist in this schema beyond the view.
-- All existing columns are preserved in their original order; the readiness
-- fields are appended at the end to minimise disruption to callers.

drop view if exists dashboard_watchlist_latest cascade;

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
  -- Phase 10C.3: readiness classification fields (null when not yet classified)
  ar.readiness_status,
  ar.provider_mix,
  ar.readiness_reason_codes,
  ar.can_run_valuation,
  ar.can_run_signal
from companies c
join  watchlist_companies             wc on wc.company_id = c.id
join  watchlists                      wl on wl.id         = wc.watchlist_id
left join latest_price_eod            p  on p.company_id  = c.id
left join latest_ratios_factors       r  on r.company_id  = c.id
left join latest_qualitative_scores   q  on q.company_id  = c.id
left join latest_valuation_runs       v  on v.company_id  = c.id
left join latest_signal_runs          s  on s.company_id  = c.id
left join analysis_readiness_latest   ar on ar.company_id = c.id
where wc.active = true
order by c.id;

revoke all    on dashboard_watchlist_latest from anon;
revoke select on dashboard_watchlist_latest from public;
grant  select on dashboard_watchlist_latest to authenticated;
