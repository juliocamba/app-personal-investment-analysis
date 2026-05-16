"""Static SQL contract tests for Phase 12A.5 dashboard data-quality exposure."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "015_dashboard_data_quality_lane.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_015_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/015_dashboard_data_quality_lane.sql"


def test_creates_latest_company_data_quality_snapshots_view() -> None:
    sql = _sql()
    assert "create view latest_company_data_quality_snapshots" in sql
    assert "security_invoker = true" in sql


def test_dashboard_watchlist_latest_appends_data_quality_columns() -> None:
    sql = _sql()
    expected_columns = [
      "as data_quality_status",
      "data_quality_warning_codes",
      "price_validation_status",
      "statement_completeness_status",
      "statement_completeness_summary",
      "fundamentals_provider_comparison_status",
      "fundamentals_provider_comparison_summary",
    ]
    for column in expected_columns:
        assert column in sql, f"Expected dashboard data-quality column fragment: {column}"


def test_migration_015_grants_select_on_new_views() -> None:
    sql = _sql()
    assert (
        "grant  select on latest_company_data_quality_snapshots to authenticated, service_role;"
        in sql
    )
    assert (
        "grant  select on dashboard_watchlist_latest to authenticated, service_role;"
        in sql
    )


def test_migration_015_uses_sanitized_summary_fields_only() -> None:
    sql = _sql()
    forbidden_fragments = [
        "price_divergence_pct",
        "price_reference_provider",
        "price_comparison_provider",
        "price_comparison_date",
        "details->'price_validation'->>'divergence_pct'",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in sql, (
            "Dashboard view should not expose raw or overly detailed provider values: "
            f"{fragment}"
        )
