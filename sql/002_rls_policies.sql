-- 002_rls_policies.sql
-- Basic RLS policies for Supabase. Adjust for your authentication model.

alter table app_users enable row level security;
alter table watchlists enable row level security;
alter table watchlist_companies enable row level security;
alter table companies enable row level security;
alter table price_eod enable row level security;
alter table fx_rates enable row level security;
alter table filings_index enable row level security;
alter table statements_norm enable row level security;
alter table ratios_factors enable row level security;
alter table qualitative_scores enable row level security;
alter table valuation_runs enable row level security;
alter table signal_runs enable row level security;
alter table alert_rules enable row level security;
alter table alert_history enable row level security;

-- Public read for core market data in private authenticated dashboard.
-- In production, replace with user-scoped policies if multiple users are supported.
--
-- All CREATE POLICY statements are preceded by DROP POLICY IF EXISTS so that
-- this file can be re-applied safely without "policy already exists" errors.

drop policy if exists "authenticated read companies" on companies;
create policy "authenticated read companies" on companies
  for select to authenticated using (true);

drop policy if exists "authenticated read prices" on price_eod;
create policy "authenticated read prices" on price_eod
  for select to authenticated using (true);

drop policy if exists "authenticated read fx" on fx_rates;
create policy "authenticated read fx" on fx_rates
  for select to authenticated using (true);

drop policy if exists "authenticated read filings" on filings_index;
create policy "authenticated read filings" on filings_index
  for select to authenticated using (true);

drop policy if exists "authenticated read statements" on statements_norm;
create policy "authenticated read statements" on statements_norm
  for select to authenticated using (true);

drop policy if exists "authenticated read ratios" on ratios_factors;
create policy "authenticated read ratios" on ratios_factors
  for select to authenticated using (true);

drop policy if exists "authenticated read qualitative" on qualitative_scores;
create policy "authenticated read qualitative" on qualitative_scores
  for select to authenticated using (true);

drop policy if exists "authenticated read valuations" on valuation_runs;
create policy "authenticated read valuations" on valuation_runs
  for select to authenticated using (true);

drop policy if exists "authenticated read signals" on signal_runs;
create policy "authenticated read signals" on signal_runs
  for select to authenticated using (true);

drop policy if exists "users read own profile" on app_users;
create policy "users read own profile" on app_users
  for select to authenticated
  using (email = auth.jwt() ->> 'email');

-- ── Helper function ───────────────────────────────────────────────────────────
-- Resolves app_users.id from the current JWT email with SECURITY DEFINER so
-- that RLS on app_users is not evaluated inside subqueries of other policies.
-- Without this, evaluating alert_history's policy causes "permission denied
-- for table app_users" because PostgreSQL re-evaluates RLS on the subquery's
-- table using the caller's role, which may not have the necessary chain of
-- privileges resolved yet.
create or replace function get_my_app_user_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select id from app_users where email = auth.jwt() ->> 'email' limit 1;
$$;

grant execute on function get_my_app_user_id() to authenticated;

-- ── User-scoped policies (use helper to avoid recursive RLS chain) ────────────

drop policy if exists "users read own watchlists" on watchlists;
create policy "users read own watchlists" on watchlists
  for select to authenticated
  using (user_id = get_my_app_user_id());

drop policy if exists "users read own watchlist companies" on watchlist_companies;
create policy "users read own watchlist companies" on watchlist_companies
  for select to authenticated
  using (
    watchlist_id in (
      select id from watchlists where user_id = get_my_app_user_id()
    )
  );

drop policy if exists "users read own alert rules" on alert_rules;
create policy "users read own alert rules" on alert_rules
  for select to authenticated
  using (user_id = get_my_app_user_id());

drop policy if exists "users read own alert history" on alert_history;
create policy "users read own alert history" on alert_history
  for select to authenticated
  using (
    alert_rule_id in (
      select id from alert_rules where user_id = get_my_app_user_id()
    )
  );

-- Backend service role bypasses RLS automatically in Supabase.
-- Use service role only in trusted backend/GitHub Actions contexts.

-- ── Explicit GRANT SELECT for authenticated role ──────────────────────────────
-- RLS policies filter *which rows* are visible, but PostgreSQL requires the
-- role to have base SELECT privilege on the table before RLS is even evaluated.
-- Supabase does not grant these automatically when RLS is enabled.
grant select on app_users to authenticated;
grant select on alert_rules to authenticated;
grant select on alert_history to authenticated;
grant select on watchlists to authenticated;
grant select on watchlist_companies to authenticated;

-- ── RLS for backend-only tables ───────────────────────────────────────────────
-- No authenticated-read policy: these tables are accessed only via service role.

alter table pipeline_runs enable row level security;
alter table pipeline_run_events enable row level security;
alter table provider_requests enable row level security;
alter table raw_provider_payloads enable row level security;
alter table statements_raw enable row level security;

-- ── RLS for supplementary market data (authenticated read) ────────────────────

alter table corporate_actions enable row level security;
alter table news_events enable row level security;

drop policy if exists "authenticated read corporate actions" on corporate_actions;
create policy "authenticated read corporate actions" on corporate_actions
  for select to authenticated using (true);

drop policy if exists "authenticated read news events" on news_events;
create policy "authenticated read news events" on news_events
  for select to authenticated using (true);
