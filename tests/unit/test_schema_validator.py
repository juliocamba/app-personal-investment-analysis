"""Unit tests for investment_app.db.schema_validator."""
from __future__ import annotations

from unittest.mock import MagicMock

from investment_app.db.schema_validator import REQUIRED_TABLES, validate_tables


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_client(present: list[str]) -> MagicMock:
    """Return a mock Supabase client that succeeds for *present* tables only."""

    def _table(name: str) -> MagicMock:
        builder = MagicMock()
        if name not in present:
            builder.select.return_value.limit.return_value.execute.side_effect = (
                Exception(f"relation \"{name}\" does not exist")
            )
        return builder

    mock = MagicMock()
    mock.table.side_effect = _table
    return mock


# ── validate_tables ───────────────────────────────────────────────────────────


def test_all_tables_present() -> None:
    client = _make_client(list(REQUIRED_TABLES))
    present, missing = validate_tables(client)

    assert set(present) == set(REQUIRED_TABLES)
    assert missing == []


def test_some_tables_missing() -> None:
    absent = {"pipeline_runs", "signal_runs"}
    present_tables = [t for t in REQUIRED_TABLES if t not in absent]
    client = _make_client(present_tables)

    present, missing = validate_tables(client)

    assert set(missing) == absent
    assert set(present) == set(present_tables)


def test_all_tables_missing() -> None:
    client = _make_client([])
    present, missing = validate_tables(client)

    assert present == []
    assert set(missing) == set(REQUIRED_TABLES)


def test_single_table_missing() -> None:
    absent = "ratios_factors"
    present_tables = [t for t in REQUIRED_TABLES if t != absent]
    client = _make_client(present_tables)

    present, missing = validate_tables(client)

    assert absent in missing
    assert absent not in present


def test_validate_tables_queries_correct_table_names() -> None:
    """Every table in REQUIRED_TABLES must be probed exactly once."""
    client = _make_client(list(REQUIRED_TABLES))
    validate_tables(client)

    queried = {call.args[0] for call in client.table.call_args_list}
    assert queried == set(REQUIRED_TABLES)


# ── REQUIRED_TABLES content ───────────────────────────────────────────────────


def test_required_tables_contains_all_mandatory_names() -> None:
    mandatory = {
        "companies",
        "watchlists",
        "watchlist_companies",
        "raw_provider_payloads",
        "price_eod",
        "filings_index",
        "statements_norm",
        "ratios_factors",
        "qualitative_scores",
        "valuation_runs",
        "signal_runs",
        "alert_rules",
        "alert_history",
        "pipeline_runs",
    }
    assert mandatory.issubset(set(REQUIRED_TABLES))


def test_required_tables_has_no_duplicates() -> None:
    assert len(REQUIRED_TABLES) == len(set(REQUIRED_TABLES))
