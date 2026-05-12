"""Unit tests for investment_app.connectors.sec_edgar."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from investment_app.connectors.sec_edgar import SECEdgarConnector, _normalise_cik


# ---------------------------------------------------------------------------
# CIK normalisation
# ---------------------------------------------------------------------------


def test_normalise_cik_pads_short():
    assert _normalise_cik("320193") == "0000320193"


def test_normalise_cik_already_padded():
    assert _normalise_cik("0000320193") == "0000320193"


def test_normalise_cik_strips_leading_zeros_then_repads():
    assert _normalise_cik("00320193") == "0000320193"


def test_normalise_cik_empty_string():
    assert _normalise_cik("") == ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(status_code: int = 200, json_data=None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = "mock"
    return resp


def _patched_connector(mock_response: MagicMock) -> SECEdgarConnector:
    connector = SECEdgarConnector.__new__(SECEdgarConnector)
    connector._timeout = 60.0
    connector._last_request_time = 0.0
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    connector._client = mock_client
    return connector


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_constructor_requires_user_agent():
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SECEdgarConnector("")


# ---------------------------------------------------------------------------
# get_submissions
# ---------------------------------------------------------------------------


def test_get_submissions_success():
    payload = {"cik": "320193", "name": "Apple Inc."}
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_submissions("320193")

    assert result.success is True
    assert result.payload["name"] == "Apple Inc."
    # CIK should be zero-padded in URL
    call_url = connector._client.get.call_args.args[0]
    assert "CIK0000320193" in call_url


def test_get_submissions_not_found():
    mock_resp = _make_mock_response(404)
    connector = _patched_connector(mock_resp)

    result = connector.get_submissions("999999999")

    assert result.success is False
    assert result.status_code == 404


# ---------------------------------------------------------------------------
# get_company_facts
# ---------------------------------------------------------------------------


def test_get_company_facts_success():
    payload = {"cik": 320193, "facts": {"us-gaap": {}}}
    mock_resp = _make_mock_response(200, payload)
    connector = _patched_connector(mock_resp)

    result = connector.get_company_facts("0000320193")

    assert result.success is True
    assert "facts" in result.payload
    call_url = connector._client.get.call_args.args[0]
    assert "companyfacts" in call_url


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


def test_timeout_returns_failure():
    import httpx

    connector = SECEdgarConnector.__new__(SECEdgarConnector)
    connector._timeout = 60.0
    connector._last_request_time = 0.0
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timeout")
    connector._client = mock_client

    result = connector.get_submissions("320193")

    assert result.success is False
    assert result.status_code == 0
