"""Static SQL contract tests for Phase 12F.2 signal validation segmentations."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "025_signal_backtest_segmentations.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_025_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/025_signal_backtest_segmentations.sql"


def test_creates_all_read_only_segmentation_views() -> None:
    sql = _sql()
    for view_name in (
        "backtest_signal_by_readiness",
        "backtest_signal_by_data_quality",
        "backtest_signal_by_sector",
        "backtest_signal_stability",
    ):
        assert f"create view {view_name}" in sql
    assert sql.count("security_invoker = true") >= 4


def test_segment_views_use_only_persisted_signal_backtest_observations() -> None:
    sql = _sql()
    assert "from signal_backtest_observations" in sql
    assert "from signal_runs" not in sql
    assert "latest_signal_runs" not in sql
    assert "latest_price_eod" not in sql
    assert "analysis_readiness_latest" not in sql
    assert "latest_company_data_quality_snapshots" not in sql


def test_stability_view_is_derived_from_chronological_signal_transitions_only() -> None:
    sql = _sql()
    assert "lead(final_signal) over" in sql
    assert "lead(signal_date) over" in sql
    assert "partition by company_id" in sql
    assert "order by signal_date, signal_run_id" in sql
    assert "flip_count" in sql
    assert "flip_rate" in sql
    assert "stability_pct" in sql
    assert "average_days_to_next_signal" in sql


def test_segment_views_expose_requested_descriptive_metrics() -> None:
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
        "coalesce(readiness_status_at_signal, 'unknown')",
        "coalesce(data_quality_status_at_signal, 'unknown')",
        "coalesce(sector_at_signal, 'unknown')",
    ]
    for fragment in expected_fragments:
        assert fragment in sql, f"Expected segmentation fragment: {fragment}"
