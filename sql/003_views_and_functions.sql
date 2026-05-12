-- 003_views_and_functions.sql
-- Dashboard views and helper functions.

create or replace view latest_price_eod as
select distinct on (company_id)
  company_id,
  price_date,
  close,
  adjusted_close,
  volume,
  market_cap,
  shares_outstanding,
  currency,
  provider
from price_eod
order by company_id, price_date desc;

create or replace view latest_ratios_factors as
select distinct on (company_id)
  *
from ratios_factors
order by company_id, factor_date desc;

create or replace view latest_valuation_runs as
select distinct on (company_id)
  *
from valuation_runs
order by company_id, valuation_date desc, created_at desc;

create or replace view latest_qualitative_scores as
select distinct on (company_id)
  *
from qualitative_scores
order by company_id, score_date desc, created_at desc;

create or replace view latest_signal_runs as
select distinct on (company_id)
  *
from signal_runs
order by company_id, signal_date desc, created_at desc;

-- ── dashboard_watchlist_latest ────────────────────────────────────────────────
-- SECURITY INVOKER (requires PostgreSQL 15+): Supabase/Postgres evaluates the
-- RLS policies on the underlying tables for the *calling role*, not the view
-- owner.  The `anon` role has no SELECT policy on any base table, so
-- unauthenticated PostgREST requests cannot read this view even when they
-- present the public anon key.
--
-- MVP visibility assumption: all authenticated Supabase Auth users see ALL
-- active companies.  This is intentional for a private single-operator
-- deployment.  If per-user watchlist isolation is ever needed, add a
-- user-scoped WHERE clause and update the RLS policies accordingly.
create or replace view dashboard_watchlist_latest with (security_invoker = true) as
select
  c.id as company_id,
  c.ticker,
  c.name,
  c.exchange,
  c.country,
  c.currency,
  c.sector,
  c.industry,
  p.price_date,
  p.close as current_price,
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
  s.freshness_flag
from companies c
left join latest_price_eod p on p.company_id = c.id
left join latest_ratios_factors r on r.company_id = c.id
left join latest_qualitative_scores q on q.company_id = c.id
left join latest_valuation_runs v on v.company_id = c.id
left join latest_signal_runs s on s.company_id = c.id
where c.active = true;

-- Grant SELECT on intermediate views to authenticated so that
-- dashboard_watchlist_latest (security_invoker=true) can resolve them
-- when called by the authenticated role.
grant select on latest_price_eod to authenticated;
grant select on latest_ratios_factors to authenticated;
grant select on latest_valuation_runs to authenticated;
grant select on latest_qualitative_scores to authenticated;
grant select on latest_signal_runs to authenticated;

-- Explicitly deny direct access to the anon role and PUBLIC (which anon
-- inherits from).  Only the authenticated role may query this view.
-- The underlying base-table RLS policies provide a second layer of defence.
revoke all on dashboard_watchlist_latest from anon;
revoke select on dashboard_watchlist_latest from public;
grant select on dashboard_watchlist_latest to authenticated;

create or replace function update_updated_at_column()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists update_companies_updated_at on companies;
create trigger update_companies_updated_at
before update on companies
for each row execute function update_updated_at_column();

drop trigger if exists update_watchlists_updated_at on watchlists;
create trigger update_watchlists_updated_at
before update on watchlists
for each row execute function update_updated_at_column();

drop trigger if exists update_alert_rules_updated_at on alert_rules;
create trigger update_alert_rules_updated_at
before update on alert_rules
for each row execute function update_updated_at_column();
