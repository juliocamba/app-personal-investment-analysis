"""Static SQL grant hygiene tests.

These tests parse the SQL migration files as text and assert that the intended
access-tier model is reflected in the grant/revoke statements.  No database
connection is required.

The tests act as a regression guard: they will fail if a future migration
accidentally widens authenticated or anon access on sensitive tables, or drops
the service_role grants that the backend pipeline depends on.
"""
from __future__ import annotations

import re
from pathlib import Path

# ── Helpers ───────────────────────────────────────────────────────────────────

SQL_DIR = Path(__file__).parent.parent.parent / "sql"

MIGRATION_011 = SQL_DIR / "011_explicit_grants_and_rls_hardening.sql"


def _sql_of(*filenames: str) -> str:
    """Return the lower-cased concatenated SQL content of the given files."""
    parts: list[str] = []
    for fname in filenames:
        path = SQL_DIR / fname
        parts.append(path.read_text(encoding="utf-8").lower())
    return "\n".join(parts)


def _combined_sql() -> str:
    """Lower-cased SQL of all migrations combined."""
    return _sql_of(*[p.name for p in sorted(SQL_DIR.glob("0*.sql"))])


def _has_grant(sql: str, table: str, role: str, privilege: str) -> bool:
    """Return True if a GRANT <privilege> ON <table> TO <role> statement exists."""
    pattern = rf"grant\s+[^;]*\b{re.escape(privilege)}\b[^;]*\bon\s+{re.escape(table)}\b[^;]*\bto\s+[^;]*\b{re.escape(role)}\b"
    return bool(re.search(pattern, sql, re.IGNORECASE | re.DOTALL))


def _has_any_grant_to_role(sql: str, table: str, role: str) -> bool:
    """Return True if ANY grant on the table to the role is found."""
    pattern = rf"grant\s+[^;]+\bon\s+{re.escape(table)}\b[^;]*\bto\s+[^;]*\b{re.escape(role)}\b"
    return bool(re.search(pattern, sql, re.IGNORECASE | re.DOTALL))


# ── Migration existence ───────────────────────────────────────────────────────


def test_migration_011_exists() -> None:
    assert MIGRATION_011.exists(), (
        "Migration 011_explicit_grants_and_rls_hardening.sql not found in sql/"
    )


def test_all_expected_migrations_exist() -> None:
    expected = [f"0{n:02d}" for n in range(1, 12)]
    present = {p.name[:3] for p in SQL_DIR.glob("0*.sql")}
    for prefix in expected:
        assert prefix in present, f"Missing migration with prefix {prefix}"


# ── service_role write grants ─────────────────────────────────────────────────


def test_service_role_insert_all_write_tables() -> None:
    """Migration 011 must grant INSERT on every table the backend writes to."""
    sql = MIGRATION_011.read_text(encoding="utf-8").lower()

    write_tables = [
        # backend-only (5)
        "pipeline_runs",
        "pipeline_run_events",
        "provider_requests",
        "raw_provider_payloads",
        "statements_raw",
        # backend-rw, authenticated read-only (12)
        "companies",
        "price_eod",
        "fx_rates",
        "filings_index",
        "statements_norm",
        "ratios_factors",
        "qualitative_scores",
        "valuation_runs",
        "signal_runs",
        "news_events",
        "corporate_actions",
        "company_analysis_readiness",
        # user-writable with backend authority (6)
        "app_users",
        "watchlists",
        "watchlist_companies",
        "watchlist_add_requests",
        "alert_rules",
        "alert_history",
    ]

    missing: list[str] = []
    for table in write_tables:
        if not _has_grant(sql, table, "service_role", "insert"):
            missing.append(table)

    assert not missing, (
        f"Migration 011 is missing service_role INSERT grant for: {missing}"
    )


# ── Backend-only table isolation ──────────────────────────────────────────────


