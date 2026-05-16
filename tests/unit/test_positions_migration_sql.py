from __future__ import annotations

from pathlib import Path


SQL_DIR = Path(__file__).parent.parent.parent / "sql"
MIGRATION = SQL_DIR / "016_positions.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_016_exists() -> None:
    assert MIGRATION.exists(), "Migration 016_positions.sql not found in sql/"


def test_creates_positions_table() -> None:
    sql = _sql()
    assert "create table if not exists positions" in sql
    assert "user_id             uuid not null references app_users(id)" in sql
    assert "company_id          uuid not null references companies(id)" in sql


def test_positions_constraints_exist() -> None:
    sql = _sql()
    assert "check (quantity > 0)" in sql
    assert "check (average_entry_price > 0)" in sql
    assert "check (fees is null or fees >= 0)" in sql
    assert "check (status in ('active', 'closed'))" in sql


def test_positions_has_single_active_position_partial_unique_index() -> None:
    sql = _sql()
    assert "create unique index if not exists idx_positions_one_active_per_user_company" in sql
    assert "where status = 'active'" in sql


def test_positions_enables_rls_and_scoped_policies() -> None:
    sql = _sql()
    assert "alter table positions enable row level security;" in sql
    assert 'create policy "users read own positions"' in sql
    assert 'create policy "users insert own positions"' in sql
    assert 'create policy "users update own positions"' in sql
    assert 'create policy "users delete own positions"' in sql
    assert "get_my_app_user_id()" in sql


def test_positions_grants_follow_auth_scoped_pattern() -> None:
    sql = _sql()
    assert "revoke all on positions from public, anon, authenticated;" in sql
    assert "grant select, insert, update, delete on positions to authenticated;" in sql
    assert "grant select, insert, update, delete on positions to service_role;" in sql
