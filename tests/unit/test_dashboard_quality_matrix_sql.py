"""Static SQL contract tests for dashboard research-quality projection."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "031_dashboard_quality_matrix_fields.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_031_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/031_dashboard_quality_matrix_fields.sql"


def test_recreates_dashboard_watchlist_latest() -> None:
    sql = _sql()
    assert "create or replace view dashboard_watchlist_latest" in sql


def test_appends_quality_matrix_summary_fields() -> None:
    sql = _sql()
    for fragment in (
        "as quality_matrix_max_severity",
        "as quality_matrix_blocking_domains",
        "as quality_matrix_primary_codes",
    ):
        assert fragment in sql


def test_quality_matrix_projection_is_read_only_and_preserves_suppression() -> None:
    sql = _sql()
    assert "when ar.can_run_signal is false then null" in sql
    assert "valuation_display_suppressed" in sql
    assert "then 'blocks_both'" in sql
    assert "then 'blocks_valuation'" in sql
    assert "then 'confidence_limited'" in sql


def test_quality_matrix_primary_codes_are_compact() -> None:
    sql = _sql()
    assert "limit 5" in sql
    assert "valuation_sanity_reason_codes" in sql
    assert "readiness_reason_codes" in sql
    assert "data_quality_warning_codes" in sql


def test_migration_031_grants_dashboard_view_select() -> None:
    sql = _sql()
    assert "grant  select on dashboard_watchlist_latest to authenticated, service_role;" in sql
