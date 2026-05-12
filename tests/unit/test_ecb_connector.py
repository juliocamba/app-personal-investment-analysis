"""Unit tests for investment_app.connectors.ecb."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from investment_app.connectors.ecb import ECBConnector


def _make_mock_response(status_code: int = 200, json_data=None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = "mock"
    return resp


def _patched_connector(mock_response: MagicMock) -> ECBConnector:
    connector = ECBConnector.__new__(ECBConnector)
    connector._timeout = 30.0
    connector._last_request_time = 0.0
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    connector._client = mock_client
    return connector


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_constructor():
    from unittest.mock import patch
    with patch("httpx.Client"):
        connector = ECBConnector()
    assert connector.provider_name == "ecb"


# ---------------------------------------------------------------------------
# get_fx_rate
# ---------------------------------------------------------------------------


def test_get_fx_rate_usd_success():
    payload = {"dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.09]}}}}]}
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_fx_rate("USD")

    assert result.success is True
    assert result.provider == "ecb"
    call_url = connector._client.get.call_args.args[0]
    assert "USD" in call_url
    assert "EXR" in call_url


def test_get_fx_rate_last_n_param():
    mock_resp = _make_mock_response(200, {})
    connector = _patched_connector(mock_resp)

    connector.get_fx_rate("GBP", last_n=3)

    call_kwargs = connector._client.get.call_args.kwargs
    params = call_kwargs.get("params") or {}
    assert params.get("lastNObservations") == 3


def test_get_fx_rate_date_params():
    mock_resp = _make_mock_response(200, {})
    connector = _patched_connector(mock_resp)

    connector.get_fx_rate("JPY", start_period="2024-01-01", end_period="2024-01-31")

    call_kwargs = connector._client.get.call_args.kwargs
    params = call_kwargs.get("params") or {}
    assert params.get("startPeriod") == "2024-01-01"
    assert params.get("endPeriod") == "2024-01-31"


def test_get_fx_rate_http_error():
    mock_resp = _make_mock_response(503)
    connector = _patched_connector(mock_resp)

    result = connector.get_fx_rate("USD")

    assert result.success is False
    assert result.status_code == 503


def test_get_fx_rate_timeout():
    import httpx

    connector = ECBConnector.__new__(ECBConnector)
    connector._timeout = 30.0
    connector._last_request_time = 0.0
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timeout")
    connector._client = mock_client

    result = connector.get_fx_rate("USD")

    assert result.success is False
    assert result.status_code == 0
