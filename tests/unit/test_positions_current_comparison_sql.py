"""Static SQL contract tests for Phase 12C.2 positions comparison fields."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "019_positions_current_comparison_fields.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_019_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/019_positions_current_comparison_fields.sql"


def test_recreates_dashboard_positions_latest_without_watchlist_coupling() -> None:
    sql = _sql()
    assert "create view dashboard_positions_latest" in sql
    assert "security_invoker = true" in sql
    assert "join dashboard_watchlist_latest" not in sql


def test_view_joins_only_existing_persisted_position_sources() -> None:
    sql = _sql()
    expected_joins = [
        "from positions pos",
        "join companies c on c.id = pos.company_id",
        "left join latest_price_eod p on p.company_id = pos.company_id",
        "left join latest_signal_runs signal_snap on signal_snap.company_id = pos.company_id",
        "left join analysis_readiness_latest readiness_snap on readiness_snap.company_id = pos.company_id",
        "left join latest_company_data_quality_snapshots dq_snap on dq_snap.company_id = pos.company_id",
        "left join latest_qualitative_scores quality_snap on quality_snap.company_id = pos.company_id",
        "from latest_valuation_runs",
    ]
    for fragment in expected_joins:
        assert fragment in sql, f"Expected view fragment: {fragment}"


def test_view_exposes_expected_current_comparison_columns() -> None:
    sql = _sql()
    expected_fragments = [
        "signal_snap.final_signal as current_signal",
        "readiness_snap.readiness_status as current_readiness_status",
        "dq_snap.data_quality_status as current_data_quality_status",
        "quality_snap.final_quality_score as current_quality_score",
        "valuation_snap.iv_p25 as current_valuation_low",
        "valuation_snap.iv_p50 as current_valuation_mid",
        "valuation_snap.iv_p75 as current_valuation_high",
        "valuation_snap.margin_of_safety_conservative as current_margin_of_safety",
        "valuation_snap.uncertainty_category as current_uncertainty_category",
    ]
    for fragment in expected_fragments:
        assert fragment in sql, f"Expected current comparison column: {fragment}"


def test_existing_price_display_rules_remain_null_safe() -> None:
    sql = _sql()
    assert "when pos.status = 'active'" in sql
    assert "and p.close is not null" in sql
    assert "and p.currency is not null" in sql
    assert "and p.currency = pos.currency" in sql


def test_view_grants_remain_read_only() -> None:
    sql = _sql()
    assert (
        "grant select on dashboard_positions_latest to authenticated, service_role;"
        in sql
    )
    assert "grant insert on dashboard_positions_latest" not in sql
    assert "grant update on dashboard_positions_latest" not in sql
    assert "grant delete on dashboard_positions_latest" not in sql
