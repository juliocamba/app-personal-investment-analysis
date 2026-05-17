-- 027_latest_views_security_invoker.sql
-- Security hardening: recreate four legacy latest_* analytical views with
-- security_invoker = true so access is evaluated as the calling role.
--
-- This migration does not change:
--   - output columns
--   - column order
--   - distinct-on semantics
--   - ordering semantics
--   - dashboard behavior
--   - pipeline behavior

create or replace view latest_ratios_factors
with (security_invoker = true) as
select distinct on (company_id)
  *
from ratios_factors
order by company_id, factor_date desc;

create or replace view latest_valuation_runs
with (security_invoker = true) as
select distinct on (company_id)
  *
from valuation_runs
order by company_id, valuation_date desc, created_at desc;

create or replace view latest_qualitative_scores
with (security_invoker = true) as
select distinct on (company_id)
  *
from qualitative_scores
order by company_id, score_date desc, created_at desc;

create or replace view latest_signal_runs
with (security_invoker = true) as
select distinct on (company_id)
  *
from signal_runs
order by company_id, signal_date desc, created_at desc;

revoke all on latest_ratios_factors from public, anon, authenticated;
revoke all on latest_valuation_runs from public, anon, authenticated;
revoke all on latest_qualitative_scores from public, anon, authenticated;
revoke all on latest_signal_runs from public, anon, authenticated;

grant select on latest_ratios_factors to authenticated, service_role;
grant select on latest_valuation_runs to authenticated, service_role;
grant select on latest_qualitative_scores to authenticated, service_role;
grant select on latest_signal_runs to authenticated, service_role;
