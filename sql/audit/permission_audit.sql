-- permission_audit.sql
-- Diagnostic queries for auditing table and view privileges in the Supabase
-- public schema.  Run these in the Supabase SQL Editor (requires postgres or
-- service_role access).  They are read-only and do not modify any data.
-- ─────────────────────────────────────────────────────────────────────────────


-- ── 1. All table/view grants grouped by object and grantee ───────────────────
-- Shows the full privilege matrix.  After 011 is applied, anon should appear
-- in zero rows; public should appear in zero rows.

select
  table_name,
  grantee,
  string_agg(privilege_type, ', ' order by privilege_type) as privileges
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee not in ('postgres', 'supabase_admin', 'supabase_auth_admin',
                      'supabase_storage_admin', 'supabase_replication_admin',
                      'dashboard_user')
group by table_name, grantee
order by table_name, grantee;


-- ── 2. Column-level privileges (watchlist_add_requests) ───────────────────────
-- Confirms authenticated has only the column-scoped INSERT and UPDATE(status)
-- that were defined in 006 and re-applied in 011.

select
  table_name,
  column_name,
  grantee,
  privilege_type
from information_schema.role_column_grants
where table_schema = 'public'
  and grantee not in ('postgres', 'supabase_admin', 'supabase_auth_admin',
                      'supabase_storage_admin')
order by table_name, column_name, grantee;


-- ── 3. Unexpected anon or public grants (should return zero rows after 011) ────

select
  table_name,
  grantee,
  privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee in ('anon', 'public')
order by table_name, grantee, privilege_type;


-- ── 4. Authenticated write grants (INSERT/UPDATE/DELETE on full table) ─────────
-- Lists authenticated write privileges for review.  Intentional exceptions:
--   watchlist_companies                 UPDATE  (soft-remove / reactivate)
--   watchlist_add_requests column-level INSERT  (watchlist_id, requested_ticker, requested_exchange)
--   watchlist_add_requests column-level UPDATE  (status — cancellation only)
-- NOTE: column-level INSERT/UPDATE on watchlist_add_requests will NOT appear in
-- this query (they appear only in role_column_grants); see Query 2 for those.
-- Unexpected broad INSERT/UPDATE/DELETE on any other table should be investigated.

select
  table_name,
  grantee,
  privilege_type
from information_schema.role_table_grants
where table_schema   = 'public'
  and grantee        = 'authenticated'
  and privilege_type in ('INSERT', 'UPDATE', 'DELETE')
order by table_name, privilege_type;


-- ── 5. service_role INSERT gaps (tables where service_role lacks INSERT) ───────
-- Expected result: zero rows after 011 is applied.

select
  t.table_name
from information_schema.tables t
left join information_schema.role_table_grants g
       on g.table_schema  = t.table_schema
      and g.table_name    = t.table_name
      and g.grantee       = 'service_role'
      and g.privilege_type = 'INSERT'
where t.table_schema = 'public'
  and t.table_type   = 'BASE TABLE'
  and g.privilege_type is null
order by t.table_name;


-- ── 6. Authenticated REFERENCES / TRIGGER / TRUNCATE (should be gone after 011)
-- These typically come from Supabase default ALTER DEFAULT PRIVILEGES granting
-- ALL to authenticated.  After the explicit REVOKE ALL + re-grant in 011,
-- this query should return zero rows.

select
  table_name,
  grantee,
  privilege_type
from information_schema.role_table_grants
where table_schema   = 'public'
  and grantee        = 'authenticated'
  and privilege_type in ('REFERENCES', 'TRIGGER', 'TRUNCATE')
order by table_name, privilege_type;
