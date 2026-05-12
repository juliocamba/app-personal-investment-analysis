"""Unit tests for investment_app.etl.raw_store."""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from investment_app.connectors.base import ProviderResponse
from investment_app.etl.raw_store import _make_checksum, _sanitize_provider_error, store_raw_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    provider: str = "fmp",
    endpoint: str = "profile/AAPL",
    payload=None,
    success: bool = True,
) -> ProviderResponse:
    return ProviderResponse(
        provider=provider,
        endpoint=endpoint,
        params={"symbol": "AAPL"},
        status_code=200 if success else 500,
        success=success,
        payload=payload or {"symbol": "AAPL"},
        payload_text='{"symbol":"AAPL"}',
    )


def _make_db_client(
    request_id: str = "req-001",
    existing_payload_id: str | None = None,
    new_payload_id: str = "raw-001",
) -> MagicMock:
    """Return a mock Supabase client with configured table responses."""
    db = MagicMock()

    # provider_requests insert → returns request row with id
    req_table = MagicMock()
    req_chain = MagicMock()
    req_chain.execute.return_value.data = [{"id": request_id}]
    req_table.insert.return_value = req_chain

    # raw_provider_payloads select (checksum lookup)
    if existing_payload_id:
        select_chain = MagicMock()
        select_chain.execute.return_value.data = [{"id": existing_payload_id}]
    else:
        select_chain = MagicMock()
        select_chain.execute.return_value.data = []

    # raw_provider_payloads insert → returns new row with id
    raw_insert_chain = MagicMock()
    raw_insert_chain.execute.return_value.data = [{"id": new_payload_id}]

    # Wire up table() to return different chains for different tables.
    def _table_side_effect(table_name: str):
        tbl = MagicMock()
        if table_name == "provider_requests":
            return req_table
        elif table_name == "raw_provider_payloads":
            # select chain (for checksum lookup)
            select_obj = MagicMock()
            select_obj.eq.return_value.limit.return_value = select_chain
            tbl.select.return_value = select_obj
            tbl.insert.return_value = raw_insert_chain
        return tbl

    db.table.side_effect = _table_side_effect
    db._provider_requests_table = req_table
    return db


# ---------------------------------------------------------------------------
# _make_checksum
# ---------------------------------------------------------------------------


def test_checksum_is_deterministic():
    resp = _make_response()
    assert _make_checksum(resp) == _make_checksum(resp)


def test_checksum_differs_for_different_payload():
    resp_a = _make_response(payload={"x": 1})
    resp_b = _make_response(payload={"x": 2})
    assert _make_checksum(resp_a) != _make_checksum(resp_b)


def test_checksum_is_hex_string():
    resp = _make_response()
    checksum = _make_checksum(resp)
    assert isinstance(checksum, str)
    int(checksum, 16)  # should not raise


# ---------------------------------------------------------------------------
# store_raw_response — new payload
# ---------------------------------------------------------------------------


def test_store_raw_response_inserts_new_payload():
    db = _make_db_client(new_payload_id="raw-abc")
    resp = _make_response()

    result = store_raw_response(resp, company_id="company-1", client=db)

    assert result == "raw-abc"
    inserted_payload = db._provider_requests_table.insert.call_args[0][0]
    assert inserted_payload["response_checksum"] == _make_checksum(resp)


def test_store_raw_response_returns_none_on_no_payload():
    db = MagicMock()
    req_chain = MagicMock()
    req_chain.execute.return_value.data = [{"id": "req-1"}]

    def _table_side_effect(name: str):
        tbl = MagicMock()
        tbl.insert.return_value = req_chain
        return tbl

    db.table.side_effect = _table_side_effect

    resp = ProviderResponse(
        provider="fmp",
        endpoint="profile/AAPL",
        params={},
        status_code=200,
        success=True,
        payload=None,
        payload_text=None,
    )

    result = store_raw_response(resp, company_id=None, client=db)

    assert result is None


# ---------------------------------------------------------------------------
# store_raw_response — duplicate detection
# ---------------------------------------------------------------------------


