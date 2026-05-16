"""Static SQL contract tests for Phase 12B.2 positions display metrics."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "017_positions_display_metrics.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_017_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/017_positions_display_metrics.sql"


def test_creates_dashboard_positions_latest_view() -> None:
    sql = _sql()
    assert "create view dashboard_positions_latest" in sql
    assert "security_invoker = true" in sql
    assert "from positions pos" in sql
    assert "join companies c on c.id = pos.company_id" in sql
    assert "left join latest_price_eod p on p.company_id = pos.company_id" in sql


def test_view_exposes_expected_display_columns() -> None:
    sql = _sql()
    expected_fragments = [
        "p.close as current_price",
        "p.currency as price_currency",
        "end as cost_basis",
        "end as current_value",
        "end as unrealized_gain_loss",
        "end as unrealized_return_pct",
    ]
    for fragment in expected_fragments:
        assert fragment in sql, f"Expected view fragment: {fragment}"


def test_view_applies_active_price_and_currency_match_rules() -> None:
    sql = _sql()
    assert "when pos.status = 'active'" in sql
    assert "and p.close is not null" in sql
    assert "and p.currency is not null" in sql
    assert "and p.currency = pos.currency" in sql


def test_view_grants_are_read_only() -> None:
    sql = _sql()
    assert (
        "grant select on dashboard_positions_latest to authenticated, service_role;"
        in sql
    )
    assert "grant insert on dashboard_positions_latest" not in sql
    assert "grant update on dashboard_positions_latest" not in sql
    assert "grant delete on dashboard_positions_latest" not in sql
