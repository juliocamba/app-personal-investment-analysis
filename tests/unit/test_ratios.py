"""Unit tests for investment_app.features.ratios."""
from __future__ import annotations

import pytest

from investment_app.features.ratios import (
    _get,
    compute_financial_ratios,
    safe_div,
)


# ---------------------------------------------------------------------------
# safe_div
# ---------------------------------------------------------------------------


def test_safe_div_normal():
    assert safe_div(10.0, 4.0) == pytest.approx(2.5)


def test_safe_div_zero_denominator_returns_none():
    assert safe_div(10.0, 0.0) is None


def test_safe_div_zero_denominator_int_returns_none():
    assert safe_div(5, 0) is None


def test_safe_div_none_numerator_returns_none():
    assert safe_div(None, 4.0) is None


def test_safe_div_none_denominator_returns_none():
    assert safe_div(10.0, None) is None


def test_safe_div_both_none_returns_none():
    assert safe_div(None, None) is None


def test_safe_div_negative_result():
    assert safe_div(-6.0, 3.0) == pytest.approx(-2.0)


# ---------------------------------------------------------------------------
# _get helper
# ---------------------------------------------------------------------------


def test_get_returns_float():
    assert _get({"revenue": "100.5"}, "revenue") == pytest.approx(100.5)


def test_get_missing_key_returns_none():
    assert _get({}, "revenue") is None


def test_get_none_value_returns_none():
    assert _get({"revenue": None}, "revenue") is None


def test_get_non_numeric_returns_none():
    assert _get({"revenue": "n/a"}, "revenue") is None


# ---------------------------------------------------------------------------
# compute_financial_ratios — empty / missing data
# ---------------------------------------------------------------------------


def test_empty_statements_returns_all_none():
    result = compute_financial_ratios([])
    assert result["gross_margin"] is None
    assert result["net_margin"] is None
    assert result["roe"] is None
    assert result["pe_ratio"] is None
    assert result["revenue_growth_yoy"] is None


def test_statement_with_all_none_fields_returns_all_none():
    stmt = {
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "revenue": None,
        "gross_profit": None,
        "operating_income": None,
        "ebit": None,
        "ebitda": None,
        "net_income": None,
        "free_cash_flow": None,
        "total_equity": None,
        "total_debt": None,
        "cash_and_equivalents": None,
        "diluted_shares": None,
    }
    result = compute_financial_ratios([stmt])
    for key, val in result.items():
        assert val is None, f"Expected None for {key!r}, got {val!r}"


# ---------------------------------------------------------------------------
# Margin ratios
# ---------------------------------------------------------------------------

_BASE_STMT = {
    "fiscal_year": 2023,
    "fiscal_period": "FY",
    "revenue": 1_000.0,
    "gross_profit": 600.0,
    "operating_income": 200.0,
    "ebit": 200.0,
    "ebitda": 300.0,
    "net_income": 150.0,
    "free_cash_flow": 120.0,
    "total_equity": 800.0,
    "total_debt": 200.0,
    "cash_and_equivalents": 50.0,
    "diluted_shares": 100.0,
}


def test_gross_margin():
    result = compute_financial_ratios([_BASE_STMT])
    assert result["gross_margin"] == pytest.approx(0.6)


def test_operating_margin():
    result = compute_financial_ratios([_BASE_STMT])
    assert result["operating_margin"] == pytest.approx(0.2)


def test_net_margin():
    result = compute_financial_ratios([_BASE_STMT])
    assert result["net_margin"] == pytest.approx(0.15)


def test_fcf_margin():
    result = compute_financial_ratios([_BASE_STMT])
    assert result["fcf_margin"] == pytest.approx(0.12)


def test_margin_zero_revenue_returns_none():
    stmt = {**_BASE_STMT, "revenue": 0.0}
    result = compute_financial_ratios([stmt])
    assert result["gross_margin"] is None
    assert result["operating_margin"] is None
    assert result["net_margin"] is None
    assert result["fcf_margin"] is None


def test_margin_none_revenue_returns_none():
    stmt = {**_BASE_STMT, "revenue": None}
    result = compute_financial_ratios([stmt])
    assert result["gross_margin"] is None


# ---------------------------------------------------------------------------
# Return ratios
# ---------------------------------------------------------------------------


def test_roe():
    # Single statement: prior equity unavailable → falls back to ending equity.
    result = compute_financial_ratios([_BASE_STMT])
    assert result["roe"] == pytest.approx(150.0 / 800.0)


def test_roe_uses_average_equity_when_two_years():
    prior = {**_BASE_STMT, "fiscal_year": 2022, "total_equity": 700.0}
    result = compute_financial_ratios([_BASE_STMT, prior])
    # avg_equity = (800 + 700) / 2 = 750
    assert result["roe"] == pytest.approx(150.0 / 750.0)


def test_roe_fallback_ending_equity_when_prior_equity_none():
    prior = {**_BASE_STMT, "fiscal_year": 2022, "total_equity": None}
    result = compute_financial_ratios([_BASE_STMT, prior])
    # prior_equity is None → fall back to ending equity = 800
    assert result["roe"] == pytest.approx(150.0 / 800.0)


def test_roe_zero_avg_equity_returns_none():
    prior = {**_BASE_STMT, "fiscal_year": 2022, "total_equity": -800.0}
    result = compute_financial_ratios([_BASE_STMT, prior])
    # avg_equity = (800 + -800) / 2 = 0 → safe_div returns None
    assert result["roe"] is None


def test_roe_zero_equity_returns_none():
    stmt = {**_BASE_STMT, "total_equity": 0.0}
    result = compute_financial_ratios([stmt])
    assert result["roe"] is None


