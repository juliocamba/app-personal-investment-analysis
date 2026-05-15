-- 012_function_execute_and_effective_privilege_hardening.sql
-- Follow-up to 011: closes two remaining gaps identified during post-apply
-- manual validation.
--
-- Gap 1 – PUBLIC EXECUTE on get_my_app_user_id()
--   PostgreSQL grants EXECUTE on every new function to the PUBLIC pseudo-role
--   by default.  Migration 011 added explicit EXECUTE grants to authenticated
--   and service_role but did not strip the pre-existing PUBLIC grant.
--   Post-apply validation showed:
--
--     grantee       | privilege_type
--     PUBLIC        | EXECUTE   ← not revoked by 011 — fixed here
--     authenticated | EXECUTE   ← correct (from 002 + 011)
--     postgres      | EXECUTE   ← Supabase internal superuser, not touched
--     service_role  | EXECUTE   ← correct (from 011)
--
-- Gap 2 – Intermediate and dashboard views: authenticated not fully stripped
--   Migration 011 revoked anon/public from all views but did not revoke the
--   existing authenticated grants before re-granting SELECT.  If Supabase's
--   ALTER DEFAULT PRIVILEGES previously gave authenticated
--   REFERENCES/TRIGGER/TRUNCATE on views (the same mechanism that caused the
--   table issue fixed in 011), those extra privileges would have survived.
--   This migration performs a full REVOKE from authenticated on every view
--   before re-granting only SELECT.
--
-- Idempotent: safe to re-apply.
-- Additive: no RLS policies, columns, tables, or business logic are changed.
-- Apply after: 001–011 already applied.
-- ─────────────────────────────────────────────────────────────────────────────


-- ═══════════════════════════════════════════════════════════════════════════════
-- A. FUNCTION EXECUTE HARDENING — get_my_app_user_id()
-- ═══════════════════════════════════════════════════════════════════════════════
--
-- Why PUBLIC EXECUTE must be revoked from SECURITY DEFINER functions
-- ──────────────────────────────────────────────────────────────────
-- 1. A SECURITY DEFINER function always executes as its owner (postgres /
--    supabase_admin), regardless of which role invoked it.
-- 2. With PUBLIC EXECUTE, the anon role can call get_my_app_user_id() directly
--    through the Supabase Data API (/rpc/get_my_app_user_id).
-- 3. When called by anon, auth.jwt() ->> 'email' evaluates to NULL, so the
--    function returns NULL rather than leaking a row — the immediate risk is
--    low.  However:
--      a. The function's body may change in the future; keeping PUBLIC EXECUTE
--         permanently widens the attack surface of any future revision.
--      b. Defence-in-depth requires that unauthenticated callers cannot invoke
--         any SECURITY DEFINER function, even if the current behaviour is safe.
--      c. Supabase PostgREST exposes public-schema RPC functions as HTTP
--         endpoints.  Revoking PUBLIC/anon EXECUTE removes the endpoint from
--         the anonymous API surface.
-- 4. The function is used only inside RLS policy USING/WITH CHECK expressions.
--    The database engine invokes it internally; explicit EXECUTE by a client
--    role is never required for RLS evaluation.  Revoking from PUBLIC does not
--    affect any RLS policy.

-- Full revoke-then-precise-grant pattern to strip all prior grants atomically.
revoke all on function public.get_my_app_user_id() from public;
revoke all on function public.get_my_app_user_id() from anon;
revoke all on function public.get_my_app_user_id() from authenticated;
revoke all on function public.get_my_app_user_id() from service_role;

grant execute on function public.get_my_app_user_id() to authenticated;
grant execute on function public.get_my_app_user_id() to service_role;


-- ═══════════════════════════════════════════════════════════════════════════════
-- B. VIEW EFFECTIVE PRIVILEGE COMPLETENESS
-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration 011 revoked anon/public from views but did not fully revoke
-- existing authenticated grants first.  This section does a clean revoke-all-
-- then-regrant-select pass on every public view so that no residual extra
-- privileges (REFERENCES, TRIGGER, TRUNCATE) can remain on any view regardless
-- of what Supabase's ALTER DEFAULT PRIVILEGES previously set.

-- ── Intermediate views ───────────────────────────────────────────────────────
revoke all on latest_price_eod          from public, anon, authenticated;
revoke all on latest_ratios_factors     from public, anon, authenticated;
revoke all on latest_valuation_runs     from public, anon, authenticated;
revoke all on latest_qualitative_scores from public, anon, authenticated;
revoke all on latest_signal_runs        from public, anon, authenticated;

grant select on latest_price_eod          to authenticated, service_role;
grant select on latest_ratios_factors     to authenticated, service_role;
grant select on latest_valuation_runs     to authenticated, service_role;
grant select on latest_qualitative_scores to authenticated, service_role;
grant select on latest_signal_runs        to authenticated, service_role;

-- ── Dashboard-facing views (security_invoker = true) ─────────────────────────
revoke all on dashboard_watchlist_latest   from public, anon, authenticated;
revoke all on dashboard_watchlist_inactive from public, anon, authenticated;
revoke all on analysis_readiness_latest    from public, anon, authenticated;

grant select on dashboard_watchlist_latest   to authenticated, service_role;
grant select on dashboard_watchlist_inactive to authenticated, service_role;
grant select on analysis_readiness_latest    to authenticated, service_role;
