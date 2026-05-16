"""Static SQL contract tests for Phase 12E.1 portfolio dashboard views."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "022_portfolio_dashboard_views.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_022_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/022_portfolio_dashboard_views.sql"


def test_creates_both_portfolio_views_with_security_invoker() -> None:
    sql = _sql()
    assert "create view dashboard_portfolio_positions" in sql
    assert "create view dashboard_portfolio_summary" in sql
    assert sql.count("security_invoker = true") >= 2


def test_positions_view_joins_only_existing_persisted_sources() -> None:
    sql = _sql()
    expected_fragments = [
        "from dashboard_positions_latest pos",
        "join companies c on c.id = pos.company_id",
        "left join position_entry_profiles profile on profile.position_id = pos.id",
        "from position_review_alerts pra",
    ]
    for fragment in expected_fragments:
        assert fragment in sql, f"Expected fragment: {fragment}"
    assert "fx_rates" not in sql
    assert "dashboard_watchlist_latest" not in sql


def test_summary_metrics_and_exposure_fields_exist() -> None:
    sql = _sql()
    expected_fragments = [
        "active_position_count",
        "closed_position_count",
        "active_positions_with_price",
        "active_positions_missing_price",
        "active_positions_currency_mismatch",
        "computable_total_cost_basis",
        "computable_total_market_value",
        "computable_total_unrealized_gain_loss",
        "computable_total_unrealized_return_pct",
        "open_review_alert_count",
        "critical_data_quality_count",
        "positions_by_signal",
        "positions_by_thesis_confidence",
        "company_concentration",
        "sector_exposure",
        "geography_exposure",
    ]
    for fragment in expected_fragments:
        assert fragment in sql, f"Expected summary fragment: {fragment}"


def test_exclusion_rules_are_explicit_for_missing_price_and_currency_mismatch() -> None:
    sql = _sql()
    assert "end as missing_current_price" in sql
    assert "end as currency_mismatch" in sql
    assert "end as value_computable" in sql
    assert "end as missing_current_price" in sql
    assert "where value_computable" in sql
    assert "count(*) filter (where missing_current_price)" in sql
    assert "count(*) filter (where currency_mismatch)" in sql


def test_portfolio_views_are_read_only() -> None:
    sql = _sql()
    assert "grant select on dashboard_portfolio_positions to authenticated, service_role;" in sql
    assert "grant select on dashboard_portfolio_summary to authenticated, service_role;" in sql
    assert "grant insert on dashboard_portfolio_positions" not in sql
    assert "grant update on dashboard_portfolio_positions" not in sql
    assert "grant delete on dashboard_portfolio_positions" not in sql
    assert "grant insert on dashboard_portfolio_summary" not in sql