def test_roic():
    # NOPAT = 200 × (1 − 0.25) = 150
    # Invested Capital = 800 + 200 − 50 = 950
    result = compute_financial_ratios([_BASE_STMT])
    assert result["roic"] == pytest.approx(150.0 / 950.0)


def test_roic_missing_debt_returns_none():
    stmt = {**_BASE_STMT, "total_debt": None}
    result = compute_financial_ratios([stmt])
    assert result["roic"] is None


def test_roic_zero_invested_capital_returns_none():
    # total_equity + total_debt - cash = 0
    stmt = {**_BASE_STMT, "total_equity": 0.0, "total_debt": 50.0, "cash_and_equivalents": 50.0}
    result = compute_financial_ratios([stmt])
    assert result["roic"] is None


# ---------------------------------------------------------------------------
# Leverage ratios
# ---------------------------------------------------------------------------


def test_net_debt_to_ebitda():
    # net_debt = 200 - 50 = 150 / ebitda 300 = 0.5
    result = compute_financial_ratios([_BASE_STMT])
    assert result["net_debt_to_ebitda"] == pytest.approx(0.5)


def test_net_debt_to_ebitda_zero_ebitda_returns_none():
    stmt = {**_BASE_STMT, "ebitda": 0.0}
    result = compute_financial_ratios([stmt])
    assert result["net_debt_to_ebitda"] is None


def test_net_debt_to_ebitda_none_debt_returns_none():
    stmt = {**_BASE_STMT, "total_debt": None}
    result = compute_financial_ratios([stmt])
    assert result["net_debt_to_ebitda"] is None


def test_interest_coverage_always_none():
    # interest expense not in statements_norm schema
    result = compute_financial_ratios([_BASE_STMT])
    assert result["interest_coverage"] is None


# ---------------------------------------------------------------------------
# Revenue growth YoY
# ---------------------------------------------------------------------------


def test_revenue_growth_yoy():
    prior = {**_BASE_STMT, "fiscal_year": 2022, "revenue": 800.0}
    result = compute_financial_ratios([_BASE_STMT, prior])
    # (1000 - 800) / 800 = 0.25
    assert result["revenue_growth_yoy"] == pytest.approx(0.25)


def test_revenue_growth_yoy_single_year_returns_none():
    result = compute_financial_ratios([_BASE_STMT])
    assert result["revenue_growth_yoy"] is None


def test_revenue_growth_yoy_zero_prior_revenue_returns_none():
    prior = {**_BASE_STMT, "fiscal_year": 2022, "revenue": 0.0}
    result = compute_financial_ratios([_BASE_STMT, prior])
    assert result["revenue_growth_yoy"] is None


def test_revenue_growth_yoy_none_prior_revenue_returns_none():
    prior = {**_BASE_STMT, "fiscal_year": 2022, "revenue": None}
    result = compute_financial_ratios([_BASE_STMT, prior])
    assert result["revenue_growth_yoy"] is None


# ---------------------------------------------------------------------------
# Market-based ratios
# ---------------------------------------------------------------------------

_PRICE_ROW = {
    "price_date": "2024-01-02",
    "close": 50.0,
    "market_cap": 5_000.0,   # 100 shares × 50
}


def test_pe_ratio():
    result = compute_financial_ratios([_BASE_STMT], latest_price_row=_PRICE_ROW)
    # 5000 / 150 ≈ 33.33
    assert result["pe_ratio"] == pytest.approx(5000.0 / 150.0)


def test_price_to_sales():
    result = compute_financial_ratios([_BASE_STMT], latest_price_row=_PRICE_ROW)
    assert result["price_to_sales"] == pytest.approx(5000.0 / 1000.0)


def test_price_to_book():
    result = compute_financial_ratios([_BASE_STMT], latest_price_row=_PRICE_ROW)
    assert result["price_to_book"] == pytest.approx(5000.0 / 800.0)


def test_ev_to_ebitda():
    # EV = 5000 + 200 - 50 = 5150; ebitda = 300
    result = compute_financial_ratios([_BASE_STMT], latest_price_row=_PRICE_ROW)
    assert result["ev_to_ebitda"] == pytest.approx(5150.0 / 300.0)


def test_fcf_yield():
    # fcf / market_cap = 120 / 5000 = 0.024
    result = compute_financial_ratios([_BASE_STMT], latest_price_row=_PRICE_ROW)
    assert result["fcf_yield"] == pytest.approx(120.0 / 5000.0)


def test_pe_ratio_zero_net_income_returns_none():
    stmt = {**_BASE_STMT, "net_income": 0.0}
    result = compute_financial_ratios([stmt], latest_price_row=_PRICE_ROW)
    assert result["pe_ratio"] is None


def test_market_based_ratios_none_when_no_price_row():
    result = compute_financial_ratios([_BASE_STMT], latest_price_row=None)
    assert result["pe_ratio"] is None
    assert result["price_to_sales"] is None
    assert result["ev_to_ebitda"] is None
    assert result["fcf_yield"] is None


def test_market_cap_derived_from_price_times_shares():
    """When market_cap is absent, derive it from close × diluted_shares."""
    price_no_mcap = {"price_date": "2024-01-02", "close": 50.0}
    result = compute_financial_ratios([_BASE_STMT], latest_price_row=price_no_mcap)
    # derived market_cap = 50 × 100 = 5000
    assert result["price_to_sales"] == pytest.approx(5000.0 / 1000.0)


def test_market_cap_none_when_no_price_and_no_shares():
    stmt = {**_BASE_STMT, "diluted_shares": None}
    price_no_mcap = {"price_date": "2024-01-02", "close": 50.0}
    result = compute_financial_ratios([stmt], latest_price_row=price_no_mcap)
    assert result["pe_ratio"] is None
