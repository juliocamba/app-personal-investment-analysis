"""Unit tests for investment_app.etl.normalize_statements.

Fixtures match the FMP *stable* API shape:
  - ``fiscalYear`` integer field (``calendarYear`` absent, as the stable API
    returns it empty and the normalizer now falls back to ``fiscalYear``).
  - ``ebit`` provided directly on the income statement.
  - Flat-list payloads (no dict wrapper).

Legacy ``calendarYear`` fixtures are retained in selected tests to verify
backwards-compatible behaviour.
"""
from __future__ import annotations

import pytest

from investment_app.etl.normalize_statements import normalize_fmp_statements, _fiscal_period

COMPANY_ID = "company-uuid-001"
TICKER = "AAPL"

# ---------------------------------------------------------------------------
# FMP Stable API fixtures (fiscalYear, not calendarYear)
# ---------------------------------------------------------------------------

_INCOME = [
    {
        "fiscalYear": 2023,
        "period": "FY",
        "date": "2023-09-30",
        "revenue": 383_285_000_000,
        "grossProfit": 169_148_000_000,
        "operatingIncome": 114_301_000_000,
        "ebit": 114_301_000_000,
        "ebitda": 125_820_000_000,
        "netIncome": 96_995_000_000,
        "weightedAverageShsOutDil": 15_744_231_000,
    }
]

_BALANCE = [
    {
        "fiscalYear": 2023,
        "period": "FY",
        "date": "2023-09-30",
        "totalAssets": 352_583_000_000,
        "totalDebt": 120_069_000_000,
        "totalLiabilities": 290_437_000_000,
        "totalStockholdersEquity": 62_146_000_000,
        "totalEquity": 62_146_000_000,
        "cashAndCashEquivalents": 29_965_000_000,
        "netReceivables": 29_508_000_000,
        "inventory": 6_331_000_000,
        "accountPayables": 62_611_000_000,
    }
]

_CASHFLOW = [
    {
        "fiscalYear": 2023,
        "period": "FY",
        "date": "2023-09-30",
        "operatingCashFlow": 113_036_000_000,
        "capitalExpenditure": -10_959_000_000,
        "freeCashFlow": 99_584_000_000,
        "depreciationAndAmortization": 11_519_000_000,
        "stockBasedCompensation": 10_833_000_000,
    }
]


# ---------------------------------------------------------------------------
# _fiscal_period helper
# ---------------------------------------------------------------------------


def test_fiscal_period_fy():
    assert _fiscal_period("FY") == "annual"


def test_fiscal_period_annual():
    assert _fiscal_period("ANNUAL") == "annual"


def test_fiscal_period_quarterly():
    assert _fiscal_period("Q2") == "Q2"


def test_fiscal_period_none():
    assert _fiscal_period(None) == "annual"


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------


def test_normalise_returns_one_row():
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    assert len(rows) == 1


def test_normalise_source_is_fmp():
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    assert rows[0]["source"] == "fmp"


# ---------------------------------------------------------------------------
# Income statement fields (stable API)
# ---------------------------------------------------------------------------


def test_normalise_maps_income_fields():
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    row = rows[0]
    assert row["company_id"] == COMPANY_ID
    assert row["fiscal_year"] == 2023
    assert row["fiscal_period"] == "annual"
    assert row["revenue"] == 383_285_000_000
    assert row["gross_profit"] == 169_148_000_000
    assert row["operating_income"] == 114_301_000_000
    assert row["ebitda"] == 125_820_000_000
    assert row["net_income"] == 96_995_000_000
    assert row["diluted_shares"] == 15_744_231_000


def test_normalise_ebit_uses_direct_field():
    """ebit should come from the income statement's ebit field directly."""
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    assert rows[0]["ebit"] == 114_301_000_000


