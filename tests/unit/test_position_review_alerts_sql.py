from __future__ import annotations

from pathlib import Path


SQL_DIR = Path(__file__).parent.parent.parent / "sql"
MIGRATION = SQL_DIR / "020_position_review_alerts.sql"
LIFECYCLE_MIGRATION = SQL_DIR / "021_position_review_alert_lifecycle_controls.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def _lifecycle_sql() -> str:
    return LIFECYCLE_MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_020_exists() -> None:
    assert MIGRATION.exists(), "Expected sql/020_position_review_alerts.sql"


def test_migration_021_exists() -> None:
    assert LIFECYCLE_MIGRATION.exists(), "Expected sql/021_position_review_alert_lifecycle_controls.sql"


def test_creates_position_review_alerts_table_with_expected_keys() -> None:
    sql = _sql()
    assert "create table if not exists position_review_alerts" in sql
    assert "position_id      uuid not null references positions(id)" in sql
    assert "user_id          uuid not null references app_users(id)" in sql
    assert "company_id       uuid not null references companies(id)" in sql
    assert "constraint position_review_alerts_dedupe_key_unique unique (dedupe_key)" in sql


def test_expected_alert_type_severity_and_status_constraints_exist() -> None:
    sql = _sql()
    assert "target_price_reached" in sql
    assert "signal_deterioration" in sql
    assert "readiness_deterioration" in sql
    assert "data_quality_deterioration" in sql
    assert "severity in ('info', 'warning', 'critical')" in sql
    assert "status in ('open', 'snoozed', 'dismissed', 'resolved')" in sql


def test_020_rls_and_grants_are_read_only_for_authenticated() -> None:
    sql = _sql()
    assert "alter table position_review_alerts enable row level security;" in sql
    assert 'create policy "users read own position review alerts"' in sql
    assert "grant select on position_review_alerts to authenticated;" in sql
    assert "grant select, insert, update, delete on position_review_alerts to service_role;" in sql
    assert "grant insert on position_review_alerts to authenticated;" not in sql
    assert "grant update on position_review_alerts to authenticated;" not in sql


def test_021_adds_scoped_authenticated_lifecycle_update() -> None:
    sql = _lifecycle_sql()
    assert 'create policy "users update own position review alerts lifecycle"' in sql
    assert "for update" in sql
    assert "status in ('dismissed', 'snoozed')" in sql
    assert "grant update (" in sql
    assert "status" in sql
    assert "dismissed_at" in sql
    assert "dismissed_reason" in sql
    assert "snoozed_until" in sql
    assert "position_review_alerts to authenticated;" in sql
