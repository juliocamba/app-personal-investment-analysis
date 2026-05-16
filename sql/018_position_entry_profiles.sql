-- 018_position_entry_profiles.sql
-- Phase 12C.1: entry thesis + entry snapshot foundation for positions.
--
-- Adds a separate entry-profile lane for manual positions. This lane is
-- intentionally separate from:
--   - signal_runs
--   - company_analysis_readiness
--   - company_data_quality_snapshots
--   - valuation math and alerts
--   - watchlist analytics views
--
-- Snapshot rows are populated only from already-stored database state.
-- No provider calls, pipeline execution, or analytical recalculation occurs.

create table if not exists position_entry_profiles (
  id                         uuid primary key default gen_random_uuid(),
  position_id                uuid not null references positions(id) on delete cascade,
  user_id                    uuid not null references app_users(id) on delete cascade,
  snapshot_taken_at          timestamptz not null default now(),

  thesis_summary             text,
  why_bought                 text,
  key_risks                  text,
  target_price               numeric,
  target_price_currency      text,
  expected_holding_period    text,
  confidence_level           text,
  catalysts                  text,
  invalidation_criteria      text,

  entry_price                numeric,
  entry_price_date           date,
  entry_price_currency       text,
  entry_signal               text,
  entry_readiness_status     text,
  entry_data_quality_status  text,
  entry_quality_score        numeric,
  entry_current_price        numeric,
  entry_valuation_low        numeric,
  entry_valuation_mid        numeric,
  entry_valuation_high       numeric,
  entry_margin_of_safety     numeric,
  entry_uncertainty_category text,
  entry_snapshot_details     jsonb not null default '{}'::jsonb,

  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint position_entry_profiles_position_id_unique unique (position_id),
  constraint position_entry_profiles_target_price_positive
    check (target_price is null or target_price > 0),
  constraint position_entry_profiles_confidence_level_check
    check (
      confidence_level is null
      or confidence_level in ('low', 'medium', 'high')
    )
);

drop trigger if exists update_position_entry_profiles_updated_at on position_entry_profiles;
create trigger update_position_entry_profiles_updated_at
  before update on position_entry_profiles
  for each row execute function update_updated_at_column();

create or replace function normalize_position_entry_profile()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.user_id is null then
    new.user_id := get_my_app_user_id();
  end if;

  new.thesis_summary := nullif(trim(new.thesis_summary), '');
  new.why_bought := nullif(trim(new.why_bought), '');
  new.key_risks := nullif(trim(new.key_risks), '');
  new.expected_holding_period := nullif(trim(new.expected_holding_period), '');
  new.confidence_level := nullif(lower(trim(new.confidence_level)), '');
  new.catalysts := nullif(trim(new.catalysts), '');
  new.invalidation_criteria := nullif(trim(new.invalidation_criteria), '');
  new.target_price_currency := nullif(upper(trim(new.target_price_currency)), '');

  if new.entry_snapshot_details is null then
    new.entry_snapshot_details := '{}'::jsonb;
  end if;

  if new.snapshot_taken_at is null then
    new.snapshot_taken_at := now();
  end if;

  return new;
end;
$$;

drop trigger if exists normalize_position_entry_profile_write on position_entry_profiles;
create trigger normalize_position_entry_profile_write
  before insert or update on position_entry_profiles
  for each row execute function normalize_position_entry_profile();