def test_normalise_ebit_falls_back_to_operating_income():
    """When ebit field is absent, fall back to operatingIncome."""
    income = [{**_INCOME[0]}]
    del income[0]["ebit"]
    rows = normalize_fmp_statements(income, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    assert rows[0]["ebit"] == 114_301_000_000  # operatingIncome fallback


# ---------------------------------------------------------------------------
# Balance sheet fields (stable API)
# ---------------------------------------------------------------------------


def test_normalise_maps_balance_fields():
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    row = rows[0]
    assert row["total_assets"] == 352_583_000_000
    assert row["total_debt"] == 120_069_000_000
    assert row["total_liabilities"] == 290_437_000_000
    assert row["total_equity"] == 62_146_000_000
    assert row["cash_and_equivalents"] == 29_965_000_000
    assert row["receivables"] == 29_508_000_000
    assert row["inventory"] == 6_331_000_000
    assert row["payables"] == 62_611_000_000


# ---------------------------------------------------------------------------
# Cash flow fields (stable API)
# ---------------------------------------------------------------------------


def test_normalise_maps_cashflow_fields():
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    row = rows[0]
    assert row["cfo"] == 113_036_000_000
    assert row["capex"] == -10_959_000_000
    assert row["free_cash_flow"] == 99_584_000_000
    assert row["depreciation_amortization"] == 11_519_000_000
    assert row["stock_based_compensation"] == 10_833_000_000


# ---------------------------------------------------------------------------
# Merge behaviour — null fields from one type must not overwrite populated ones
# ---------------------------------------------------------------------------


def test_all_three_types_merged_into_one_row():
    """Income + balance + CF data must all appear in the same single row."""
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    assert len(rows) == 1
    row = rows[0]
    # Income fields present
    assert row["revenue"] is not None
    # Balance fields present (were null before the fiscalYear fix)
    assert row["total_assets"] is not None
    assert row["cash_and_equivalents"] is not None
    # Cash flow fields present (were null before the fiscalYear fix)
    assert row["cfo"] is not None
    assert row["free_cash_flow"] is not None


def test_missing_balance_does_not_nullify_income_fields():
    """If balance payload is empty, income fields should still be populated."""
    rows = normalize_fmp_statements(_INCOME, [], _CASHFLOW, COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["revenue"] == 383_285_000_000
    assert rows[0]["total_assets"] is None


def test_missing_cashflow_does_not_nullify_income_or_balance_fields():
    """If cash flow payload is empty, income and balance fields should still be populated."""
    rows = normalize_fmp_statements(_INCOME, _BALANCE, [], COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["revenue"] == 383_285_000_000
    assert rows[0]["total_assets"] == 352_583_000_000
    assert rows[0]["cfo"] is None
    assert rows[0]["free_cash_flow"] is None


# ---------------------------------------------------------------------------
# fiscalYear key matching (the critical stable API fix)
# ---------------------------------------------------------------------------


def test_fiscalYear_key_matches_across_all_three_types():
    """fiscalYear (stable API) must join income/balance/CF correctly."""
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    row = rows[0]
    # All three data sources populated — confirms the join worked
    assert row["revenue"] is not None       # income
    assert row["total_assets"] is not None  # balance
    assert row["cfo"] is not None           # cash flow


def test_legacy_calendarYear_still_works():
    """Legacy v3 fixtures using calendarYear must still produce correct output."""
    income = [{"calendarYear": "2022", "period": "FY", "date": "2022-09-30",
               "revenue": 300_000, "grossProfit": 100_000, "operatingIncome": 70_000,
               "ebitda": 80_000, "netIncome": 50_000, "weightedAverageShsOutDil": 1_000}]
    balance = [{"calendarYear": "2022", "period": "FY", "date": "2022-09-30",
                "totalAssets": 200_000, "totalDebt": 50_000,
                "totalStockholdersEquity": 100_000, "cashAndCashEquivalents": 20_000}]
    cashflow = [{"calendarYear": "2022", "period": "FY", "date": "2022-09-30",
                 "operatingCashFlow": 60_000, "freeCashFlow": 50_000}]
    rows = normalize_fmp_statements(income, balance, cashflow, COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["total_assets"] == 200_000
    assert rows[0]["cfo"] == 60_000


def test_date_fallback_matches_when_fiscalYear_and_calendarYear_absent():
    """When neither fiscalYear nor calendarYear is present, date[:4] is the key."""
    income = [{"period": "FY", "date": "2021-09-30",
               "revenue": 100_000, "netIncome": 20_000, "weightedAverageShsOutDil": 500}]
    balance = [{"period": "FY", "date": "2021-09-30", "totalAssets": 150_000}]
    cashflow = [{"period": "FY", "date": "2021-09-30", "operatingCashFlow": 30_000}]
    rows = normalize_fmp_statements(income, balance, cashflow, COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["total_assets"] == 150_000
    assert rows[0]["cfo"] == 30_000


# ---------------------------------------------------------------------------
# Multiple periods
# ---------------------------------------------------------------------------


def test_multiple_periods_produce_multiple_rows():
    income_2 = [
        {**_INCOME[0]},
        {"fiscalYear": 2022, "period": "FY", "date": "2022-09-30",
         "revenue": 350_000, "netIncome": 80_000, "weightedAverageShsOutDil": 16_000},
    ]
    rows = normalize_fmp_statements(income_2, [], [], COMPANY_ID, TICKER)
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_normalise_empty_income_returns_empty():
    rows = normalize_fmp_statements([], _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    assert rows == []


def test_normalise_none_payloads_returns_empty():
    rows = normalize_fmp_statements(None, None, None, COMPANY_ID, TICKER)
    assert rows == []


def test_normalise_missing_balance_still_works():
    rows = normalize_fmp_statements(_INCOME, [], [], COMPANY_ID, TICKER)
    assert len(rows) == 1
    assert rows[0]["total_assets"] is None


# ---------------------------------------------------------------------------
# Valuation-readiness: FCF, debt/cash, shares are all populated
# ---------------------------------------------------------------------------


def test_valuation_critical_fields_all_populated():
    """All fields required by the DCF/valuation layer must be non-null."""
    rows = normalize_fmp_statements(_INCOME, _BALANCE, _CASHFLOW, COMPANY_ID, TICKER)
    row = rows[0]
    valuation_critical = [
        "free_cash_flow",
        "cfo",
        "total_debt",
        "cash_and_equivalents",
        "total_assets",
        "total_equity",
        "diluted_shares",
        "net_income",
    ]
    for field in valuation_critical:
        assert row[field] is not None, f"Expected {field!r} to be non-null"

