"""Unit tests for Phase 9B repository functions.

Tests cover:
  - list_companies_by_ticker
  - get_company_by_ticker_exchange
  - create_company
  - get_watchlist_membership
  - create_watchlist_membership
  - list_pending_watchlist_add_requests
  - approve_watchlist_add_request
  - reject_watchlist_add_request
  - fail_watchlist_add_request
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from investment_app.db import repositories as repo


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_select_client(data: list[dict[str, Any]]) -> MagicMock:
    """Client where .table().select()...execute() returns *data*."""
    response = MagicMock()
    response.data = data
    chain = MagicMock()
    chain.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = response
    chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = response
    chain.select.return_value.eq.return_value.execute.return_value = response
    chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = response
    mock = MagicMock()
    mock.table.return_value = chain
    return mock


def _make_insert_client(returned_row: dict[str, Any]) -> MagicMock:
    """Client where .table().insert().execute() returns *returned_row*."""
    response = MagicMock()
    response.data = [returned_row]
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value = response
    return mock


def _make_update_client(returned_row: dict[str, Any] | None) -> MagicMock:
    """Client where .table().update()...execute() returns *returned_row*."""
    response = MagicMock()
    response.data = [returned_row] if returned_row else []
    mock = MagicMock()
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = response
    return mock


# ── list_companies_by_ticker ──────────────────────────────────────────────────


def test_list_companies_by_ticker_returns_all_matches() -> None:
    rows = [
        {"id": "c1", "ticker": "MSFT", "exchange": "NASDAQ"},
        {"id": "c2", "ticker": "MSFT", "exchange": "LSE"},
    ]
    response = MagicMock()
    response.data = rows
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = response

    result = repo.list_companies_by_ticker("MSFT", client=mock)

    assert len(result) == 2
    assert result[0]["ticker"] == "MSFT"


def test_list_companies_by_ticker_returns_empty_when_none() -> None:
    response = MagicMock()
    response.data = []
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = response

    result = repo.list_companies_by_ticker("ZZZZ", client=mock)

    assert result == []


def test_list_companies_by_ticker_uppercases_input() -> None:
    response = MagicMock()
    response.data = [{"id": "c1", "ticker": "AAPL"}]
    mock = MagicMock()
    chain = mock.table.return_value.select.return_value.eq
    chain.return_value.execute.return_value = response

    repo.list_companies_by_ticker("aapl", client=mock)

    chain.assert_called_once_with("ticker", "AAPL")


# ── get_company_by_ticker_exchange ────────────────────────────────────────────


def test_get_company_by_ticker_exchange_exact_match() -> None:
    company = {"id": "c1", "ticker": "AAPL", "exchange": "NASDAQ"}
    response = MagicMock()
    response.data = [company]
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = response

    result = repo.get_company_by_ticker_exchange("AAPL", "NASDAQ", client=mock)

    assert result is not None
    assert result["exchange"] == "NASDAQ"


def test_get_company_by_ticker_exchange_no_exchange_falls_back() -> None:
    company = {"id": "c1", "ticker": "AAPL", "exchange": "NASDAQ"}
    response = MagicMock()
    response.data = [company]
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = response

    result = repo.get_company_by_ticker_exchange("AAPL", None, client=mock)

    assert result is not None
    assert result["ticker"] == "AAPL"


def test_get_company_by_ticker_exchange_returns_none_when_not_found() -> None:
    response = MagicMock()
    response.data = []
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = response

    result = repo.get_company_by_ticker_exchange("ZZZZ", "NYSE", client=mock)

    assert result is None


# ── create_company ────────────────────────────────────────────────────────────


def test_create_company_inserts_and_returns_row() -> None:
    inserted = {"id": "new-c1", "ticker": "NVDA", "name": "NVIDIA Corp", "active": True}
    response = MagicMock()
    response.data = [inserted]
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value = response

    result = repo.create_company("nvda", "NVIDIA Corp", exchange="NASDAQ", client=mock)

    assert result["id"] == "new-c1"
    assert result["ticker"] == "NVDA"


def test_create_company_allows_null_cik() -> None:
    inserted = {"id": "c1", "ticker": "XYZ", "cik": None, "active": True}
    response = MagicMock()
    response.data = [inserted]
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value = response

    result = repo.create_company("xyz", "XYZ Corp", cik=None, client=mock)

    assert result["cik"] is None
    # Verify cik was NOT included in the insert payload.
    call_args = mock.table.return_value.insert.call_args[0][0]
    assert "cik" not in call_args


def test_create_company_uppercases_ticker() -> None:
    response = MagicMock()
    response.data = [{"id": "c1", "ticker": "MSFT"}]
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value = response

    repo.create_company("msft", "Microsoft", client=mock)

    payload = mock.table.return_value.insert.call_args[0][0]
    assert payload["ticker"] == "MSFT"


# ── get_watchlist_membership ──────────────────────────────────────────────────


def test_get_watchlist_membership_returns_row_when_found() -> None:
    wc_row = {"id": "wc1", "watchlist_id": "wl1", "company_id": "c1", "active": True}
    response = MagicMock()
    response.data = [wc_row]
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = response

    result = repo.get_watchlist_membership("wl1", "c1", client=mock)

    assert result is not None
    assert result["id"] == "wc1"


def test_get_watchlist_membership_returns_none_when_absent() -> None:
    response = MagicMock()
    response.data = []
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = response

    result = repo.get_watchlist_membership("wl1", "c-missing", client=mock)

    assert result is None


# ── create_watchlist_membership ───────────────────────────────────────────────


def test_create_watchlist_membership_inserts_active_row() -> None:
    new_row = {"id": "wc2", "watchlist_id": "wl1", "company_id": "c1", "active": True}
    response = MagicMock()
    response.data = [new_row]
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value = response

    result = repo.create_watchlist_membership("wl1", "c1", client=mock)

    assert result["active"] is True
    payload = mock.table.return_value.insert.call_args[0][0]
    assert payload["active"] is True
    assert payload["watchlist_id"] == "wl1"
    assert payload["company_id"] == "c1"


# ── list_pending_watchlist_add_requests ───────────────────────────────────────


def test_list_pending_add_requests_returns_pending_rows() -> None:
    pending = [
        {"id": "req1", "status": "pending", "requested_ticker": "AAPL"},
        {"id": "req2", "status": "pending", "requested_ticker": "TSLA"},
    ]
    response = MagicMock()
    response.data = pending
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = response

    result = repo.list_pending_watchlist_add_requests(client=mock)

    assert len(result) == 2
    assert all(r["status"] == "pending" for r in result)


def test_list_pending_add_requests_empty_when_none() -> None:
    response = MagicMock()
    response.data = []
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = response

    result = repo.list_pending_watchlist_add_requests(client=mock)

    assert result == []


# ── approve_watchlist_add_request ─────────────────────────────────────────────


def test_approve_add_request_sets_approved_status() -> None:
    updated = {"id": "req1", "status": "approved", "company_id": "c1"}
    mock = _make_update_client(updated)

    result = repo.approve_watchlist_add_request("req1", "c1", client=mock)

    assert result is not None
    assert result["status"] == "approved"
    payload = mock.table.return_value.update.call_args[0][0]
    assert payload["status"] == "approved"
    assert payload["company_id"] == "c1"
    assert "processed_at" in payload


# ── reject_watchlist_add_request ──────────────────────────────────────────────


def test_reject_add_request_sets_rejected_status() -> None:
    updated = {"id": "req1", "status": "rejected", "error_code": "invalid_ticker"}
    mock = _make_update_client(updated)

    result = repo.reject_watchlist_add_request(
        "req1", "invalid_ticker", "Not found.", client=mock
    )

    assert result is not None
    payload = mock.table.return_value.update.call_args[0][0]
    assert payload["status"] == "rejected"
    assert payload["error_code"] == "invalid_ticker"
    assert payload["error_message"] == "Not found."
    assert "processed_at" in payload


# ── fail_watchlist_add_request ────────────────────────────────────────────────


def test_fail_add_request_sets_failed_status() -> None:
    updated = {"id": "req1", "status": "failed", "error_code": "provider_unavailable"}
    mock = _make_update_client(updated)

    result = repo.fail_watchlist_add_request(
        "req1", "provider_unavailable", "Provider down.", client=mock
    )

    assert result is not None
    payload = mock.table.return_value.update.call_args[0][0]
    assert payload["status"] == "failed"
    assert payload["error_code"] == "provider_unavailable"
    assert "processed_at" in payload
