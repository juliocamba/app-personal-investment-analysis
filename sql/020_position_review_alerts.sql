-- 020_position_review_alerts.sql
-- Phase 12D.1: persisted review-alert foundation for open positions.
--
-- Adds a separate position-review alert lane for decision-support prompts.
-- These alerts are intentionally separate from:
--   - signal_runs
--   - company_analysis_readiness
--   - company_data_quality_snapshots
--   - valuation logic
--   - automated trade execution
--
-- Alerts in this phase are review prompts only. They do not recommend selling,
-- do not close positions automatically, and use already-persisted DB state only.

create table if not exists position_review_alerts (
  id               uuid primary key default gen_random_uuid(),
  position_id      uuid not null references positions(id) on delete cascade,
  user_id          uuid not null references app_users(id) on delete cascade,
  company_id       uuid not null references companies(id) on delete cascade,
  alert_type       text not null,
  severity         text not null,
  status           text not null default 'open',
  title            text not null,
  message          text not null,
  details          jsonb not null default '{}'::jsonb,
  dedupe_key       text not null,
  triggered_at     timestamptz not null default now(),
  first_seen_at    timestamptz not null default now(),
  last_seen_at     timestamptz not null default now(),
  resolved_at      timestamptz,
  dismissed_at     timestamptz,
  dismissed_reason text,
  snoozed_until    timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  constraint position_review_alerts_alert_type_check
    check (
      alert_type in (
        'target_price_reached',
        'signal_deterioration',
        'readiness_deterioration',
        'data_quality_deterioration'
      )
    ),
  constraint position_review_alerts_severity_check
    check (severity in ('info', 'warning', 'critical')),
  constraint position_review_alerts_status_check
    check (status in ('open', 'snoozed', 'dismissed', 'resolved')),
  constraint position_review_alerts_dedupe_key_unique unique (dedupe_key)
);

drop trigger if exists update_position_review_alerts_updated_at on position_review_alerts;
create trigger update_position_review_alerts_updated_at
  before update on position_review_alerts
  for each row execute function update_updated_at_column();

create or replace function normalize_position_review_alert()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.user_id is null then
    new.user_id := get_my_app_user_id();
  end if;

  new.title := trim(new.title);
  new.message := trim(new.message);
  new.dismissed_reason := nullif(trim(new.dismissed_reason), '');
  new.details := coalesce(new.details, '{}'::jsonb);

  if new.status = 'open' then
    new.resolved_at := null;
    new.dismissed_at := null;
    new.dismissed_reason := null;
    new.snoozed_until := null;
  elsif new.status = 'resolved' then
    new.dismissed_at := null;
    new.dismissed_reason := null;
    new.snoozed_until := null;
  elsif new.status = 'dismissed' then
    new.resolved_at := null;
    new.snoozed_until := null;
  elsif new.status = 'snoozed' then
    new.resolved_at := null;
    new.dismissed_at := null;
    new.dismissed_reason := null;
  end if;

  if new.first_seen_at is null then
    new.first_seen_at := now();
  end if;
  if new.last_seen_at is null then
    new.last_seen_at := now();
  end if;
  if new.triggered_at is null then
    new.triggered_at := now();
  end if;

  return new;
end;
$$;

drop trigger if exists normalize_position_review_alert_write on position_review_alerts;
create trigger normalize_position_review_alert_write
  before insert or update on position_review_alerts
  for each row execute function normalize_position_review_alert();

create index if not exists idx_position_review_alerts_user_status_last_seen
  on position_review_alerts (user_id, status, last_seen_at desc);

create index if not exists idx_position_review_alerts_position_id
  on position_review_alerts (position_id);

alter table position_review_alerts enable row level security;

drop policy if exists "users read own position review alerts" on position_review_alerts;
create policy "users read own position review alerts"
  on position_review_alerts
  for select
  to authenticated
  using (
    user_id = get_my_app_user_id()
    and exists (
      select 1
      from positions pos
      where pos.id = position_id
        and pos.user_id = get_my_app_user_id()
    )
  );

revoke all on position_review_alerts from public, anon, authenticated;
grant select on position_review_alerts to authenticated;
grant select, insert, update, delete on position_review_alerts to service_role;
