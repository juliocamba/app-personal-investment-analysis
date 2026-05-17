"""Static SQL contract tests for migration 027 latest_* view hardening."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "027_latest_views_security_invoker.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_027_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/027_latest_views_security_invoker.sql"


def test_recreates_all_four_views_with_security_invoker() -> None:
    sql = _sql()
    for view_name in (
        "latest_ratios_factors",
        "latest_valuation_runs",
        "latest_qualitative_scores",
        "latest_signal_runs",
    ):
        assert f"create or replace view {view_name}" in sql
    assert sql.count("security_invoker = true") >= 4


def test_preserves_expected_distinct_on_and_ordering_fragments() -> None:
    sql = _sql()
    assert "from ratios_factors" in sql
    assert "order by company_id, factor_date desc;" in sql
    assert "from valuation_runs" in sql
    assert "order by company_id, valuation_date desc, created_at desc;" in sql
    assert "from qualitative_scores" in sql
    assert "order by company_id, score_date desc, created_at desc;" in sql
    assert "from signal_runs" in sql
    assert "order by company_id, signal_date desc, created_at desc;" in sql
    assert sql.count("select distinct on (company_id)") >= 4


def test_reapplies_read_only_grants_and_revokes_anon_public() -> None:
    sql = _sql()
    assert "grant select on latest_ratios_factors to authenticated, service_role;" in sql
    assert "grant select on latest_valuation_runs to authenticated, service_role;" in sql
    assert "grant select on latest_qualitative_scores to authenticated, service_role;" in sql
    assert "grant select on latest_signal_runs to authenticated, service_role;" in sql
    assert "revoke all on latest_ratios_factors from public, anon, authenticated;" in sql
    assert "revoke all on latest_valuation_runs from public, anon, authenticated;" in sql
    assert "revoke all on latest_qualitative_scores from public, anon, authenticated;" in sql
    assert "revoke all on latest_signal_runs from public, anon, authenticated;" in sql
