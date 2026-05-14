"""Unit tests for TwelveDataConnector."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from investment_app.connectors.twelve_data import TwelveDataConnector


_FAKE_KEY = "fake-twelve-api-key-0123456789"

_VALID_PAYLOAD = {
    "meta": {"symbol": "ORCL", "interval": "1day", "currency": "USD"},
    "values": [
        {
            "datetime": "2024-01-02",
            "open": "102.50",
            "high": "105.00",
            "low": "101.00",
            "close": "104.00",
            "volume": "5000000",
        },
    ],
}


def _make_connector() -> TwelveDataConnector:
    conn = TwelveDataConnector.__new__(TwelveDataConnector)
    conn._api_key = _FAKE_KEY
    conn._timeout = 30.0
    conn._last_request_time = 0.0
    conn._min_request_interval = 0.0  # skip rate-limiting in tests
    conn._client = MagicMock()
    return conn


# ── Constructor ────────────────────────────────────────────────────────────────


def test_empty_api_key_raises():
    with pytest.raises(ValueError, match="TWELVE_DATA_API_KEY"):
        TwelveDataConnector("")


def test_provider_name():
    conn = _make_connector()
    assert conn.provider_name == "twelve_data"


# ── Successful fetch ───────────────────────────────────────────────────────────


def test_get_time_series_success():
    conn = _make_connector()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"meta": {}, "values": []}'
    mock_resp.json.return_value = _VALID_PAYLOAD
    conn._client.get.return_value = mock_resp

    result = conn.get_time_series("ORCL")

    assert result.success is True
    assert result.provider == "twelve_data"
    assert result.payload == _VALID_PAYLOAD
    # API key must NOT appear in the returned params
    assert "apikey" not in result.params
    assert _FAKE_KEY not in str(result.params)


def test_get_time_series_params_passed_correctly():
    conn = _make_connector()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "{}"
    mock_resp.json.return_value = {"meta": {}, "values": []}
    conn._client.get.return_value = mock_resp

    conn.get_time_series("AAPL", start_date="2024-01-01", end_date="2024-01-31", outputsize=30)

    call_kwargs = conn._client.get.call_args
    sent_params = call_kwargs[1]["params"]
    assert sent_params["symbol"] == "AAPL"
    assert sent_params["start_date"] == "2024-01-01"
    assert sent_params["end_date"] == "2024-01-31"
    assert sent_params["outputsize"] == 30
    assert sent_params["interval"] == "1day"
    # API key should be in the actual HTTP request params (so the request works)
    assert sent_params["apikey"] == _FAKE_KEY


# ── HTTP error status ─────────────────────────────────────────────────────────


def test_get_time_series_http_402_returns_failure():
    conn = _make_connector()

    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_resp.text = "payment required"
    mock_resp.json.side_effect = Exception("no json")
    conn._client.get.return_value = mock_resp

    result = conn.get_time_series("ORCL")

    assert result.success is False
    assert result.status_code == 402
    assert result.payload is None


def test_get_time_series_application_error_code_in_200():
    """Twelve Data sometimes returns HTTP 200 with {"code": 400, "message": "..."}."""
    conn = _make_connector()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"code": 400, "message": "Invalid symbol"}'
    mock_resp.json.return_value = {"code": 400, "message": "Invalid symbol"}
    conn._client.get.return_value = mock_resp

    result = conn.get_time_series("INVALID")

    assert result.success is False
    assert result.payload is None


# ── Error sanitisation ────────────────────────────────────────────────────────


def test_get_time_series_timeout_error_sanitized():
    conn = _make_connector()
    conn._client.get.side_effect = httpx.ConnectTimeout("timed out")

    result = conn.get_time_series("ORCL")

    assert result.success is False
    assert result.error_message is not None
    assert "twelve_data_request_failed" in result.error_message
    assert "ConnectTimeout" in result.error_message
    # Must NOT contain the full URL or API key
    assert _FAKE_KEY not in result.error_message
    assert "twelvedata.com" not in result.error_message


def test_get_time_series_request_error_sanitized():
    conn = _make_connector()
    conn._client.get.side_effect = httpx.ConnectError("refused")

    result = conn.get_time_series("ORCL")

    assert result.success is False
    assert result.error_message is not None
    assert "twelve_data_request_failed" in result.error_message
    assert "ConnectError" in result.error_message
    assert _FAKE_KEY not in result.error_message


def test_no_api_key_in_error_message():
    """API key value must never appear in any error message."""
    conn = _make_connector()
    conn._client.get.side_effect = httpx.ReadTimeout("read timeout")

    result = conn.get_time_series("ORCL")

    assert _FAKE_KEY not in (result.error_message or "")
    assert _FAKE_KEY not in str(result.params)
    assert _FAKE_KEY not in (result.payload_text or "")


def test_no_api_key_in_response_params():
    """ProviderResponse.params must never contain apikey."""
    conn = _make_connector()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "{}"
    mock_resp.json.return_value = {"meta": {}, "values": []}
    conn._client.get.return_value = mock_resp

    result = conn.get_time_series("MU", start_date="2024-01-01")

    assert "apikey" not in result.params
    for v in result.params.values():
        assert _FAKE_KEY != v
