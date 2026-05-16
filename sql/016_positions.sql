-- 016_positions.sql
-- Phase 12B.1: Manual positions foundation.
--
-- Adds a user-owned positions table for manual portfolio tracking.
-- This table is intentionally separate from:
--   - signal_runs
--   - company_analysis_readiness
--   - company_data_quality_snapshots
--   - valuation and alerts
--   - watchlist analytics logic
--
-- Positions are decision-support recordkeeping only. They do not drive
-- pipeline behavior, signal generation, readiness, alerts, or dashboard
-- analytics views in this phase.

create table if not exists positions (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references app_users(id) on delete cascade,
  company_id          uuid not null references companies(id) on delete restrict,
  entry_date          date not null,
  quantity            numeric not null,
  average_entry_price numeric not null,
  currency            text not null,
  fees                numeric,
  notes               text,
  status              text not null default 'active',
  closed_at           timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint positions_quantity_positive
    check (quantity > 0),
  constraint positions_average_entry_price_positive
    check (average_entry_price > 0),
  constraint positions_fees_non_negative
    check (fees is null or fees >= 0),
  constraint positions_status_check
    check (status in ('active', 'closed'))
);

drop trigger if exists update_positions_updated_at on positions;
create trigger update_positions_updated_at
  before update on positions
  for each row execute function update_updated_at_column();

create or replace function normalize_position_record()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.user_id is null then
    new.user_id := get_my_app_user_id();
  end if;

  new.currency := upper(trim(new.currency));
  new.notes := nullif(trim(new.notes), '');

  if new.status = 'active' then
    new.closed_at := null;
  end if;

  return new;
end;
$$;

drop trigger if exists normalize_position_record_write on positions;
create trigger normalize_position_record_write
  before insert or update on positions
  for each row execute function normalize_position_record();

create index if not exists idx_positions_user_status_entry_date
  on positions (user_id, status, entry_date desc);

create index if not exists idx_positions_company_id
  on positions (company_id);

create unique index if not exists idx_positions_one_active_per_user_company
  on positions (user_id, company_id)
  where status = 'active';

alter table positions enable row level security;

drop policy if exists "users read own positions" on positions;
create policy "users read own positions"
  on positions
  for select
  to authenticated
  using (user_id = get_my_app_user_id());

drop policy if exists "users insert own positions" on positions;
create policy "users insert own positions"
  on positions
  for insert
  to authenticated
  with check (user_id = get_my_app_user_id());

drop policy if exists "users update own positions" on positions;
create policy "users update own positions"
  on positions
  for update
  to authenticated
  using (user_id = get_my_app_user_id())
  with check (user_id = get_my_app_user_id());

drop policy if exists "users delete own positions" on positions;
create policy "users delete own positions"
  on positions
  for delete
  to authenticated
  using (user_id = get_my_app_user_id());

revoke all on positions from public, anon, authenticated;
grant select, insert, update, delete on positions to authenticated;
grant select, insert, update, delete on positions to service_role;
