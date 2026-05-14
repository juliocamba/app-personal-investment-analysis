-- 009_price_eod_metadata_and_precedence.sql
-- Phase 10B: add provenance columns to price_eod and rebuild latest_price_eod
-- with deterministic provider precedence.
--
-- Idempotent: safe to run multiple times.

-- ── 1. Add raw_payload_id column ─────────────────────────────────────────────
alter table price_eod
  add column if not exists raw_payload_id uuid
    references raw_provider_payloads(id) on delete set null;

-- ── 2. Add metadata column ───────────────────────────────────────────────────
alter table price_eod
  add column if not exists metadata jsonb not null default '{}'::jsonb;

-- ── 3. Recreate latest_price_eod with provider precedence ───────────────────
-- "create or replace" cannot reorder existing view columns; drop first.
-- Grants are re-applied in step 4.
--
-- Precedence (lower = preferred):
--   0 = fmp          (primary source, most reliable)
--   1 = twelve_data  (Phase 10B fallback)
--   9 = all others
--
-- Within the same provider, newest created_at wins (handles re-ingestion).

-- CASCADE also drops dashboard_watchlist_latest which depends on this view.
-- It is recreated in step 4 below.
drop view if exists latest_price_eod cascade;

create view latest_price_eod
  with (security_invoker = true)
as
select distinct on (company_id)
  company_id,
  price_date,
  open,
  high,
  low,
  close,
  adjusted_close,
  volume,
  market_cap,
  shares_outstanding,
  currency,
  provider,
  raw_payload_id,
  metadata
from price_eod
order by
  company_id,
  price_date desc,
  case provider
    when 'fmp'         then 0
    when 'twelve_data' then 1
    else                    9
  end,
  created_at desc;

-- ── 4. Restore grants on latest_price_eod ───────────────────────────────────
grant select on latest_price_eod to authenticated;

-- ── 5. Recreate dashboard_watchlist_latest (dropped by cascade above) ────────
drop view if exists dashboard_watchlist_latest cascade;

create view dashboard_watchlist_latest with (security_invoker = true) as
select distinct on (c.id)
  wc.id                           as watchlist_membership_id,
  c.id                            as company_id,
  c.ticker,
  c.name,
  c.exchange,
  c.country,
  c.currency,
  c.sector,
  c.industry,
  p.price_date,
  p.close                         as current_price,
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
join watchlist_companies wc on wc.company_id = c.id
join watchlists          wl on wl.id = wc.watchlist_id
left join latest_price_eod          p on p.company_id = c.id
left join latest_ratios_factors     r on r.company_id = c.id
left join latest_qualitative_scores q on q.company_id = c.id
left join latest_valuation_runs     v on v.company_id = c.id
left join latest_signal_runs        s on s.company_id = c.id
where wc.active = true
order by c.id;

revoke all    on dashboard_watchlist_latest from anon;
revoke select on dashboard_watchlist_latest from public;
grant  select on dashboard_watchlist_latest to authenticated;
