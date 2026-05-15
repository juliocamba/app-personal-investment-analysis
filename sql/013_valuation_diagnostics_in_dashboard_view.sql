-- 013_valuation_diagnostics_in_dashboard_view.sql
-- Phase 11A.5: Surface valuation diagnostic fields in dashboard_watchlist_latest.
--
-- Adds four new columns extracted from valuation_runs.assumptions->diagnostics:
--
--   mos_basis             text     – value used for MoS calculation ("iv_p10").
--   scenario_count        integer  – number of DCF scenarios that contributed to
--                                    the valuation distribution (0–3).
--   uncertainty_category  text     – "low" | "moderate" | "high" | "extreme";
--                                    derived from uncertainty_width in the engine.
--   distribution_collapsed boolean – true when all distribution entries share the
--                                    same value, signalling limited diversity.
--
-- These fields are read-only metadata already computed and stored in
-- valuation_runs.assumptions["diagnostics"] by PR 11A.2.  No valuation math,
-- signal logic, or scoring is changed.
--
-- Field source paths (JSONB):
--   mos_basis            → assumptions->'diagnostics'->>'mos_basis'
--   scenario_count       → (assumptions->'diagnostics'->>'scenario_count')::int
--   uncertainty_category → assumptions->'diagnostics'->>'uncertainty_category'
--   distribution_collapsed →
--       (assumptions->'diagnostics'->'warnings') @> '["distribution_collapsed"]'
--
-- Security / access model (unchanged from 010–012):
--   security_invoker = true  →  Supabase evaluates RLS for the calling role.
--   authenticated            →  SELECT only.
--   service_role             →  SELECT (used by backend pipeline queries).
--   anon / public            →  fully revoked.
--
-- Pattern: drop-then-recreate with CASCADE (no dependent objects exist).
-- All existing columns are preserved in their original order; the four new
-- diagnostic fields are appended at the end to minimise disruption to callers.
--
-- Idempotent: safe to re-apply.
-- Apply after: 001–012 already applied.

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
  ar.can_run_signal,
  -- Phase 11A.5: valuation diagnostic fields (null when no valuation run exists)
  v.assumptions->'diagnostics'->>'mos_basis'
                                        as mos_basis,
  (v.assumptions->'diagnostics'->>'scenario_count')::int
                                        as scenario_count,
  v.assumptions->'diagnostics'->>'uncertainty_category'
                                        as uncertainty_category,
  (v.assumptions->'diagnostics'->'warnings') @> '["distribution_collapsed"]'::jsonb
                                        as distribution_collapsed
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

-- Full revoke-then-precise-grant pattern (matches migration 012 hardening).
-- authenticated: SELECT only (dashboard read).
-- service_role:  SELECT (backend pipeline queries against the view).
-- anon/public:   no access at all.
revoke all    on dashboard_watchlist_latest from public, anon, authenticated;
grant  select on dashboard_watchlist_latest to authenticated, service_role;
