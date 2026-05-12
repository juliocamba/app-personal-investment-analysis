"""Unit tests for Phase 9A watchlist repository functions.

Tests cover:
  - list_watchlist_active_companies
  - soft_remove_watchlist_company
  - reactivate_watchlist_company
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from investment_app.db import repositories as repo


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_two_table_client(
    wc_data: list[dict[str, Any]],
    company_data: list[dict[str, Any]],
) -> MagicMock:
    """Return a mock client that returns different data for different table names.

    - ``watchlist_companies`` table: SELECT → *wc_data*
    - ``companies`` table:          SELECT → *company_data*

    Supports the two-query pattern used by ``list_watchlist_active_companies``.
    """
    # watchlist_companies mock: .select().eq().execute()
    wc_response = MagicMock()
    wc_response.data = wc_data
    wc_chain = MagicMock()
    wc_chain.select.return_value.eq.return_value.execute.return_value = wc_response

    # companies mock: .select().in_().execute()
    company_response = MagicMock()
    company_response.data = company_data
    company_chain = MagicMock()
    company_chain.select.return_value.in_.return_value.execute.return_value = (
        company_response
    )

    mock = MagicMock()

    def _table_side_effect(name: str) -> MagicMock:
        if name == "watchlist_companies":
            return wc_chain
        if name == "companies":
            return company_chain
        return MagicMock()

    mock.table.side_effect = _table_side_effect
    return mock


def _make_update_client(returned_row: dict[str, Any] | None) -> MagicMock:
    """Return a mock client suitable for UPDATE … .eq() calls on watchlist_companies."""
    response = MagicMock()
    response.data = [returned_row] if returned_row is not None else []

    mock = MagicMock()
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        response
    )
    return mock


# ── list_watchlist_active_companies ───────────────────────────────────────────


def test_list_watchlist_active_companies_returns_companies() -> None:
    """Returns company rows corresponding to active memberships."""
    wc_data = [{"company_id": "cid-1"}, {"company_id": "cid-2"}]
    company_data = [
        {"id": "cid-1", "ticker": "AAPL"},
        {"id": "cid-2", "ticker": "MSFT"},
    ]
    client = _make_two_table_client(wc_data, company_data)

    result = repo.list_watchlist_active_companies(client=client)

    assert result == company_data


def test_list_watchlist_active_companies_empty_when_no_active_memberships() -> None:
    """Returns an empty list when watchlist_companies has no active rows."""
    client = _make_two_table_client(wc_data=[], company_data=[])

    result = repo.list_watchlist_active_companies(client=client)

    assert result == []
    # Should NOT query companies table when wc_data is empty.
    companies_chain = client.table("companies")
    companies_chain.select.assert_not_called()


def test_list_watchlist_active_companies_deduplicates_company_ids() -> None:
    """Deduplicates company_ids when the same company appears in multiple watchlists."""
    # Same company_id appears twice (e.g., added to two watchlists).
    wc_data = [{"company_id": "cid-1"}, {"company_id": "cid-1"}]
    company_data = [{"id": "cid-1", "ticker": "AAPL"}]

    # Use a fresh client so we can inspect the in_() call.
    wc_response = MagicMock()
    wc_response.data = wc_data
    wc_chain = MagicMock()
    wc_chain.select.return_value.eq.return_value.execute.return_value = wc_response

    company_response = MagicMock()
    company_response.data = company_data
    company_chain = MagicMock()
    company_chain.select.return_value.in_.return_value.execute.return_value = (
        company_response
    )

    mock = MagicMock()

    def _table_side_effect(name: str) -> MagicMock:
        return wc_chain if name == "watchlist_companies" else company_chain

    mock.table.side_effect = _table_side_effect

    result = repo.list_watchlist_active_companies(client=mock)

    # Only one unique company_id should be passed to .in_()
    in_call_args = company_chain.select.return_value.in_.call_args
    passed_ids = in_call_args[0][1]  # positional arg: list of IDs
    assert len(passed_ids) == 1
    assert "cid-1" in passed_ids
    assert result == company_data


def test_list_watchlist_active_companies_filters_active_flag() -> None:
    """Queries watchlist_companies with active = True."""
    wc_response = MagicMock()
    wc_response.data = []
    wc_chain = MagicMock()
    wc_chain.select.return_value.eq.return_value.execute.return_value = wc_response

    mock = MagicMock()
    mock.table.side_effect = lambda name: wc_chain if name == "watchlist_companies" else MagicMock()

    repo.list_watchlist_active_companies(client=mock)

    # Verify that eq("active", True) was called on the watchlist_companies query.
    wc_chain.select.return_value.eq.assert_called_once_with("active", True)


# ── soft_remove_watchlist_company ─────────────────────────────────────────────


def test_soft_remove_watchlist_company_calls_update_correctly() -> None:
    """Sets active = False and removed_at on the membership row."""
    membership_id = "wc-abc-123"
    returned_row = {"id": membership_id, "active": False, "removed_at": "2025-01-01T00:00:00"}
    client = _make_update_client(returned_row)

    with patch("investment_app.db.repositories.utc_now") as mock_utc:
        from datetime import datetime, timezone
        mock_utc.return_value = datetime(2025, 1, 1, tzinfo=timezone.utc)

        result = repo.soft_remove_watchlist_company(membership_id, client=client)

    assert result is not None
    assert result["active"] is False

    # Verify .update() was called with active=False and a removed_at value.
    update_call_kwargs = client.table.return_value.update.call_args[0][0]
    assert update_call_kwargs["active"] is False
    assert "removed_at" in update_call_kwargs
    assert update_call_kwargs["removed_at"] is not None

    # Verify .eq("id", membership_id) was called.
    client.table.return_value.update.return_value.eq.assert_called_once_with(
        "id", membership_id
    )


def test_soft_remove_watchlist_company_returns_none_when_no_data() -> None:
    """Returns None when Supabase returns no rows (e.g., wrong membership ID)."""
    client = _make_update_client(returned_row=None)

    result = repo.soft_remove_watchlist_company("nonexistent-id", client=client)

    assert result is None


def test_soft_remove_does_not_delete_company() -> None:
    """soft_remove must NOT call .delete() on companies or any other table."""
    client = _make_update_client({"id": "wc-1", "active": False, "removed_at": "2025-01-01"})

    with patch("investment_app.db.repositories.utc_now"):
        repo.soft_remove_watchlist_company("wc-1", client=client)

    # The mock client's .delete method must never have been called.
    client.table.return_value.delete.assert_not_called()


# ── reactivate_watchlist_company ──────────────────────────────────────────────


def test_reactivate_watchlist_company_calls_update_correctly() -> None:
    """Sets active = True and removed_at = None on the membership row."""
    membership_id = "wc-xyz-456"
    returned_row = {"id": membership_id, "active": True, "removed_at": None}
    client = _make_update_client(returned_row)

    result = repo.reactivate_watchlist_company(membership_id, client=client)

    assert result is not None
    assert result["active"] is True
    assert result["removed_at"] is None

    # Verify .update() was called with active=True and removed_at=None.
    update_call_kwargs = client.table.return_value.update.call_args[0][0]
    assert update_call_kwargs["active"] is True
    assert update_call_kwargs["removed_at"] is None

    # Verify .eq("id", membership_id) was called.
    client.table.return_value.update.return_value.eq.assert_called_once_with(
        "id", membership_id
    )


def test_reactivate_watchlist_company_returns_none_when_no_data() -> None:
    """Returns None when Supabase returns no rows."""
    client = _make_update_client(returned_row=None)

    result = repo.reactivate_watchlist_company("nonexistent-id", client=client)

    assert result is None
