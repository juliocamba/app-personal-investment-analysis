-- 011_explicit_grants_and_rls_hardening.sql
-- Phase 11: Project-wide explicit Supabase grants and RLS hardening pass.
--
-- Context
-- ───────
-- Supabase announced that default public-schema grants (which previously gave
-- every role access to new tables automatically) are being removed for all
-- projects.  Migrations 001–010 relied on those defaults; this migration makes
-- every grant and revoke explicit so the application never depends on implicit
-- platform defaults.
--
-- Idempotent: safe to re-apply.  GRANT and REVOKE are idempotent in PostgreSQL.
-- Additive: no RLS policies, columns, or tables are changed or removed.
-- Apply after: 001–010 already applied.
--
-- ── ACCESS TIERS ──────────────────────────────────────────────────────────────
--   A. backend_only      → service_role ALL;  authenticated/anon: NONE
--   B. backend_rw_auth_r → service_role ALL;  authenticated: SELECT only
--   C. auth_scoped_write → service_role ALL;  authenticated: SELECT + scoped write
--   D. views             → service_role SELECT; authenticated: SELECT; anon: NONE
--
-- ── ROLES IN SCOPE ────────────────────────────────────────────────────────────
--   authenticated  Frontend Supabase-JS sessions (dashboard read + scoped write)
--   service_role   Backend pipeline + GitHub Actions (all write operations)
--   anon           Public / unauthenticated — NO access to any table or view
--   public         PostgreSQL pseudo-role — stripped from all objects
-- ─────────────────────────────────────────────────────────────────────────────


-- ═══════════════════════════════════════════════════════════════════════════════
-- A. BACKEND-ONLY TABLES
-- ═══════════════════════════════════════════════════════════════════════════════
-- These tables are read and written exclusively by service_role.
-- No authenticated SELECT policy exists on them (RLS blocks all rows).
-- This section also strips any lingering Supabase default public-schema grants.

revoke all on pipeline_runs         from public, anon, authenticated;
revoke all on pipeline_run_events   from public, anon, authenticated;
revoke all on provider_requests     from public, anon, authenticated;
revoke all on raw_provider_payloads from public, anon, authenticated;
revoke all on statements_raw        from public, anon, authenticated;

grant select, insert, update, delete on pipeline_runs         to service_role;
grant select, insert, update, delete on pipeline_run_events   to service_role;
grant select, insert, update, delete on provider_requests     to service_role;
grant select, insert, update, delete on raw_provider_payloads to service_role;
grant select, insert, update, delete on statements_raw        to service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- B. BACKEND-WRITABLE, AUTHENTICATED READ-ONLY TABLES
-- ═══════════════════════════════════════════════════════════════════════════════
-- The backend pipeline is the sole writer.  Dashboard and frontend read via
-- existing RLS policies (002, 010).  Authenticated gets SELECT only.
-- Fixes: 002 was missing explicit GRANT SELECT for these 11 market-data tables.
-- Fixes: company_analysis_readiness had unexpected REFERENCES/TRIGGER/TRUNCATE.

revoke all on companies                  from public, anon, authenticated;
revoke all on price_eod                  from public, anon, authenticated;
revoke all on fx_rates                   from public, anon, authenticated;
revoke all on filings_index              from public, anon, authenticated;
revoke all on statements_norm            from public, anon, authenticated;
revoke all on ratios_factors             from public, anon, authenticated;
revoke all on qualitative_scores         from public, anon, authenticated;
revoke all on valuation_runs             from public, anon, authenticated;
revoke all on signal_runs                from public, anon, authenticated;
revoke all on news_events                from public, anon, authenticated;
revoke all on corporate_actions          from public, anon, authenticated;
revoke all on company_analysis_readiness from public, anon, authenticated;

grant select on companies                  to authenticated;
grant select on price_eod                  to authenticated;
grant select on fx_rates                   to authenticated;
grant select on filings_index              to authenticated;
grant select on statements_norm            to authenticated;
grant select on ratios_factors             to authenticated;
grant select on qualitative_scores         to authenticated;
grant select on valuation_runs             to authenticated;
grant select on signal_runs                to authenticated;
grant select on news_events                to authenticated;
grant select on corporate_actions          to authenticated;
grant select on company_analysis_readiness to authenticated;

grant select, insert, update, delete on companies                  to service_role;
grant select, insert, update, delete on price_eod                  to service_role;
grant select, insert, update, delete on fx_rates                   to service_role;
grant select, insert, update, delete on filings_index              to service_role;
grant select, insert, update, delete on statements_norm            to service_role;
grant select, insert, update, delete on ratios_factors             to service_role;
grant select, insert, update, delete on qualitative_scores         to service_role;
grant select, insert, update, delete on valuation_runs             to service_role;
grant select, insert, update, delete on signal_runs                to service_role;
grant select, insert, update, delete on news_events                to service_role;
grant select, insert, update, delete on corporate_actions          to service_role;
grant select, insert, update, delete on company_analysis_readiness to service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- C. USER-WRITABLE TABLES (authenticated with scoped RLS write policies)
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── app_users ─────────────────────────────────────────────────────────────────
-- Users read only their own row via the "users read own profile" RLS policy.
-- Backend manages all insert/update/delete operations.

