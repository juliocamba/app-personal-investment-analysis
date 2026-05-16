-- 021_position_review_alert_lifecycle_controls.sql
-- Phase 12D.2: authenticated lifecycle controls for persisted position review
-- alerts.
--
-- This migration keeps alert generation logic unchanged. It only adds a
-- tightly scoped authenticated update path for lifecycle management:
--   - open -> dismissed
--   - open -> snoozed
--   - snoozed -> open (system-driven after snooze expiry if condition persists)
--
-- Alerts remain decision-support only. No automatic selling, closing, or
-- external notification behavior is added here.

drop policy if exists "users update own position review alerts lifecycle"
  on position_review_alerts;
create policy "users update own position review alerts lifecycle"
  on position_review_alerts
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
    and status in ('dismissed', 'snoozed')
  );

grant update (
  status,
  dismissed_at,
  dismissed_reason,
  snoozed_until
) on position_review_alerts to authenticated;
