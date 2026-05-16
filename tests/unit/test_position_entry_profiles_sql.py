from __future__ import annotations

from pathlib import Path


SQL_DIR = Path(__file__).parent.parent.parent / "sql"
MIGRATION = SQL_DIR / "018_position_entry_profiles.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_018_exists() -> None:
    assert MIGRATION.exists(), "Migration 018_position_entry_profiles.sql not found in sql/"


def test_creates_position_entry_profiles_table() -> None:
    sql = _sql()
    assert "create table if not exists position_entry_profiles" in sql
    assert "position_id                uuid not null references positions(id)" in sql
    assert "user_id                    uuid not null references app_users(id)" in sql
    assert "constraint position_entry_profiles_position_id_unique unique (position_id)" in sql


def test_thesis_constraints_exist() -> None:
    sql = _sql()
    assert "check (target_price is null or target_price > 0)" in sql
    assert "confidence_level in ('low', 'medium', 'high')" in sql


def test_snapshot_trigger_uses_stored_views_only() -> None:
    sql = _sql()
    assert "create or replace function refresh_position_entry_profile_snapshot()" in sql
    assert "from latest_price_eod" in sql
    assert "from latest_valuation_runs" in sql
    assert "left join latest_signal_runs" in sql
    assert "left join latest_qualitative_scores" in sql
    assert "left join analysis_readiness_latest" in sql
    assert "left join latest_company_data_quality_snapshots" in sql
    assert "after insert on position_entry_profiles" in sql


def test_positions_insert_trigger_creates_entry_profile() -> None:
    sql = _sql()
    assert "create or replace function create_position_entry_profile()" in sql
    assert "after insert on positions" in sql
    assert "insert into position_entry_profiles (position_id, user_id)" in sql


def test_position_entry_profiles_rls_and_scoped_grants_exist() -> None:
    sql = _sql()
    assert "alter table position_entry_profiles enable row level security;" in sql
    assert 'create policy "users read own position entry profiles"' in sql
    assert 'create policy "users insert own position entry profiles"' in sql
    assert 'create policy "users update own position entry profiles"' in sql
    assert "grant select on position_entry_profiles to authenticated;" in sql
    assert "grant select, insert, update, delete on position_entry_profiles to service_role;" in sql