revoke all on app_users from public, anon, authenticated;
grant select                          on app_users to authenticated;
grant select, insert, update, delete  on app_users to service_role;

-- ── watchlists ────────────────────────────────────────────────────────────────
-- Users read only their own watchlists via RLS.  Backend creates/manages rows.

revoke all on watchlists from public, anon, authenticated;
grant select                          on watchlists to authenticated;
grant select, insert, update, delete  on watchlists to service_role;

-- ── watchlist_companies ───────────────────────────────────────────────────────
-- Authenticated may SELECT and UPDATE (soft-remove / reactivate, via RLS).
-- INSERT and DELETE are backend-only; the add-request flow controls membership.
-- Revoke all first to strip Supabase default grants, then re-grant precisely.

revoke all on watchlist_companies from public, anon, authenticated;
grant select, update                  on watchlist_companies to authenticated;
grant select, insert, update, delete  on watchlist_companies to service_role;

-- ── watchlist_add_requests ────────────────────────────────────────────────────
-- Column-scoped grants from 006 are re-applied idempotently after a full revoke
-- so that any unexpected Supabase default grants are stripped.

revoke all on watchlist_add_requests from public, anon, authenticated;
grant select                          on watchlist_add_requests to authenticated;
grant insert(watchlist_id, requested_ticker, requested_exchange)
                                      on watchlist_add_requests to authenticated;
grant update(status)                  on watchlist_add_requests to authenticated;
grant select, insert, update, delete  on watchlist_add_requests to service_role;

-- ── alert_rules ───────────────────────────────────────────────────────────────
-- Users read only their own rules via RLS.  Backend manages all writes.

revoke all on alert_rules from public, anon, authenticated;
grant select                          on alert_rules to authenticated;
grant select, insert, update, delete  on alert_rules to service_role;

-- ── alert_history ─────────────────────────────────────────────────────────────
-- Users read only their own alert history via RLS.  Backend manages all writes.

revoke all on alert_history from public, anon, authenticated;
grant select                          on alert_history to authenticated;
grant select, insert, update, delete  on alert_history to service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- D. INTERMEDIATE VIEWS
-- ═══════════════════════════════════════════════════════════════════════════════
-- These views are used as building blocks for dashboard_watchlist_latest.
-- security_invoker = true is NOT set on these views (003 / 009 did not set it);
-- access is gated by the base-table grants and the dashboard view's invoker
-- setting.  authenticated needs SELECT so dashboard_watchlist_latest (security
-- invoker) can resolve them when the calling role is authenticated.

revoke all on latest_price_eod          from public, anon;
revoke all on latest_ratios_factors     from public, anon;
revoke all on latest_valuation_runs     from public, anon;
revoke all on latest_qualitative_scores from public, anon;
revoke all on latest_signal_runs        from public, anon;

grant select on latest_price_eod          to authenticated, service_role;
grant select on latest_ratios_factors     to authenticated, service_role;
grant select on latest_valuation_runs     to authenticated, service_role;
grant select on latest_qualitative_scores to authenticated, service_role;
grant select on latest_signal_runs        to authenticated, service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- E. DASHBOARD-FACING VIEWS  (security_invoker = true on all three)
-- ═══════════════════════════════════════════════════════════════════════════════
-- authenticated access was already granted in earlier migrations; this section
-- adds service_role SELECT and re-applies anon/public revoke idempotently.

revoke all on dashboard_watchlist_latest   from public, anon;
revoke all on dashboard_watchlist_inactive from public, anon;
revoke all on analysis_readiness_latest    from public, anon;

grant select on dashboard_watchlist_latest   to authenticated, service_role;
grant select on dashboard_watchlist_inactive to authenticated, service_role;
grant select on analysis_readiness_latest    to authenticated, service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- F. FUNCTIONS
-- ═══════════════════════════════════════════════════════════════════════════════

-- get_my_app_user_id(): security-definer helper used inside RLS policies.
-- Already granted to authenticated in 002; add service_role idempotently.
grant execute on function get_my_app_user_id() to authenticated, service_role;

-- update_updated_at_column() and normalize_watchlist_add_request() are trigger
-- functions invoked by the database engine through the trigger mechanism, not
-- by application roles directly.  They do not need explicit EXECUTE grants.


-- ═══════════════════════════════════════════════════════════════════════════════
-- G. PERMISSION-MATRIX VALIDATION FUNCTION
-- ═══════════════════════════════════════════════════════════════════════════════
-- SECURITY DEFINER helper used by scripts/validate_supabase_permissions.py.
-- Returns a JSONB array of check results so the Python script can report pass/
-- fail without needing a direct Postgres connection.

create or replace function public.check_permission_matrix()
returns jsonb
language plpgsql
security definer
set search_path = public, information_schema
as $$
declare
  result      jsonb   := '[]'::jsonb;
  v_count     bigint;
  v_expected  bigint;
