-- 014_company_data_quality_snapshots.sql
-- Phase 12A.2: persist backend-owned data-quality diagnostics snapshots.
--
-- One row per company_id + snapshot_date. These snapshots are diagnostic-only:
-- they do not change readiness, valuation, signals, alerts, or dashboard views.
--
-- Additive and idempotent where practical.

create table if not exists company_data_quality_snapshots (
  id                         uuid        primary key default gen_random_uuid(),
  company_id                 uuid        not null
                                       references companies(id) on delete cascade,
  snapshot_date              date        not null,
  price_validation_status    text        not null,
  price_reference_provider   text,
  price_comparison_provider  text,
  price_comparison_date      date,
  price_divergence_pct       numeric,
  warning_codes              jsonb       not null default '[]'::jsonb,
  details                    jsonb       not null default '{}'::jsonb,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint company_data_quality_snapshots_company_date_key
    unique(company_id, snapshot_date),
  constraint check_company_data_quality_price_validation_status check (
    price_validation_status in ('ok', 'warning', 'critical', 'not_comparable')
  ),
  constraint check_company_data_quality_warning_codes_is_array check (
    jsonb_typeof(warning_codes) = 'array'
  ),
  constraint check_company_data_quality_details_is_object check (
    jsonb_typeof(details) = 'object'
  )
);

drop trigger if exists update_company_data_quality_snapshots_updated_at
  on company_data_quality_snapshots;

create trigger update_company_data_quality_snapshots_updated_at
  before update on company_data_quality_snapshots
  for each row execute function update_updated_at_column();

alter table company_data_quality_snapshots enable row level security;

drop policy if exists "authenticated read company data quality snapshots"
  on company_data_quality_snapshots;

create policy "authenticated read company data quality snapshots"
  on company_data_quality_snapshots
  for select to authenticated using (true);

revoke all on company_data_quality_snapshots from public, anon, authenticated;
grant select on company_data_quality_snapshots to authenticated;
grant select, insert, update, delete on company_data_quality_snapshots to service_role;
