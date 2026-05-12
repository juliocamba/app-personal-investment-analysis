"""Unit tests for investment_app.connectors.fmp.

Tests verify behaviour against the FMP *stable* API endpoints:
  - profile?symbol={ticker}
  - historical-price-eod/full?symbol={ticker}
  - income-statement?symbol={ticker}
  - balance-sheet-statement?symbol={ticker}
  - cash-flow-statement?symbol={ticker}

All HTTP calls are mocked — no live API requests.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from investment_app.connectors.fmp import FMPConnector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(
    status_code: int = 200,
    json_data: Any = None,
    raise_exc: Exception | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    if raise_exc:
        resp.json.side_effect = raise_exc
    else:
        resp.json.return_value = json_data or {}
    resp.text = "mock"
    return resp


def _patched_connector(mock_response: MagicMock) -> FMPConnector:
    connector = FMPConnector.__new__(FMPConnector)
    connector._timeout = 30.0
    connector._api_key = "test-key"
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    connector._client = mock_client
    connector._last_request_time = 0.0
    return connector


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_constructor_requires_api_key():
    with pytest.raises(ValueError, match="FMP_API_KEY"):
        FMPConnector("")


def test_constructor_accepts_key():
    with patch("httpx.Client"):
        connector = FMPConnector("test-key")
    assert connector.provider_name == "fmp"


# ---------------------------------------------------------------------------
# get_profile — stable: GET /stable/profile?symbol=AAPL
# ---------------------------------------------------------------------------


def test_get_profile_success():
    payload = [{"symbol": "AAPL", "companyName": "Apple Inc."}]
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_profile("AAPL")

    assert result.success is True
    assert result.payload == payload
    assert result.provider == "fmp"
    connector._client.get.assert_called_once()
    # Verify symbol is passed as query param, not embedded in path
    call_kwargs = connector._client.get.call_args
    params = call_kwargs.kwargs.get("params") or {}
    assert params.get("symbol") == "AAPL"


def test_get_profile_not_found_returns_failure():
    mock_resp = _make_mock_response(404, {})
    connector = _patched_connector(mock_resp)

    result = connector.get_profile("UNKNOWN")

    assert result.success is False
    assert result.status_code == 404


def test_get_profile_rate_limited_returns_failure():
    mock_resp = _make_mock_response(429, {})
    connector = _patched_connector(mock_resp)

    result = connector.get_profile("AAPL")

    assert result.success is False
    assert result.status_code == 429


def test_get_profile_forbidden_returns_failure():
    """HTTP 403 must be recorded as failure; error_message must not leak the URL or key."""
    mock_resp = _make_mock_response(403, {})
    mock_resp.text = "Forbidden"
    connector = _patched_connector(mock_resp)

    result = connector.get_profile("AAPL")

    assert result.success is False
    assert result.status_code == 403
    # error_message comes from the sanitized path, never from raw exception text
    assert result.error_message is None  # HTTP errors set no error_message on ProviderResponse


# ---------------------------------------------------------------------------
# get_historical_prices — stable: GET /stable/historical-price-eod/full?symbol=AAPL
# ---------------------------------------------------------------------------


def test_get_historical_prices_success():
    # Stable API returns a flat list (no "historical" wrapper)
    payload = [
        {"date": "2024-01-02", "open": 185.0, "close": 186.0, "volume": 100000}
    ]
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_historical_prices("AAPL")

    assert result.success is True
    assert isinstance(result.payload, list)
    # Verify correct stable endpoint path is used
    call_url = connector._client.get.call_args.args[0]
    assert "historical-price-eod/full" in call_url
    assert "historical-price-full" not in call_url


def test_get_historical_prices_symbol_as_query_param():
    payload = [{"date": "2024-01-02", "close": 186.0}]
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    connector.get_historical_prices("AAPL")

    call_kwargs = connector._client.get.call_args
    params = call_kwargs.kwargs.get("params") or {}
    assert params.get("symbol") == "AAPL"


def test_get_historical_prices_with_dates():
    payload = [{"date": "2024-01-02", "close": 186.0}]
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_historical_prices("AAPL", from_date="2024-01-01", to_date="2024-01-31")

    assert result.success is True
    call_kwargs = connector._client.get.call_args
    params = call_kwargs.kwargs.get("params") or {}
    assert params.get("from") == "2024-01-01"
    assert params.get("to") == "2024-01-31"


# ---------------------------------------------------------------------------
# get_income_statement — stable: GET /stable/income-statement?symbol=AAPL
# ---------------------------------------------------------------------------


def test_get_income_statement_annual():
    payload = [{"calendarYear": "2023", "period": "FY", "revenue": 100_000}]
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_income_statement("AAPL", period="annual", limit=5)

    assert result.success is True
    assert isinstance(result.payload, list)
    call_kwargs = connector._client.get.call_args
    params = call_kwargs.kwargs.get("params") or {}
    assert params.get("symbol") == "AAPL"
    assert "income-statement" in connector._client.get.call_args.args[0]


# ---------------------------------------------------------------------------
# get_balance_sheet — stable: GET /stable/balance-sheet-statement?symbol=AAPL
# ---------------------------------------------------------------------------


def test_get_balance_sheet_success():
    payload = [{"calendarYear": "2023", "period": "FY", "totalAssets": 500_000}]
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_balance_sheet("AAPL")

    assert result.success is True
    assert isinstance(result.payload, list)
    call_kwargs = connector._client.get.call_args
    params = call_kwargs.kwargs.get("params") or {}
    assert params.get("symbol") == "AAPL"
    assert "balance-sheet-statement" in connector._client.get.call_args.args[0]


# ---------------------------------------------------------------------------
# get_cash_flow — stable: GET /stable/cash-flow-statement?symbol=AAPL
# ---------------------------------------------------------------------------


def test_get_cash_flow_success():
    payload = [{"calendarYear": "2023", "period": "FY", "operatingCashFlow": 200_000}]
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_cash_flow("AAPL")

    assert result.success is True
    assert isinstance(result.payload, list)
    call_kwargs = connector._client.get.call_args
    params = call_kwargs.kwargs.get("params") or {}
    assert params.get("symbol") == "AAPL"
    assert "cash-flow-statement" in connector._client.get.call_args.args[0]


# ---------------------------------------------------------------------------
# Timeout / request error handling
# ---------------------------------------------------------------------------


def test_timeout_returns_failure():
    import httpx

    connector = FMPConnector.__new__(FMPConnector)
    connector._timeout = 30.0
    connector._api_key = "test-key"
    connector._last_request_time = 0.0
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timeout")
    connector._client = mock_client

    result = connector.get_profile("AAPL")

    assert result.success is False
    assert result.status_code == 0
    assert "timeout" in (result.error_message or "").lower()


def test_request_error_returns_failure():
    import httpx

    connector = FMPConnector.__new__(FMPConnector)
    connector._timeout = 30.0
    connector._api_key = "test-key"
    connector._last_request_time = 0.0
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.ConnectError("connect error")
    connector._client = mock_client

    result = connector.get_profile("AAPL")

    assert result.success is False
    assert result.error_message is not None


def test_error_message_does_not_contain_api_key():
    """Sanitization: error_message must never leak the API key."""
    import httpx

    connector = FMPConnector.__new__(FMPConnector)
    connector._timeout = 30.0
    connector._api_key = "super-secret-key-12345"
    connector._last_request_time = 0.0
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.ConnectError("super-secret-key-12345 leaked")
    connector._client = mock_client

    result = connector.get_profile("AAPL")

    assert result.error_message is not None
    assert "super-secret-key-12345" not in (result.error_message or "")

