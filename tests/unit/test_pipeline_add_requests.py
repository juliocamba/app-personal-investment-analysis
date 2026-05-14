"""Unit tests for Phase 9B pipeline stage: _process_pending_add_requests.

Tests the full decision tree without live Supabase or FMP access.
Uses the module-import pattern from test_pipeline_authority.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "run_daily_pipeline.py"


def _load_pipeline_module() -> Any:
    """Import the pipeline script as a fresh module object."""
    spec = importlib.util.spec_from_file_location("pipeline_script_9b", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_fmp_profile(ticker: str, exchange: str = "NASDAQ") -> MagicMock:
    """Return a mock FMP connector that returns a valid profile for *ticker*."""
    profile = {
        "companyName": f"{ticker} Inc",
        "exchangeShortName": exchange,
        "country": "US",
        "currency": "USD",
        "sector": "Technology",
        "industry": "Software",
        "cik": "0001234567",
    }
    resp = MagicMock()
    resp.success = True
    resp.payload = [profile]
    fmp = MagicMock()
    fmp.get_profile.return_value = resp
    return fmp


def _make_fmp_empty() -> MagicMock:
    """Return a mock FMP connector that returns an empty payload (ticker not found)."""
    resp = MagicMock()
    resp.success = True
    resp.payload = []
    fmp = MagicMock()
    fmp.get_profile.return_value = resp
    return fmp


def _make_fmp_failure() -> MagicMock:
    """Return a mock FMP connector where get_profile raises an exception."""
    fmp = MagicMock()
    fmp.get_profile.side_effect = RuntimeError("Network error")
    return fmp


def _make_fmp_api_error() -> MagicMock:
    """Return a mock FMP connector where success=False."""
    resp = MagicMock()
    resp.success = False
    resp.payload = None
    fmp = MagicMock()
    fmp.get_profile.return_value = resp
    return fmp


def _make_fmp_no_cik(ticker: str) -> MagicMock:
    """Return a mock FMP connector that returns a profile with no CIK."""
    profile = {
        "companyName": f"{ticker} Corp",
        "exchangeShortName": "NYSE",
        "country": "UK",
        "currency": "GBP",
        "sector": "Finance",
        "industry": "Banking",
        "cik": None,
    }
    resp = MagicMock()
    resp.success = True
    resp.payload = [profile]
    fmp = MagicMock()
    fmp.get_profile.return_value = resp
    return fmp


def _base_repo() -> MagicMock:
    """Return a repo mock with sensible defaults for Phase 9B."""
    r = MagicMock()
    r.list_pending_watchlist_add_requests.return_value = []
    r.list_companies_by_ticker.return_value = []
    r.get_company_by_ticker_exchange.return_value = None
    r.get_watchlist_membership.return_value = None
    return r


def _metrics() -> dict[str, int]:
    return {
        "add_requests_processed": 0,
        "add_requests_approved": 0,
        "add_requests_rejected": 0,
        "add_requests_failed": 0,
    }


def _pending_request(
    req_id: str = "req-1",
    ticker: str = "AAPL",
    exchange: str | None = None,
    watchlist_id: str = "wl-1",
) -> dict[str, Any]:
    return {
        "id": req_id,
        "watchlist_id": watchlist_id,
        "requested_ticker": ticker,
        "requested_exchange": exchange,
        "status": "pending",
    }


# ── No pending requests ───────────────────────────────────────────────────────


def test_no_pending_requests_does_nothing() -> None:
    mod = _load_pipeline_module()
    repo = _base_repo()
    repo.list_pending_watchlist_add_requests.return_value = []
    m = _metrics()

    mod._process_pending_add_requests(repo, None, "run-1", m)

    repo.approve_watchlist_add_request.assert_not_called()
    repo.reject_watchlist_add_request.assert_not_called()
    repo.fail_watchlist_add_request.assert_not_called()
    assert m["add_requests_processed"] == 0


# ── Invalid ticker format ─────────────────────────────────────────────────────


def test_invalid_ticker_is_rejected() -> None:
    mod = _load_pipeline_module()
    repo = _base_repo()
    repo.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="AA PL")  # space is invalid
    ]
    m = _metrics()

    mod._process_pending_add_requests(repo, None, "run-1", m)

    repo.reject_watchlist_add_request.assert_called_once()
    args = repo.reject_watchlist_add_request.call_args[0]
    assert args[1] == "invalid_ticker"
    assert m["add_requests_rejected"] == 1
    assert m["add_requests_processed"] == 1


# ── Already active in watchlist ───────────────────────────────────────────────


def test_already_active_membership_rejects_request() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    existing_company = {"id": "c1", "ticker": "AAPL", "exchange": "NASDAQ"}
    active_membership = {"id": "wc1", "watchlist_id": "wl-1", "company_id": "c1", "active": True}
    r.list_pending_watchlist_add_requests.return_value = [_pending_request()]
    r.list_companies_by_ticker.return_value = [existing_company]
    r.get_company_by_ticker_exchange.return_value = None  # no exchange specified
    r.get_watchlist_membership.return_value = active_membership
    m = _metrics()

    mod._process_pending_add_requests(r, None, "run-1", m)

    r.reject_watchlist_add_request.assert_called_once()
    args = r.reject_watchlist_add_request.call_args[0]
    assert args[1] == "already_active"
    assert m["add_requests_rejected"] == 1


# ── Inactive membership — reactivate ─────────────────────────────────────────


def test_inactive_membership_is_reactivated_and_approved() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    existing_company = {"id": "c1", "ticker": "AAPL", "exchange": "NASDAQ"}
    inactive_membership = {"id": "wc1", "watchlist_id": "wl-1", "company_id": "c1", "active": False}
    r.list_pending_watchlist_add_requests.return_value = [_pending_request()]
    r.list_companies_by_ticker.return_value = [existing_company]
    r.get_watchlist_membership.return_value = inactive_membership
    m = _metrics()

    mod._process_pending_add_requests(r, None, "run-1", m)

    r.reactivate_watchlist_company.assert_called_once_with("wc1")
    r.approve_watchlist_add_request.assert_called_once_with("req-1", "c1")
    assert m["add_requests_approved"] == 1


# ── Existing company, no membership — create membership ──────────────────────


def test_existing_company_no_membership_creates_membership_and_approves() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    existing_company = {"id": "c1", "ticker": "MSFT", "exchange": "NASDAQ"}
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="MSFT")
    ]
    r.list_companies_by_ticker.return_value = [existing_company]
    r.get_watchlist_membership.return_value = None
    m = _metrics()

    mod._process_pending_add_requests(r, None, "run-1", m)

    r.create_watchlist_membership.assert_called_once_with("wl-1", "c1")
    r.approve_watchlist_add_request.assert_called_once_with("req-1", "c1")
    assert m["add_requests_approved"] == 1


# ── Exchange mismatch ─────────────────────────────────────────────────────────


def test_exchange_mismatch_rejects_request() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    existing_on_different_exchange = [{"id": "c1", "ticker": "AAPL", "exchange": "NASDAQ"}]
    # User requested AAPL on NYSE, but it's on NASDAQ.
    req = _pending_request(ticker="AAPL", exchange="NYSE")
    r.list_pending_watchlist_add_requests.return_value = [req]
    # get_company_by_ticker_exchange returns None (not on NYSE)
    r.get_company_by_ticker_exchange.return_value = None
    # list_companies_by_ticker returns the NASDAQ one
    r.list_companies_by_ticker.return_value = existing_on_different_exchange
    m = _metrics()

    mod._process_pending_add_requests(r, None, "run-1", m)

    r.reject_watchlist_add_request.assert_called_once()
    args = r.reject_watchlist_add_request.call_args[0]
    assert args[1] == "exchange_mismatch"
    assert m["add_requests_rejected"] == 1


# ── Ambiguous ticker (multiple exchanges, no exchange specified) ───────────────


def test_ambiguous_ticker_rejects_request() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [_pending_request(ticker="VOD")]
    r.list_companies_by_ticker.return_value = [
        {"id": "c1", "ticker": "VOD", "exchange": "NASDAQ"},
        {"id": "c2", "ticker": "VOD", "exchange": "LSE"},
    ]
    m = _metrics()

    mod._process_pending_add_requests(r, None, "run-1", m)

    r.reject_watchlist_add_request.assert_called_once()
    args = r.reject_watchlist_add_request.call_args[0]
    assert args[1] == "ambiguous_ticker"
    assert m["add_requests_rejected"] == 1


# ── Valid new ticker — creates company and membership ─────────────────────────


def test_valid_new_ticker_creates_company_and_membership() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="NVDA")
    ]
    r.list_companies_by_ticker.return_value = []  # doesn't exist yet
    r.create_company.return_value = {"id": "new-c1", "ticker": "NVDA"}
    fmp = _make_fmp_profile("NVDA")
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.create_company.assert_called_once()
    r.create_watchlist_membership.assert_called_once_with("wl-1", "new-c1")
    r.approve_watchlist_add_request.assert_called_once_with("req-1", "new-c1")
    assert m["add_requests_approved"] == 1


# ── New ticker with missing CIK ───────────────────────────────────────────────


def test_new_ticker_with_missing_cik_creates_company_with_null_cik() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="BARCY")
    ]
    r.list_companies_by_ticker.return_value = []
    r.create_company.return_value = {"id": "new-c2", "ticker": "BARCY", "cik": None}
    fmp = _make_fmp_no_cik("BARCY")
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    call_kwargs = r.create_company.call_args[1]
    assert call_kwargs.get("cik") is None
    assert m["add_requests_approved"] == 1


# ── Invalid ticker (FMP returns empty payload) ────────────────────────────────


def test_ticker_not_found_in_fmp_is_rejected() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="NOTREAL")
    ]
    r.list_companies_by_ticker.return_value = []
    fmp = _make_fmp_empty()
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.reject_watchlist_add_request.assert_called_once()
    args = r.reject_watchlist_add_request.call_args[0]
    assert args[1] == "invalid_ticker"
    assert m["add_requests_rejected"] == 1


# ── FMP technical failure ─────────────────────────────────────────────────────


def test_fmp_exception_marks_request_failed() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="TSLA")
    ]
    r.list_companies_by_ticker.return_value = []
    fmp = _make_fmp_failure()
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.fail_watchlist_add_request.assert_called_once()
    args = r.fail_watchlist_add_request.call_args[0]
    assert args[1] == "fmp_request_failed"
    assert m["add_requests_failed"] == 1


def test_fmp_api_error_marks_request_failed() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="AMD")
    ]
    r.list_companies_by_ticker.return_value = []
    fmp = _make_fmp_api_error()
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.fail_watchlist_add_request.assert_called_once()
    args = r.fail_watchlist_add_request.call_args[0]
    assert args[1] == "provider_unavailable"
    assert m["add_requests_failed"] == 1


# ── FMP not configured ────────────────────────────────────────────────────────


def test_fmp_none_marks_request_failed() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="QCOM")
    ]
    r.list_companies_by_ticker.return_value = []
    m = _metrics()

    mod._process_pending_add_requests(r, None, "run-1", m)

    r.fail_watchlist_add_request.assert_called_once()
    args = r.fail_watchlist_add_request.call_args[0]
    assert args[1] == "provider_unavailable"
    assert m["add_requests_failed"] == 1


# ── No raw provider errors in persisted messages ──────────────────────────────


def test_fmp_exception_message_is_not_persisted_raw() -> None:
    """Raw provider exception text must not be stored in error_message."""
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="TSLA")
    ]
    r.list_companies_by_ticker.return_value = []
    fmp = _make_fmp_failure()  # raises RuntimeError("Network error")
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    args = r.fail_watchlist_add_request.call_args[0]
    # The raw exception text "Network error" must not appear.
    assert "Network error" not in args[2]
    assert "RuntimeError" not in args[2]


# ── Approved request appears in active companies (same run) ───────────────────


def test_approved_request_company_included_in_same_run() -> None:
    """After _process_pending_add_requests, list_watchlist_active_companies
    will include the newly created membership because create_watchlist_membership
    was called (pipeline then re-fetches via _load_live_companies).

    This test verifies create_watchlist_membership is called so the newly
    approved company will be picked up by the subsequent active-company load.
    """
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="INTC")
    ]
    r.list_companies_by_ticker.return_value = []
    r.create_company.return_value = {"id": "new-intc", "ticker": "INTC"}
    fmp = _make_fmp_profile("INTC")
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    # create_watchlist_membership was called — the company is now in the watchlist
    # and will be returned by list_watchlist_active_companies on the next call.
    r.create_watchlist_membership.assert_called_once_with("wl-1", "new-intc")
    assert m["add_requests_approved"] == 1


# ── pending-request load failure is logged and skipped ───────────────────────


def test_repo_failure_on_load_requests_is_handled_gracefully() -> None:
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.side_effect = RuntimeError("DB down")
    m = _metrics()

    # Must not raise.
    mod._process_pending_add_requests(r, None, "run-1", m)

    assert m["add_requests_processed"] == 0
    r.log_pipeline_event.assert_called()


# ── FMP exchange mismatch via profile ────────────────────────────────────────


def test_fmp_exchange_mismatch_in_profile_rejects_request() -> None:
    """User requests AAPL on NYSE, FMP says it's on NASDAQ."""
    mod = _load_pipeline_module()
    r = _base_repo()
    req = _pending_request(ticker="AAPL", exchange="NYSE")
    r.list_pending_watchlist_add_requests.return_value = [req]
    r.get_company_by_ticker_exchange.return_value = None  # not on NYSE
    r.list_companies_by_ticker.return_value = []  # not in DB
    fmp = _make_fmp_profile("AAPL", exchange="NASDAQ")
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.reject_watchlist_add_request.assert_called_once()
    args = r.reject_watchlist_add_request.call_args[0]
    assert args[1] == "exchange_mismatch"
    assert m["add_requests_rejected"] == 1


