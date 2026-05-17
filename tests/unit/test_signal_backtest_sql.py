"""Static SQL contract tests for Phase 12F.1 signal validation foundation."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "024_signal_backtest_observations.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_024_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/024_signal_backtest_observations.sql"


def test_creates_signal_backtest_observations_table() -> None:
    sql = _sql()
    assert "create table if not exists signal_backtest_observations" in sql
    expected_fields = [
        "signal_run_id",
        "company_id",
        "signal_date",
        "model_version",
        "final_signal",
        "p_buy",
        "p_buy_adjusted",
        "p_sell",
        "signal_price",
        "signal_price_currency",
        "readiness_status_at_signal",
        "data_quality_status_at_signal",
        "sector_at_signal",
        "market_cap_at_signal",
        "valuation_mos_at_signal",
        "valuation_uncertainty_category_at_signal",
        "return_30d",
        "return_90d",
        "return_180d",
        "return_365d",
        "price_30d",
        "price_90d",
        "price_180d",
        "price_365d",
        "price_date_30d",
        "price_date_90d",
        "price_date_180d",
        "price_date_365d",
        "has_price_30d",
        "has_price_90d",
        "has_price_180d",
        "has_price_365d",
        "coverage_gap_30d",
        "coverage_gap_90d",
        "coverage_gap_180d",
        "coverage_gap_365d",
    ]
    for field in expected_fields:
        assert field in sql, f"Expected field: {field}"


def test_table_is_keyed_by_signal_run_id_and_read_only_for_authenticated() -> None:
    sql = _sql()
    assert "signal_run_id                               uuid primary key" in sql
    assert "references signal_runs(id) on delete cascade" in sql
    assert "grant select on signal_backtest_observations to authenticated;" in sql
    assert (
        "grant select, insert, update, delete on signal_backtest_observations to service_role;"
        in sql
    )
    assert "grant insert on signal_backtest_observations to authenticated" not in sql


def test_creates_read_only_summary_views() -> None:
    sql = _sql()
    assert "create view signal_backtest_summary_by_bucket" in sql
    assert "create view signal_backtest_summary_by_horizon" in sql
    assert sql.count("security_invoker = true") >= 2
    assert "grant select on signal_backtest_summary_by_bucket to authenticated, service_role;" in sql
    assert "grant select on signal_backtest_summary_by_horizon to authenticated, service_role;" in sql


def test_summary_views_expose_requested_metrics() -> None:
    sql = _sql()
    expected_fragments = [
        "observation_count",
        "covered_observation_count",
        "average_return",
        "median_return",
        "hit_rate",
        "coverage_pct",
        "horizon_days",
        "final_signal",
    ]
    for fragment in expected_fragments:
        assert fragment in sql, f"Expected summary fragment: {fragment}"
