"""Unit tests for Twelve Data price normaliser and fmp_prices_need_fallback."""
from __future__ import annotations

import pytest

from investment_app.connectors.base import ProviderResponse
from investment_app.etl.normalize_prices import (
    fmp_prices_need_fallback,
    normalize_twelve_data_prices,
)

COMPANY_ID = "company-uuid-td-001"
TICKER = "ORCL"

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
        {
            "datetime": "2024-01-03",
            "open": "104.00",
            "high": "106.00",
            "low": "103.00",
            "close": "105.50",
            "volume": "4800000",
        },
    ],
}


# ── normalize_twelve_data_prices ──────────────────────────────────────────────


def test_normalize_twelve_valid_payload_returns_rows():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert len(rows) == 2


def test_normalize_twelve_provider_is_twelve_data():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert all(r["provider"] == "twelve_data" for r in rows)


def test_normalize_twelve_numeric_strings_coerced():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    row = rows[0]
    assert row["close"] == 104.0
    assert row["open"] == 102.5
    assert row["high"] == 105.0
    assert row["low"] == 101.0
    assert row["volume"] == 5_000_000.0


def test_normalize_twelve_maps_date_field():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert rows[0]["price_date"] == "2024-01-02"
    assert rows[1]["price_date"] == "2024-01-03"


def test_normalize_twelve_maps_company_id():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert all(r["company_id"] == COMPANY_ID for r in rows)


def test_normalize_twelve_market_cap_null():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert all(r["market_cap"] is None for r in rows)


def test_normalize_twelve_shares_outstanding_null():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert all(r["shares_outstanding"] is None for r in rows)


def test_normalize_twelve_currency_from_meta():
    payload = {**_VALID_PAYLOAD, "meta": {"symbol": "ORCL", "currency": "EUR"}}
    rows = normalize_twelve_data_prices(payload, COMPANY_ID, TICKER, currency="USD")
    # meta currency takes precedence over the fallback argument
    assert all(r["currency"] == "EUR" for r in rows)


def test_normalize_twelve_currency_fallback_when_meta_absent():
    payload = {"values": _VALID_PAYLOAD["values"]}  # no meta
    rows = normalize_twelve_data_prices(payload, COMPANY_ID, TICKER, currency="GBP")
    assert all(r["currency"] == "GBP" for r in rows)


def test_normalize_twelve_raw_payload_id_included_when_provided():
    rows = normalize_twelve_data_prices(
        _VALID_PAYLOAD, COMPANY_ID, TICKER, raw_payload_id="uuid-raw-001"
    )
    assert all(r.get("raw_payload_id") == "uuid-raw-001" for r in rows)


def test_normalize_twelve_raw_payload_id_absent_when_none():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER, raw_payload_id=None)
    assert all("raw_payload_id" not in r for r in rows)


def test_normalize_twelve_skips_missing_date():
    payload = {
        "values": [
            {"open": "100", "close": "101", "volume": "1000"},  # no datetime
            {"datetime": "2024-01-02", "close": "102"},
        ]
    }
    rows = normalize_twelve_data_prices(payload, COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["price_date"] == "2024-01-02"


def test_normalize_twelve_skips_missing_close():
    payload = {
        "values": [
            {"datetime": "2024-01-02", "open": "100"},  # no close
            {"datetime": "2024-01-03", "close": "103"},
        ]
    }
    rows = normalize_twelve_data_prices(payload, COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["price_date"] == "2024-01-03"


def test_normalize_twelve_empty_values_returns_empty():
    rows = normalize_twelve_data_prices({"values": []}, COMPANY_ID, TICKER)
    assert rows == []


def test_normalize_twelve_none_payload_returns_empty():
    rows = normalize_twelve_data_prices(None, COMPANY_ID, TICKER)
    assert rows == []


def test_normalize_twelve_non_dict_payload_returns_empty():
    rows = normalize_twelve_data_prices("bad payload", COMPANY_ID, TICKER)  # type: ignore[arg-type]
    assert rows == []


def test_normalize_twelve_metadata_field_present():
    rows = normalize_twelve_data_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert all("metadata" in r for r in rows)
    assert all(r["metadata"] == {} for r in rows)


def test_normalize_twelve_close_string_zero_not_skipped():
    """close='0' is a valid (edge-case) price — should NOT be skipped."""
    payload = {
        "values": [{"datetime": "2024-01-02", "close": "0"}]
    }
    rows = normalize_twelve_data_prices(payload, COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["close"] == 0.0


# ── fmp_prices_need_fallback ──────────────────────────────────────────────────


def _fmp_resp(status_code: int, success: bool, payload) -> ProviderResponse:
    return ProviderResponse(
        provider="fmp",
        endpoint="historical-price-eod/full",
        params={"symbol": "ORCL"},
        status_code=status_code,
        success=success,
        payload=payload,
        payload_text="",
    )


def test_fmp_prices_need_fallback_402_triggers():
    resp = _fmp_resp(402, False, None)
    needs, reason = fmp_prices_need_fallback(resp, [])
    assert needs is True
    assert reason == "fmp_402"


def test_fmp_prices_need_fallback_403_triggers():
    resp = _fmp_resp(403, False, None)
    needs, reason = fmp_prices_need_fallback(resp, [])
    assert needs is True
    assert reason == "fmp_403"


def test_fmp_prices_need_fallback_success_false_triggers():
    resp = _fmp_resp(500, False, None)
    needs, reason = fmp_prices_need_fallback(resp, [])
    assert needs is True
    assert reason == "fmp_price_fetch_failed"


def test_fmp_prices_need_fallback_empty_payload_triggers():
    resp = _fmp_resp(200, True, None)
    needs, reason = fmp_prices_need_fallback(resp, [])
    assert needs is True
    assert reason == "fmp_price_empty_payload"


def test_fmp_prices_need_fallback_zero_rows_triggers():
    resp = _fmp_resp(200, True, {"historical": []})
    needs, reason = fmp_prices_need_fallback(resp, [])
    assert needs is True
    assert reason == "fmp_price_normalized_zero_rows"


def test_fmp_prices_need_fallback_not_triggered_when_rows_exist():
    resp = _fmp_resp(200, True, {"historical": [{"date": "2024-01-02", "close": 100}]})
    price_rows = [{"price_date": "2024-01-02", "close": 100.0}]
    needs, reason = fmp_prices_need_fallback(resp, price_rows)
    assert needs is False
    assert reason == ""


def test_fmp_prices_need_fallback_402_checked_before_success_flag():
    """402 is a more specific reason than 'success=False'; 402 must win."""
    resp = _fmp_resp(402, False, None)
    needs, reason = fmp_prices_need_fallback(resp, [])
    assert reason == "fmp_402"
