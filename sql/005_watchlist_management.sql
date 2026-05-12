-- 005_watchlist_management.sql
-- Phase 9A: Watchlist Active Membership
--
-- Migrates the dashboard view and daily pipeline from companies.active to
-- watchlist_companies.active as the source of truth for the active watchlist.
--
-- Idempotent: safe to re-run against an already-migrated database.
-- Requires: 001, 002, 003, 004 already applied.
-- Requires: get_my_app_user_id() function (from 002_rls_policies.sql).

-- ── 1. Add new columns to watchlist_companies ─────────────────────────────────
--   removed_at : set when a company is soft-removed; cleared on reactivation.
--   updated_at : maintained by trigger, mirrors companies.updated_at pattern.

alter table watchlist_companies
  add column if not exists removed_at  timestamptz,
  add column if not exists updated_at  timestamptz not null default now();

-- ── 2. updated_at trigger for watchlist_companies ─────────────────────────────
-- Reuses the existing update_updated_at_column() trigger function from 003.

drop trigger if exists update_watchlist_companies_updated_at on watchlist_companies;
create trigger update_watchlist_companies_updated_at
  before update on watchlist_companies
  for each row execute function update_updated_at_column();

-- ── 3. Replace dashboard_watchlist_latest ────────────────────────────────────
-- Old definition:  WHERE c.active = true  (companies.active flag)
-- New definition:  JOIN watchlist_companies wc ON wc.active = true
--
-- Key changes:
--   • Exposes wc.id as watchlist_membership_id so the frontend can reference
--     the specific watchlist_companies row for soft-remove / reactivate.
--   • Joins through watchlists → watchlist_companies to determine membership.
--   • DISTINCT ON (c.id) prevents duplicates when a company appears in
--     multiple watchlists (single-operator MVP: never happens, but defensive).
--   • security_invoker = true retained: RLS is evaluated as the calling role.
--
-- DROP first because CREATE OR REPLACE VIEW cannot rename/reorder columns.
-- CASCADE drops any dependent objects (none exist in this schema).

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
left join latest_price_eod        p on p.company_id = c.id
left join latest_ratios_factors   r on r.company_id = c.id
left join latest_qualitative_scores q on q.company_id = c.id
left join latest_valuation_runs   v on v.company_id = c.id
left join latest_signal_runs      s on s.company_id = c.id
where wc.active = true
order by c.id;

revoke all   on dashboard_watchlist_latest from anon;
revoke select on dashboard_watchlist_latest from public;
grant  select on dashboard_watchlist_latest to authenticated;

-- ── 4. New view: dashboard_watchlist_inactive ─────────────────────────────────
-- Exposes soft-removed memberships so the frontend can offer reactivation.
-- Shows only companies with active = false in at least one watchlist.
--
-- DROP first for consistency (in case this migration is re-run after a partial
-- apply or if the view already exists from a previous attempt).

drop view if exists dashboard_watchlist_inactive cascade;

create view dashboard_watchlist_inactive with (security_invoker = true) as
select
  wc.id          as watchlist_membership_id,
  c.id           as company_id,
  c.ticker,
  c.name,
  c.exchange,
  c.country,
  c.currency,
  c.sector,
  wc.removed_at
from companies c
join watchlist_companies wc on wc.company_id = c.id
join watchlists          wl on wl.id = wc.watchlist_id
where wc.active = false
order by wc.removed_at desc nulls last;

revoke all    on dashboard_watchlist_inactive from anon;
revoke select on dashboard_watchlist_inactive from public;
grant  select on dashboard_watchlist_inactive to authenticated;

-- ── 5. Privileges and RLS write policies for watchlist_companies ─────────────
--
-- Hardened privilege model (matches verified Supabase state post Phase 9A):
--   authenticated : SELECT (from 002_rls_policies.sql) + UPDATE (added here)
--   anon          : no direct privileges
--   public        : no direct privileges
--   service_role  : admin bypass (Supabase built-in, not controlled here)
--
-- No INSERT privilege is granted: new memberships are added only by the
-- backend service role (pipeline / admin SQL).  Phase 9B will revisit.
-- No DELETE privilege is ever granted: all removal is a soft update.

revoke insert, update, delete, truncate, references, trigger
    on watchlist_companies from public, anon, authenticated;

-- Re-grant only what authenticated users legitimately need:
--   SELECT : already exists from 002_rls_policies.sql; re-grant is idempotent.
--   UPDATE : required for soft-remove (active=false) and reactivate (active=true).
grant select, update on watchlist_companies to authenticated;

-- RLS UPDATE policy: scoped to own watchlist rows only.
-- USING    → which existing rows may this user update?
-- WITH CHECK → may the updated row still be owned by this user?
-- Both predicates use the SECURITY DEFINER helper to avoid recursive RLS.

drop policy if exists "users update own watchlist companies" on watchlist_companies;
create policy "users update own watchlist companies" on watchlist_companies
  for update to authenticated
  using (
    watchlist_id in (select id from watchlists where user_id = get_my_app_user_id())
  )
  with check (
    watchlist_id in (select id from watchlists where user_id = get_my_app_user_id())
  );

-- No INSERT policy: Phase 9A does not expose new-membership creation.
-- No DELETE policy: removal is always a soft update (active=false).

-- Ensure any leftover INSERT policy from an earlier draft is removed.
drop policy if exists "users insert own watchlist companies" on watchlist_companies;