def test_no_authenticated_select_on_pipeline_run_events() -> None:
    """pipeline_run_events must never be readable by authenticated."""
    sql = _combined_sql()
    assert not _has_grant(sql, "pipeline_run_events", "authenticated", "select"), (
        "Found GRANT SELECT on pipeline_run_events TO authenticated in migrations — "
        "this table must remain backend-only."
    )


def test_no_authenticated_select_on_raw_provider_payloads() -> None:
    """raw_provider_payloads must never be readable by authenticated."""
    sql = _combined_sql()
    assert not _has_grant(sql, "raw_provider_payloads", "authenticated", "select"), (
        "Found GRANT SELECT on raw_provider_payloads TO authenticated — "
        "this table must remain backend-only."
    )


def test_no_authenticated_insert_on_pipeline_runs() -> None:
    """pipeline_runs must never be writable by authenticated."""
    sql = _combined_sql()
    assert not _has_grant(sql, "pipeline_runs", "authenticated", "insert"), (
        "Found GRANT INSERT on pipeline_runs TO authenticated — backend-only."
    )


def test_no_authenticated_insert_on_provider_requests() -> None:
    sql = _combined_sql()
    assert not _has_grant(sql, "provider_requests", "authenticated", "insert"), (
        "Found GRANT INSERT on provider_requests TO authenticated — backend-only."
    )


# ── company_analysis_readiness write isolation ────────────────────────────────


def test_no_authenticated_insert_on_company_analysis_readiness() -> None:
    """Authenticated users must not be able to write readiness snapshots."""
    sql = _combined_sql()
    assert not _has_grant(
        sql, "company_analysis_readiness", "authenticated", "insert"
    ), (
        "Found GRANT INSERT on company_analysis_readiness TO authenticated — "
        "only service_role may write readiness snapshots."
    )


def test_no_authenticated_update_on_company_analysis_readiness() -> None:
    sql = _combined_sql()
    assert not _has_grant(
        sql, "company_analysis_readiness", "authenticated", "update"
    ), (
        "Found GRANT UPDATE on company_analysis_readiness TO authenticated."
    )


def test_authenticated_select_on_company_analysis_readiness_exists() -> None:
    """Migration 010 or 011 must grant authenticated SELECT on this table."""
    sql = _combined_sql()
    assert _has_grant(sql, "company_analysis_readiness", "authenticated", "select"), (
        "No GRANT SELECT on company_analysis_readiness TO authenticated found — "
        "the dashboard cannot display readiness data."
    )


# ── watchlist_add_requests column-scoped grants ───────────────────────────────


def test_watchlist_add_requests_column_scoped_insert() -> None:
    """The INSERT grant on watchlist_add_requests must be column-scoped."""
    sql = _combined_sql()
    # Column-scoped INSERT looks like: GRANT INSERT(col, ...) ON table TO role
    pattern = r"grant\s+insert\s*\([^)]+\)\s+on\s+watchlist_add_requests\b"
    assert re.search(pattern, sql, re.IGNORECASE | re.DOTALL), (
        "Expected column-scoped INSERT grant on watchlist_add_requests — "
        "full-table INSERT must not be granted to authenticated."
    )


def test_no_full_table_insert_authenticated_on_watchlist_add_requests() -> None:
    """There must be no GRANT INSERT (full table) on watchlist_add_requests to authenticated."""
    sql = _combined_sql()
    # A full-table INSERT grant would look like: GRANT SELECT, INSERT, UPDATE ... ON watchlist_add_requests TO authenticated
    # or: GRANT INSERT ON watchlist_add_requests TO authenticated
    # The column-scoped form has parentheses after INSERT; we check the unscoped form is absent.
    pattern = r"grant\s+(?:select\s*,\s*)?insert\s+on\s+watchlist_add_requests\b[^;]*to[^;]*\bauthenticated\b"
    assert not re.search(pattern, sql, re.IGNORECASE | re.DOTALL), (
        "Found an unscoped GRANT INSERT ON watchlist_add_requests TO authenticated — "
        "only column-limited INSERT is permitted."
    )


