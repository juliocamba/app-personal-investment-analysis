"""Static SQL contract tests for Phase 12G stale-readiness dashboard suppression."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "028_dashboard_stale_readiness_suppression.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_028_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/028_dashboard_stale_readiness_suppression.sql"


def test_recreates_dashboard_watchlist_latest() -> None:
    sql = _sql()
    assert "create or replace view dashboard_watchlist_latest" in sql


def test_suppresses_valuation_fields_when_can_run_valuation_false() -> None:
    sql = _sql()
    assert "when ar.can_run_valuation is false then null" in sql
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


def test_suppresses_signal_fields_when_can_run_signal_false() -> None:
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


def test_preserves_readiness_and_data_quality_lanes() -> None:
    sql = _sql()
    assert "ar.readiness_status" in sql
    assert "ar.readiness_reason_codes" in sql
    assert "coalesce(dq.data_quality_status, 'no_diagnostics')" in sql


def test_migration_028_grants_dashboard_view_select() -> None:
    sql = _sql()
    assert "grant  select on dashboard_watchlist_latest to authenticated, service_role;" in sql
