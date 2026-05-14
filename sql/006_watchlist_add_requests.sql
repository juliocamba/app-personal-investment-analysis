-- 006_watchlist_add_requests.sql
-- Phase 9B: Add New Company Request Flow
--
-- Introduces watchlist_add_requests: authenticated users submit pending
-- requests; the backend pipeline is the sole authority to validate, enrich,
-- and approve/reject them.
--
-- Idempotent: safe to re-run against an already-migrated database.
-- Requires: 001, 002, 003, 004, 005 already applied.
-- Requires: get_my_app_user_id() (from 002_rls_policies.sql).
-- Requires: update_updated_at_column() trigger function (from 003_views_and_functions.sql).

-- ── 1. Create table ───────────────────────────────────────────────────────────

create table if not exists watchlist_add_requests (
  id               uuid        primary key default gen_random_uuid(),
  user_id          uuid        not null references app_users(id) on delete cascade,
  watchlist_id     uuid        not null references watchlists(id) on delete cascade,
  requested_ticker text        not null,
  requested_exchange text,
  status           text        not null default 'pending',
  company_id       uuid        references companies(id) on delete set null,
  error_code       text,
  error_message    text,
  requested_at     timestamptz not null default now(),
  processed_at     timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint watchlist_add_requests_status_check
    check (status in ('pending', 'approved', 'rejected', 'failed', 'cancelled'))
);

-- ── 2. updated_at trigger ─────────────────────────────────────────────────────

drop trigger if exists update_watchlist_add_requests_updated_at on watchlist_add_requests;
create trigger update_watchlist_add_requests_updated_at
  before update on watchlist_add_requests
  for each row execute function update_updated_at_column();

-- ── 3. Normalization trigger: uppercase/trim ticker and exchange on INSERT ────
-- Sets user_id from get_my_app_user_id() when omitted (supports frontend inserts).

create or replace function normalize_watchlist_add_request()
returns trigger language plpgsql security definer as $$
begin
  new.requested_ticker := upper(trim(new.requested_ticker));
  if new.requested_exchange is not null then
    new.requested_exchange := nullif(trim(upper(new.requested_exchange)), '');
  end if;
  -- Allow frontend to omit user_id; fill it from the session JWT.
  if new.user_id is null then
    new.user_id := get_my_app_user_id();
  end if;
  return new;
end;
$$;

drop trigger if exists normalize_watchlist_add_request_insert on watchlist_add_requests;
create trigger normalize_watchlist_add_request_insert
  before insert on watchlist_add_requests
  for each row execute function normalize_watchlist_add_request();

-- ── 4. Indexes ────────────────────────────────────────────────────────────────

-- For pipeline: fetch all pending requests ordered by submission time.
create index if not exists idx_watchlist_add_requests_status_requested_at
  on watchlist_add_requests (status, requested_at);

-- For frontend: fetch a watchlist's requests ordered newest-first.
create index if not exists idx_watchlist_add_requests_watchlist_requested_at
  on watchlist_add_requests (watchlist_id, requested_at desc);

-- Deduplication: prevent a user from submitting the same pending ticker
-- (+ exchange) for the same watchlist more than once.
-- Exchange is normalised to '' when null so the index works correctly.
create unique index if not exists idx_watchlist_add_requests_pending_dedup
  on watchlist_add_requests (watchlist_id, upper(requested_ticker), coalesce(upper(requested_exchange), ''))
  where status = 'pending';

-- ── 5. Row Level Security ─────────────────────────────────────────────────────

alter table watchlist_add_requests enable row level security;

-- Deny all access to the public / anon role.
revoke all on watchlist_add_requests from public, anon;

-- Grant authenticated users SELECT and column-limited INSERT and UPDATE.
-- INSERT is restricted to the three fields a frontend user may supply.
--   Pipeline-owned fields (status, company_id, error_code, error_message,
--   processed_at, user_id, requested_at, created_at, updated_at) cannot be
--   set by authenticated clients at insert time.
-- UPDATE is restricted to status only, so authenticated users cannot mutate
--   any pipeline-owned outcome field even during cancellation.
-- The column-level grants are enforced by the database engine independently
--   of RLS; even a malicious JWT bearer cannot touch any other column.
-- No DELETE is granted — requests are immutable once submitted.
grant select on watchlist_add_requests to authenticated;
grant insert(watchlist_id, requested_ticker, requested_exchange) on watchlist_add_requests to authenticated;
grant update(status) on watchlist_add_requests to authenticated;

-- SELECT: users can only read their own requests.
drop policy if exists "users read own add requests" on watchlist_add_requests;
create policy "users read own add requests"
  on watchlist_add_requests
  for select
  to authenticated
  using (user_id = get_my_app_user_id());

-- INSERT: users can only insert requests for their own watchlists.
-- The normalization trigger fills user_id from the session, so we check both.
drop policy if exists "users insert own add requests" on watchlist_add_requests;
create policy "users insert own add requests"
  on watchlist_add_requests
  for insert
  to authenticated
  with check (
    user_id = get_my_app_user_id()
    and watchlist_id in (
      select id from watchlists where user_id = get_my_app_user_id()
    )
  );

-- UPDATE: users can only cancel their own pending requests.
-- Transitions to any status other than 'cancelled' are blocked for authenticated users.
-- The backend pipeline uses the service_role key and bypasses RLS entirely.
drop policy if exists "users cancel own pending add requests" on watchlist_add_requests;
create policy "users cancel own pending add requests"
  on watchlist_add_requests
  for update
  to authenticated
  using  (user_id = get_my_app_user_id() and status = 'pending')
  with check (user_id = get_my_app_user_id() and status = 'cancelled');

-- ── 6. Privilege hardening notes ─────────────────────────────────────────────
-- Phase 9A privilege hardening is preserved:
--   • authenticated role has SELECT, UPDATE on watchlist_companies (no INSERT).
--   • authenticated role has no access to companies (cannot create/modify).
-- Phase 9B adds no new grants on companies or watchlist_companies.