# ── Dashboard view grants ─────────────────────────────────────────────────────


def test_dashboard_watchlist_latest_auth_select_exists() -> None:
    sql = _combined_sql()
    assert _has_any_grant_to_role(sql, "dashboard_watchlist_latest", "authenticated"), (
        "No grant on dashboard_watchlist_latest to authenticated found."
    )


def test_analysis_readiness_latest_auth_select_exists() -> None:
    sql = _combined_sql()
    assert _has_any_grant_to_role(sql, "analysis_readiness_latest", "authenticated"), (
        "No grant on analysis_readiness_latest to authenticated found."
    )


def test_dashboard_views_service_role_select_in_011() -> None:
    """Migration 011 must add service_role SELECT on all dashboard views."""
    sql = MIGRATION_011.read_text(encoding="utf-8").lower()

    dashboard_views = [
        "dashboard_watchlist_latest",
        "dashboard_watchlist_inactive",
        "analysis_readiness_latest",
        "latest_price_eod",
        "latest_ratios_factors",
        "latest_valuation_runs",
        "latest_qualitative_scores",
        "latest_signal_runs",
    ]

    missing: list[str] = []
    for view in dashboard_views:
        # service_role is granted alongside authenticated in a single statement
        # e.g. "grant select on dashboard_watchlist_latest to authenticated, service_role"
        if "service_role" not in sql or view not in sql:
            missing.append(view)
        else:
            pattern = rf"grant\s+select\s+on\s+{re.escape(view)}\b[^;]*service_role"
            if not re.search(pattern, sql, re.IGNORECASE | re.DOTALL):
                missing.append(view)

    assert not missing, (
        f"Migration 011 is missing service_role SELECT grant for views: {missing}"
    )


# ── No anon grants anywhere ───────────────────────────────────────────────────


def test_no_grant_to_anon_in_migrations() -> None:
    """No migration should grant any privilege to the anon role."""
    sql = _combined_sql()
    pattern = r"grant\s+[^;]+\bto\s+[^;]*\banon\b"
    assert not re.search(pattern, sql, re.IGNORECASE | re.DOTALL), (
        "Found a GRANT ... TO anon in one or more migrations — "
        "anon must not receive any table or view privileges."
    )


# ── Revoke statements in 011 ─────────────────────────────────────────────────


def test_011_revokes_from_authenticated_on_backend_only_tables() -> None:
    """Migration 011 must explicitly revoke from authenticated on backend-only tables."""
    sql = MIGRATION_011.read_text(encoding="utf-8").lower()

    backend_only = [
        "pipeline_runs",
        "pipeline_run_events",
        "provider_requests",
        "raw_provider_payloads",
        "statements_raw",
    ]

    missing_revoke: list[str] = []
    for table in backend_only:
        pattern = rf"revoke\s+all\s+on\s+{re.escape(table)}\b[^;]*\bauthenticated\b"
        if not re.search(pattern, sql, re.IGNORECASE | re.DOTALL):
            missing_revoke.append(table)

    assert not missing_revoke, (
        f"Migration 011 is missing REVOKE ALL FROM authenticated for: {missing_revoke}"
    )


def test_011_revokes_from_anon_on_market_data_tables() -> None:
    """Migration 011 must revoke from anon/public on market-data tables."""
    sql = MIGRATION_011.read_text(encoding="utf-8").lower()

    market_tables = [
        "companies",
        "price_eod",
        "fx_rates",
        "statements_norm",
        "ratios_factors",
    ]

    missing_revoke: list[str] = []
    for table in market_tables:
        pattern = rf"revoke\s+all\s+on\s+{re.escape(table)}\b[^;]*\banon\b"
        if not re.search(pattern, sql, re.IGNORECASE | re.DOTALL):
            missing_revoke.append(table)

    assert not missing_revoke, (
        f"Migration 011 is missing REVOKE ALL FROM anon for: {missing_revoke}"
    )