create or replace function refresh_position_entry_profile_snapshot()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update position_entry_profiles pep
  set
    entry_price = price_snap.current_price,
    entry_price_date = price_snap.price_date,
    entry_price_currency = price_snap.price_currency,
    entry_signal = signal_snap.final_signal,
    entry_readiness_status = readiness_snap.readiness_status,
    entry_data_quality_status = dq_snap.data_quality_status,
    entry_quality_score = quality_snap.final_quality_score,
    entry_current_price = price_snap.current_price,
    entry_valuation_low = valuation_snap.iv_p25,
    entry_valuation_mid = valuation_snap.iv_p50,
    entry_valuation_high = valuation_snap.iv_p75,
    entry_margin_of_safety = valuation_snap.margin_of_safety_conservative,
    entry_uncertainty_category = valuation_snap.uncertainty_category,
    entry_snapshot_details = jsonb_strip_nulls(
      jsonb_build_object(
        'provider_mix', readiness_snap.provider_mix,
        'p_buy', signal_snap.p_buy,
        'p_buy_adjusted', signal_snap.p_buy_adjusted,
        'p_sell', signal_snap.p_sell,
        'mos_basis', valuation_snap.mos_basis,
        'scenario_count', valuation_snap.scenario_count,
        'distribution_collapsed', valuation_snap.distribution_collapsed,
        'data_quality_warning_codes', dq_snap.data_quality_warning_codes
      )
    )
  from positions pos
  left join (
    select
      company_id,
      price_date,
      close as current_price,
      currency as price_currency
    from latest_price_eod
  ) price_snap on price_snap.company_id = pos.company_id
  left join latest_signal_runs signal_snap on signal_snap.company_id = pos.company_id
  left join latest_qualitative_scores quality_snap on quality_snap.company_id = pos.company_id
  left join (
    select
      company_id,
      iv_p25,
      iv_p50,
      iv_p75,
      margin_of_safety_conservative,
      assumptions->'diagnostics'->>'uncertainty_category' as uncertainty_category,
      assumptions->'diagnostics'->>'mos_basis' as mos_basis,
      (assumptions->'diagnostics'->>'scenario_count')::int as scenario_count,
      (assumptions->'diagnostics'->'warnings') @> '["distribution_collapsed"]'::jsonb
        as distribution_collapsed
    from latest_valuation_runs
  ) valuation_snap on valuation_snap.company_id = pos.company_id
  left join analysis_readiness_latest readiness_snap on readiness_snap.company_id = pos.company_id
  left join latest_company_data_quality_snapshots dq_snap on dq_snap.company_id = pos.company_id
  where pep.id = new.id
    and pos.id = new.position_id;

  return null;
end;
$$;

drop trigger if exists refresh_position_entry_profile_snapshot_after_insert on position_entry_profiles;
create trigger refresh_position_entry_profile_snapshot_after_insert
  after insert on position_entry_profiles
  for each row execute function refresh_position_entry_profile_snapshot();

create or replace function create_position_entry_profile()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into position_entry_profiles (position_id, user_id)
  values (new.id, new.user_id)
  on conflict (position_id) do nothing;

  return new;
end;
$$;

drop trigger if exists create_position_entry_profile_after_insert on positions;
create trigger create_position_entry_profile_after_insert
  after insert on positions
  for each row execute function create_position_entry_profile();

create index if not exists idx_position_entry_profiles_user_id
  on position_entry_profiles (user_id);

alter table position_entry_profiles enable row level security;

drop policy if exists "users read own position entry profiles" on position_entry_profiles;
create policy "users read own position entry profiles"
  on position_entry_profiles
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

drop policy if exists "users insert own position entry profiles" on position_entry_profiles;
create policy "users insert own position entry profiles"
  on position_entry_profiles
  for insert
  to authenticated
  with check (
    user_id = get_my_app_user_id()
    and exists (
      select 1
      from positions pos
      where pos.id = position_id
        and pos.user_id = get_my_app_user_id()
    )
  );

drop policy if exists "users update own position entry profiles" on position_entry_profiles;
create policy "users update own position entry profiles"
  on position_entry_profiles
  for update
  to authenticated
  using (
    user_id = get_my_app_user_id()
    and exists (
      select 1
      from positions pos
      where pos.id = position_id
        and pos.user_id = get_my_app_user_id()
    )
  )
  with check (
    user_id = get_my_app_user_id()
    and exists (
      select 1
      from positions pos
      where pos.id = position_id
        and pos.user_id = get_my_app_user_id()
    )
  );

revoke all on position_entry_profiles from public, anon, authenticated;
grant select on position_entry_profiles to authenticated;
grant insert (
  position_id,
  thesis_summary,
  why_bought,
  key_risks,
  target_price,
  target_price_currency,
  expected_holding_period,
  confidence_level,
  catalysts,
  invalidation_criteria
) on position_entry_profiles to authenticated;
grant update (
  thesis_summary,
  why_bought,
  key_risks,
  target_price,
  target_price_currency,
  expected_holding_period,
  confidence_level,
  catalysts,
  invalidation_criteria
) on position_entry_profiles to authenticated;
grant select, insert, update, delete on position_entry_profiles to service_role;