# ── Multi-profile FMP responses ───────────────────────────────────────────────


def _make_fmp_multi_profile(profiles: list[dict]) -> MagicMock:
    """Return a mock FMP connector that returns multiple profiles."""
    resp = MagicMock()
    resp.success = True
    resp.payload = profiles
    fmp = MagicMock()
    fmp.get_profile.return_value = resp
    return fmp


def test_fmp_multi_profile_no_exchange_rejects_ambiguous_ticker() -> None:
    """Multi-profile FMP response with no requested_exchange → ambiguous_ticker."""
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="VOD", exchange=None)
    ]
    r.list_companies_by_ticker.return_value = []  # not in DB yet
    fmp = _make_fmp_multi_profile([
        {"companyName": "Vodafone NASDAQ", "exchangeShortName": "NASDAQ", "country": "US"},
        {"companyName": "Vodafone LSE", "exchangeShortName": "LSE", "country": "GB"},
    ])
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.reject_watchlist_add_request.assert_called_once()
    args = r.reject_watchlist_add_request.call_args[0]
    assert args[1] == "ambiguous_ticker"
    assert m["add_requests_rejected"] == 1
    r.create_company.assert_not_called()


def test_fmp_multi_profile_with_exact_exchange_match_approves() -> None:
    """Multi-profile FMP response with an exact exchange match → approved using matched profile."""
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="VOD", exchange="NASDAQ")
    ]
    r.list_companies_by_ticker.return_value = []
    nasdaq_profile = {
        "companyName": "Vodafone NASDAQ",
        "exchangeShortName": "NASDAQ",
        "country": "US",
        "currency": "USD",
        "sector": "Telecom",
        "industry": "Wireless",
        "cik": "0009876543",
    }
    lse_profile = {
        "companyName": "Vodafone LSE",
        "exchangeShortName": "LSE",
        "country": "GB",
        "currency": "GBP",
        "sector": "Telecom",
        "industry": "Wireless",
        "cik": None,
    }
    fmp = _make_fmp_multi_profile([nasdaq_profile, lse_profile])
    r.create_company.return_value = {"id": "new-vod", "ticker": "VOD"}
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.create_company.assert_called_once()
    call_kwargs = r.create_company.call_args[1]
    # Must use NASDAQ profile data, not LSE
    assert call_kwargs.get("country") == "US"
    assert call_kwargs.get("currency") == "USD"
    assert call_kwargs.get("cik") == "0009876543"
    r.approve_watchlist_add_request.assert_called_once_with("req-1", "new-vod")
    assert m["add_requests_approved"] == 1


def test_fmp_multi_profile_no_exchange_match_rejects_exchange_mismatch() -> None:
    """Multi-profile FMP with exchange provided but no profile matches → exchange_mismatch."""
    mod = _load_pipeline_module()
    r = _base_repo()
    r.list_pending_watchlist_add_requests.return_value = [
        _pending_request(ticker="VOD", exchange="NYSE")
    ]
    r.list_companies_by_ticker.return_value = []
    fmp = _make_fmp_multi_profile([
        {"companyName": "Vodafone NASDAQ", "exchangeShortName": "NASDAQ", "country": "US"},
        {"companyName": "Vodafone LSE", "exchangeShortName": "LSE", "country": "GB"},
    ])
    m = _metrics()

    mod._process_pending_add_requests(r, fmp, "run-1", m)

    r.reject_watchlist_add_request.assert_called_once()
    args = r.reject_watchlist_add_request.call_args[0]
    assert args[1] == "exchange_mismatch"
    assert m["add_requests_rejected"] == 1
    r.create_company.assert_not_called()
