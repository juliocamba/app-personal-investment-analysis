"""Unit tests for investment_app.etl.normalize_prices."""
from __future__ import annotations

import pytest

from investment_app.etl.normalize_prices import normalize_fmp_prices

COMPANY_ID = "company-uuid-001"
TICKER = "AAPL"

# Minimal valid FMP historical-price-full payload
_VALID_PAYLOAD = {
    "symbol": "AAPL",
    "historical": [
        {
            "date": "2024-01-02",
            "open": 185.0,
            "high": 188.0,
            "low": 184.0,
            "close": 186.0,
            "adjClose": 186.0,
            "volume": 1_000_000,
        },
        {
            "date": "2024-01-03",
            "open": 186.0,
            "high": 189.0,
            "low": 185.0,
            "close": 187.0,
            "adjClose": 187.0,
            "volume": 950_000,
        },
    ],
}


def test_normalise_returns_correct_row_count():
    rows = normalize_fmp_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    assert len(rows) == 2


def test_normalise_maps_fields():
    rows = normalize_fmp_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER)
    row = rows[0]
    assert row["company_id"] == COMPANY_ID
    assert row["price_date"] == "2024-01-02"
    assert row["open"] == 185.0
    assert row["high"] == 188.0
    assert row["low"] == 184.0
    assert row["close"] == 186.0
    assert row["adjusted_close"] == 186.0
    assert row["volume"] == 1_000_000.0
    assert row["provider"] == "fmp"


def test_normalise_includes_currency():
    rows = normalize_fmp_prices(_VALID_PAYLOAD, COMPANY_ID, TICKER, currency="EUR")
    assert rows[0]["currency"] == "EUR"


def test_normalise_empty_historical_returns_empty_list():
    payload = {"symbol": "AAPL", "historical": []}
    rows = normalize_fmp_prices(payload, COMPANY_ID, TICKER)
    assert rows == []


def test_normalise_none_payload_returns_empty_list():
    rows = normalize_fmp_prices(None, COMPANY_ID, TICKER)
    assert rows == []


def test_normalise_skips_entries_missing_date():
    payload = {
        "symbol": "AAPL",
        "historical": [{"open": 100.0, "close": 101.0}],  # no date
    }
    rows = normalize_fmp_prices(payload, COMPANY_ID, TICKER)
    assert rows == []


def test_normalise_skips_entries_missing_close():
    payload = {
        "symbol": "AAPL",
        "historical": [{"date": "2024-01-02"}],  # no close or adjClose
    }
    rows = normalize_fmp_prices(payload, COMPANY_ID, TICKER)
    assert rows == []


# ---------------------------------------------------------------------------
# Stable API flat-list format
# ---------------------------------------------------------------------------

# Stable /stable/historical-price-eod/full returns a flat list, not a wrapped dict.
_STABLE_PAYLOAD = [
    {
        "date": "2024-01-02",
        "open": 185.0,
        "high": 188.0,
        "low": 184.0,
        "close": 186.0,
        "adjClose": 186.0,
        "volume": 1_000_000,
    },
    {
        "date": "2024-01-03",
        "open": 186.0,
        "high": 189.0,
        "low": 185.0,
        "close": 187.0,
        "adjClose": 187.0,
        "volume": 950_000,
    },
]


def test_normalise_stable_flat_list_returns_correct_row_count():
    rows = normalize_fmp_prices(_STABLE_PAYLOAD, COMPANY_ID, TICKER)
    assert len(rows) == 2


def test_normalise_stable_flat_list_maps_fields():
    rows = normalize_fmp_prices(_STABLE_PAYLOAD, COMPANY_ID, TICKER)
    row = rows[0]
    assert row["company_id"] == COMPANY_ID
    assert row["price_date"] == "2024-01-02"
    assert row["open"] == 185.0
    assert row["close"] == 186.0
    assert row["adjusted_close"] == 186.0
    assert row["provider"] == "fmp"


def test_normalise_stable_empty_list_returns_empty():
    rows = normalize_fmp_prices([], COMPANY_ID, TICKER)
    assert rows == []

