"""Static SQL contract tests for Phase 12F.4 interpretation summary."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "026_signal_backtest_interpretation_summary.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_026_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/026_signal_backtest_interpretation_summary.sql"


def test_creates_read_only_interpretation_summary_view() -> None:
    sql = _sql()
    assert "create view signal_backtest_interpretation_summary" in sql
    assert "security_invoker = true" in sql
    assert "grant select on signal_backtest_interpretation_summary to authenticated, service_role;" in sql


def test_view_exposes_requested_fields() -> None:
    sql = _sql()
    for field in (
        "total_observations",
        "evaluatable_observations",
        "historical_coverage_pct",
        "earliest_signal_date",
        "latest_signal_date",
        "signal_history_days",
        "dataset_maturity",
    ):
        assert field in sql, f"Expected field: {field}"


def test_view_uses_only_signal_backtest_observations() -> None:
    sql = _sql()
    assert "from signal_backtest_observations" in sql
    assert "from signal_runs" not in sql
    assert "from price_eod" not in sql
    assert "from valuation_runs" not in sql
    assert "from company_data_quality_snapshots" not in sql


def test_dataset_maturity_scoring_cases_exist() -> None:
    sql = _sql()
    assert "then 'high'" in sql
    assert "then 'low'" in sql
    assert "else 'medium'" in sql
    assert "total_observations >= 300" in sql
    assert "historical_coverage_pct >= 0.75" in sql
    assert "total_observations < 100" in sql
    assert "historical_coverage_pct < 0.50".lower() in sql
