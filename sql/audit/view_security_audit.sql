-- view_security_audit.sql
-- Diagnostic queries for auditing view security settings.
-- Run in Supabase SQL Editor (requires postgres or service_role access).
-- ─────────────────────────────────────────────────────────────────────────────


-- ── 1. All views with their reloptions (security_invoker / security_definer) ──
-- Dashboard views should have reloptions containing 'security_invoker=true'.
-- Intermediate views (latest_*) do not set security_invoker; they rely on
-- base-table grants for access control.

select
  c.relname     as view_name,
  c.reloptions
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname  = 'public'
  and c.relkind  = 'v'
order by c.relname;


-- ── 2. Views with security_invoker = true (expected: dashboard views) ─────────
-- Expected: dashboard_watchlist_latest, dashboard_watchlist_inactive,
--           analysis_readiness_latest.
-- latest_price_eod and other intermediate views should NOT appear here.

select
  c.relname as view_name
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname       = 'public'
  and c.relkind       = 'v'
  and 'security_invoker=true' = any(c.reloptions)
order by c.relname;


-- ── 3. View privileges grouped by view and grantee ───────────────────────────
-- After 011: all views should have authenticated SELECT and service_role SELECT.
-- No view should grant to anon or public.

select
  rtg.table_name  as view_name,
  rtg.grantee,
  string_agg(rtg.privilege_type, ', ' order by rtg.privilege_type) as privileges
from information_schema.role_table_grants rtg
join pg_views v
  on v.viewname    = rtg.table_name
 and v.schemaname  = rtg.table_schema
where rtg.table_schema = 'public'
  and rtg.grantee not in ('postgres', 'supabase_admin', 'supabase_auth_admin',
                          'supabase_storage_admin')
group by rtg.table_name, rtg.grantee
order by rtg.table_name, rtg.grantee;


-- ── 4. Views with anon or public grants (should return zero rows after 011) ───

select
  rtg.table_name  as view_name,
  rtg.grantee,
  rtg.privilege_type
from information_schema.role_table_grants rtg
join pg_views v
  on v.viewname   = rtg.table_name
 and v.schemaname = rtg.table_schema
where rtg.table_schema = 'public'
  and rtg.grantee in ('anon', 'public')
order by rtg.table_name, rtg.grantee;


-- ── 5. Views missing service_role SELECT (should return zero rows after 011) ──

select
  v.viewname as view_missing_service_role_select
from pg_views v
left join information_schema.role_table_grants g
       on g.table_name    = v.viewname
      and g.table_schema  = v.schemaname
      and g.grantee       = 'service_role'
      and g.privilege_type = 'SELECT'
where v.schemaname       = 'public'
  and g.privilege_type   is null
order by v.viewname;


-- ── 6. Function execute privileges on get_my_app_user_id (after 012) ─────────
-- Expected rows:
--   authenticated | EXECUTE
--   service_role  | EXECUTE
--   postgres      | EXECUTE  (Supabase internal superuser — acceptable)
-- Must NOT appear:
--   PUBLIC        | EXECUTE
--   anon          | EXECUTE

select
  r.routine_schema,
  r.routine_name,
  rp.grantee,
  rp.privilege_type
from information_schema.routines r
join information_schema.routine_privileges rp
  on rp.specific_schema = r.specific_schema
 and rp.specific_name   = r.specific_name
where r.routine_schema = 'public'
  and r.routine_name   = 'get_my_app_user_id'
order by rp.grantee;


-- ── 7. Unexpected PUBLIC or anon EXECUTE on any public-schema function ────────
-- Expected: zero rows after 012 is applied.

select
  r.routine_name,
  rp.grantee,
  rp.privilege_type
from information_schema.routines r
join information_schema.routine_privileges rp
  on rp.specific_schema = r.specific_schema
 and rp.specific_name   = r.specific_name
where r.routine_schema = 'public'
  and rp.grantee       in ('PUBLIC', 'anon')
order by r.routine_name, rp.grantee;


-- ── 8. Effective privilege check — authenticated on critical objects ───────────
-- Uses has_table_privilege() to confirm the runtime privilege state, not just
-- the grant catalogue.  Run in Supabase SQL Editor as postgres / service_role.
-- Expected:
--   company_analysis_readiness  authenticated INSERT → false
--   company_analysis_readiness  authenticated SELECT → true
--   dashboard_watchlist_latest  authenticated SELECT → true
--   analysis_readiness_latest   authenticated SELECT → true
--   pipeline_run_events         authenticated SELECT → false

select
  obj,
  privilege,
  has_table_privilege('authenticated', obj, privilege) as granted
from (values
  ('company_analysis_readiness', 'INSERT'),
  ('company_analysis_readiness', 'SELECT'),
  ('dashboard_watchlist_latest', 'SELECT'),
  ('dashboard_watchlist_inactive', 'SELECT'),
  ('analysis_readiness_latest',  'SELECT'),
  ('pipeline_run_events',        'SELECT'),
  ('raw_provider_payloads',      'SELECT')
) as t(obj, privilege)
order by obj, privilege;
