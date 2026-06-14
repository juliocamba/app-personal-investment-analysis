"""Static SQL contract tests for Phase 12G signal display-state projection."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "030_dashboard_signal_display_state.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_030_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/030_dashboard_signal_display_state.sql"


def test_recreates_dashboard_watchlist_latest() -> None:
    sql = _sql()
    assert "create or replace view dashboard_watchlist_latest" in sql


def test_preserves_signal_suppression_when_can_run_signal_false() -> None:
    sql = _sql()
    assert "when ar.can_run_signal is false then null" in sql
    for column in (
        "as p_buy",
        "as p_buy_adjusted",
        "as p_sell",
        "as final_signal",
        "as red_flags",
        "as explanation",
        "as freshness_flag",
    ):
        assert column in sql


def test_surfaces_raw_and_display_state_signal_columns() -> None:
    sql = _sql()
    assert "as stored_final_signal" in sql
    assert "as signal_display_state" in sql


def test_migration_030_grants_dashboard_view_select() -> None:
    sql = _sql()
    assert "grant  select on dashboard_watchlist_latest to authenticated, service_role;" in sql