def test_store_raw_response_skips_duplicate_checksum():
    db = _make_db_client(existing_payload_id="existing-raw-id")
    resp = _make_response()

    result = store_raw_response(resp, company_id="company-1", client=db)

    # Should return the existing ID without inserting a new row.
    assert result == "existing-raw-id"


# ---------------------------------------------------------------------------
# _sanitize_provider_error
# ---------------------------------------------------------------------------


def test_sanitize_accepts_safe_connector_tag():
    assert _sanitize_provider_error("fmp_request_failed (ConnectError)") == "fmp_request_failed (ConnectError)"


def test_sanitize_accepts_other_valid_tags():
    assert _sanitize_provider_error("ecb_request_failed (TimeoutException)") == "ecb_request_failed (TimeoutException)"
    assert _sanitize_provider_error("sec_edgar_request_failed (ReadTimeout)") == "sec_edgar_request_failed (ReadTimeout)"
    assert _sanitize_provider_error("gdelt_request_failed (ConnectError)") == "gdelt_request_failed (ConnectError)"


def test_sanitize_none_returns_none():
    assert _sanitize_provider_error(None) is None


def test_sanitize_replaces_raw_url():
    raw = "ConnectError: https://financialmodelingprep.com/api/v3/profile/AAPL?apikey=SECRET_KEY_12345"
    result = _sanitize_provider_error(raw)
    assert result == "provider_error_sanitized"
    assert "SECRET_KEY_12345" not in (result or "")


def test_sanitize_replaces_raw_exception_message():
    raw = "HTTPStatusError: 401 Unauthorized for https://api.telegram.org/botTOKEN/sendMessage"
    result = _sanitize_provider_error(raw)
    assert result == "provider_error_sanitized"
    assert "TOKEN" not in (result or "")


def test_sanitize_replaces_long_messages():
    raw = "x" * 200
    result = _sanitize_provider_error(raw)
    assert result == "provider_error_sanitized"


def test_sanitize_persists_safe_error_in_provider_requests():
    """When a connector provides a safe error_message, it is stored as-is."""
    db = MagicMock()
    req_chain = MagicMock()
    req_chain.execute.return_value.data = [{"id": "req-1"}]

    captured: dict[str, object] = {}

    def _table_side_effect(name: str) -> MagicMock:
        tbl = MagicMock()
        if name == "provider_requests":
            def _capture_insert(payload: dict) -> MagicMock:
                captured["payload"] = payload
                return req_chain
            tbl.insert.side_effect = _capture_insert
        else:
            tbl.insert.return_value = req_chain
        return tbl

    db.table.side_effect = _table_side_effect

    resp = ProviderResponse(
        provider="fmp",
        endpoint="profile/AAPL",
        params={},
        status_code=0,
        success=False,
        payload=None,
        payload_text=None,
        error_message="fmp_request_failed (ConnectError)",
    )
    store_raw_response(resp, company_id=None, client=db)

    assert "payload" in captured
    assert captured["payload"].get("error_message") == "fmp_request_failed (ConnectError)"


def test_sanitize_strips_unsafe_error_in_provider_requests():
    """Raw exception text accidentally passed by a connector is sanitized before DB write."""
    db = MagicMock()
    req_chain = MagicMock()
    req_chain.execute.return_value.data = [{"id": "req-1"}]

    captured: dict[str, object] = {}

    def _table_side_effect(name: str) -> MagicMock:
        tbl = MagicMock()
        if name == "provider_requests":
            def _capture_insert(payload: dict) -> MagicMock:
                captured["payload"] = payload
                return req_chain
            tbl.insert.side_effect = _capture_insert
        else:
            tbl.insert.return_value = req_chain
        return tbl

    db.table.side_effect = _table_side_effect

    # Simulate a connector that accidentally passes raw exception text.
    resp = ProviderResponse(
        provider="fmp",
        endpoint="profile/AAPL",
        params={},
        status_code=0,
        success=False,
        payload=None,
        payload_text=None,
        error_message="ConnectError: https://financialmodelingprep.com?apikey=SECRET_KEY",
    )
    store_raw_response(resp, company_id=None, client=db)

    assert "payload" in captured
    stored_error = captured["payload"].get("error_message", "")
    assert stored_error == "provider_error_sanitized"
    assert "SECRET_KEY" not in stored_error
