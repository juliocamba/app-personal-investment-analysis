-- rls_policy_audit.sql
-- Diagnostic queries for auditing Row Level Security state and policies.
-- Run in Supabase SQL Editor (requires postgres or service_role access).
-- ─────────────────────────────────────────────────────────────────────────────


-- ── 1. RLS enabled/disabled per table ────────────────────────────────────────
-- All tables in the investment analysis schema should have RLS enabled.
-- Tables with rowsecurity = false are accessible to all roles without a policy
-- filter (dangerous if the table has sensitive data).

select
  tablename,
  rowsecurity       as rls_enabled,
  forcerowsecurity  as rls_forced
from pg_tables
where schemaname = 'public'
order by tablename;


-- ── 2. All RLS policies ───────────────────────────────────────────────────────

select
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname = 'public'
order by tablename, policyname;


-- ── 3. Tables with RLS enabled but zero policies ──────────────────────────────
-- These tables block ALL row access via PostgREST (service_role bypasses RLS,
-- so the backend is unaffected).  Expected for backend-only tables:
-- pipeline_runs, pipeline_run_events, provider_requests, raw_provider_payloads,
-- statements_raw.  Any other table appearing here warrants investigation.

select
  pt.tablename as table_with_rls_but_no_policies
from pg_tables pt
left join pg_policies pp
       on pp.tablename  = pt.tablename
      and pp.schemaname = pt.schemaname
where pt.schemaname    = 'public'
  and pt.rowsecurity   = true
  and pp.policyname    is null
order by pt.tablename;


-- ── 4. Tables with RLS disabled (all rows visible to any grantee) ─────────────
-- Expected result: zero rows.  Any table here is visible to any role that has
-- a GRANT without RLS filtering.

select
  tablename as table_without_rls
from pg_tables
where schemaname    = 'public'
  and rowsecurity   = false
order by tablename;


-- ── 5. Authenticated INSERT/UPDATE/DELETE policies ────────────────────────────
-- Expected: watchlist_companies (UPDATE via 005), watchlist_add_requests
-- (INSERT and UPDATE via 006), and alert_rules / alert_history are managed
-- entirely by the backend.  Any unexpected write policy here warrants review.

select
  tablename,
  policyname,
  cmd,
  roles,
  with_check
from pg_policies
where schemaname = 'public'
  and cmd        in ('INSERT', 'UPDATE', 'DELETE', 'ALL')
  and 'authenticated' = any(roles)
order by tablename, policyname;