begin
  -- ── Check 1: backend-only tables — no authenticated access ──────────────────
  select count(*) into v_count
  from information_schema.role_table_grants
  where table_schema   = 'public'
    and grantee        = 'authenticated'
    and table_name in (
      'pipeline_runs', 'pipeline_run_events', 'provider_requests',
      'raw_provider_payloads', 'statements_raw'
    );
  result := result || jsonb_build_array(jsonb_build_object(
    'check',   'backend_only_table_isolation',
    'passed',  v_count = 0,
    'detail',  case when v_count = 0
               then 'ok — no authenticated grants on backend-only tables'
               else v_count::text || ' unexpected authenticated grant(s) on backend-only table(s)'
               end
  ));

  -- ── Check 2: service_role INSERT on all write tables ─────────────────────────
  v_expected := 23;
  select count(*) into v_count
  from information_schema.role_table_grants
  where table_schema  = 'public'
    and grantee       = 'service_role'
    and privilege_type = 'INSERT'
    and table_name in (
      -- backend-only (5)
      'pipeline_runs', 'pipeline_run_events', 'provider_requests',
      'raw_provider_payloads', 'statements_raw',
      -- backend-rw auth-r (12)
      'companies', 'price_eod', 'fx_rates', 'filings_index', 'statements_norm',
      'ratios_factors', 'qualitative_scores', 'valuation_runs', 'signal_runs',
      'news_events', 'corporate_actions', 'company_analysis_readiness',
      -- user-writable (6)
      'app_users', 'watchlists', 'watchlist_companies', 'watchlist_add_requests',
      'alert_rules', 'alert_history'
    );
  result := result || jsonb_build_array(jsonb_build_object(
    'check',   'service_role_write_access',
    'passed',  v_count = v_expected,
    'detail',  'service_role has INSERT on ' || v_count::text || '/' || v_expected::text || ' write tables'
  ));

  -- ── Check 3: authenticated SELECT on market-data tables ──────────────────────
  v_expected := 12;
  select count(*) into v_count
  from information_schema.role_table_grants
  where table_schema   = 'public'
    and grantee        = 'authenticated'
    and privilege_type = 'SELECT'
    and table_name in (
      'companies', 'price_eod', 'fx_rates', 'filings_index', 'statements_norm',
      'ratios_factors', 'qualitative_scores', 'valuation_runs', 'signal_runs',
      'news_events', 'corporate_actions', 'company_analysis_readiness'
    );
  result := result || jsonb_build_array(jsonb_build_object(
    'check',   'market_data_auth_select',
    'passed',  v_count = v_expected,
    'detail',  'authenticated SELECT on ' || v_count::text || '/' || v_expected::text || ' market-data tables'
  ));

  -- ── Check 4: company_analysis_readiness — no authenticated writes ────────────
  select count(*) into v_count
  from information_schema.role_table_grants
  where table_schema   = 'public'
    and grantee        = 'authenticated'
    and privilege_type in ('INSERT', 'UPDATE', 'DELETE')
    and table_name     = 'company_analysis_readiness';
  result := result || jsonb_build_array(jsonb_build_object(
    'check',   'readiness_table_write_blocked',
    'passed',  v_count = 0,
    'detail',  case when v_count = 0
               then 'ok — no authenticated write grants on company_analysis_readiness'
               else v_count::text || ' unexpected authenticated write grant(s) on company_analysis_readiness'
               end
  ));

  -- ── Check 5: no anon grants on any public table or view ──────────────────────
  select count(*) into v_count
  from information_schema.role_table_grants
  where table_schema = 'public'
    and grantee      = 'anon';
  result := result || jsonb_build_array(jsonb_build_object(
    'check',   'no_anon_grants',
    'passed',  v_count = 0,
    'detail',  case when v_count = 0
               then 'ok — no anon grants'
               else v_count::text || ' unexpected anon grant(s)'
               end
  ));

  -- ── Check 6: authenticated SELECT on all 8 dashboard views ───────────────────
  v_expected := 8;
  select count(*) into v_count
  from information_schema.role_table_grants
  where table_schema   = 'public'
    and grantee        = 'authenticated'
    and privilege_type = 'SELECT'
    and table_name in (
      'dashboard_watchlist_latest', 'dashboard_watchlist_inactive',
      'analysis_readiness_latest',
      'latest_price_eod', 'latest_ratios_factors', 'latest_valuation_runs',
      'latest_qualitative_scores', 'latest_signal_runs'
    );
  result := result || jsonb_build_array(jsonb_build_object(
    'check',   'dashboard_view_auth_select',
    'passed',  v_count = v_expected,
    'detail',  'authenticated SELECT on ' || v_count::text || '/' || v_expected::text || ' dashboard views'
  ));

  return result;
end;
$$;

-- Only backend tooling should call this validation helper.
revoke all    on function public.check_permission_matrix() from public, anon, authenticated;
grant  execute on function public.check_permission_matrix() to service_role;
