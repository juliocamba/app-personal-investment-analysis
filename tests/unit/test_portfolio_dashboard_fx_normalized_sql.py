"""Static SQL contract tests for Phase 12E.2 FX-normalized portfolio views."""
from __future__ import annotations

from pathlib import Path


SQL_PATH = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "023_portfolio_dashboard_fx_normalized_views.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_migration_023_exists() -> None:
    assert SQL_PATH.exists(), "Expected sql/023_portfolio_dashboard_fx_normalized_views.sql"


def test_creates_both_fx_views_with_security_invoker() -> None:
    sql = _sql()
    assert "create view dashboard_portfolio_positions_fx_eur" in sql
    assert "create view dashboard_portfolio_summary_fx_eur" in sql
    assert sql.count("security_invoker = true") >= 2


def test_fx_views_use_only_portfolio_positions_and_fx_rates() -> None:
    sql = _sql()
    assert "from dashboard_portfolio_positions pos" in sql
    assert "from fx_rates" in sql
    assert "from dashboard_portfolio_positions_fx_eur" in sql
    assert "dashboard_watchlist_latest" not in sql
    assert "latest_signal_runs" not in sql
    assert "position_entry_profiles" not in sql
    assert "position_review_alerts" not in sql


def test_exact_date_matching_and_eur_base_are_explicit() -> None:
    sql = _sql()
    assert "fx.rate_date = pos.price_date" in sql
    assert "base_currency = 'eur'" in sql
    assert "provider = 'ecb'" in sql


def test_same_currency_and_missing_fx_rules_are_explicit() -> None:
    sql = _sql()
    assert "pos.currency = 'eur'" in sql
    assert "pos.currency <> 'eur'" in sql
    assert "fx.rate is not null" in sql
    assert "normalized_current_value_eur is null" in sql
    assert "positions_missing_fx_rate" in sql


def test_existing_currency_mismatch_rows_are_not_normalized() -> None:
    sql = _sql()
    assert "not pos.currency_mismatch" in sql


def test_fx_views_are_read_only() -> None:
    sql = _sql()
    assert "grant select on dashboard_portfolio_positions_fx_eur to authenticated, service_role;" in sql
    assert "grant select on dashboard_portfolio_summary_fx_eur to authenticated, service_role;" in sql
    assert "grant insert on dashboard_portfolio_positions_fx_eur" not in sql
    assert "grant update on dashboard_portfolio_positions_fx_eur" not in sql
    assert "grant insert on dashboard_portfolio_summary_fx_eur" not in sql
