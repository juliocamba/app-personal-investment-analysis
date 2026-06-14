"""Static SQL contract tests for Phase 12G valuation sanity display suppression."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "029_dashboard_valuation_sanity_suppression.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_029_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/029_dashboard_valuation_sanity_suppression.sql"


def test_recreates_dashboard_watchlist_latest() -> None:
    sql = _sql()
    assert "create or replace view dashboard_watchlist_latest" in sql


def test_uses_valuation_display_suppressed_guard() -> None:
    sql = _sql()
    assert "valuation_display_suppressed" in sql
    assert "coalesce((v.assumptions->'diagnostics'->>'valuation_display_suppressed')::boolean, false)" in sql


def test_suppresses_valuation_and_diagnostics_projection_fields() -> None:
    sql = _sql()
    for column in (
        "as iv_p25",
        "as iv_p50",
        "as iv_p75",
        "as margin_of_safety_conservative",
        "as uncertainty_width",
        "as mos_basis",
        "as scenario_count",
        "as uncertainty_category",
        "as distribution_collapsed",
    ):
        assert column in sql


def test_preserves_signal_projection_guard_by_can_run_signal() -> None:
    sql = _sql()
    assert "when ar.can_run_signal is false then null" in sql


def test_migration_029_grants_dashboard_view_select() -> None:
    sql = _sql()
    assert "grant  select on dashboard_watchlist_latest to authenticated, service_role;" in sql
