"""Unit tests for valuation/dcf.py, valuation/multiples.py,
valuation/dividend_discount.py, and valuation/financials.py.

All tests use deterministic fixtures and no live I/O.
"""
from __future__ import annotations

import math
import pytest

from investment_app.valuation.dcf import (
    compute_present_value_fcfs,
    compute_terminal_value,
    enterprise_to_equity_value,
    extract_base_fcf,
    run_dcf_scenario,
    safe_div,
)
from investment_app.valuation.dividend_discount import (
    compute_ddm_value,
    is_ddm_applicable,
)
from investment_app.valuation.financials import (
    compute_financial_sector_value,
    is_financial_sector,
)
from investment_app.valuation.multiples import (
    compute_multiples_value,
    value_by_ev_ebitda,
    value_by_pb,
    value_by_pe,
    value_by_ps,
)


# ---------------------------------------------------------------------------
# safe_div
# ---------------------------------------------------------------------------


def test_safe_div_normal():
    assert safe_div(10.0, 2.0) == pytest.approx(5.0)


def test_safe_div_zero_denominator():
    assert safe_div(10.0, 0.0) is None


def test_safe_div_none_inputs():
    assert safe_div(None, 2.0) is None
    assert safe_div(10.0, None) is None


# ---------------------------------------------------------------------------
# compute_terminal_value
# ---------------------------------------------------------------------------


def test_terminal_value_basic():
    # TV = FCF*(1+g) / (WACC - g)
    # = 100 * 1.02 / (0.10 - 0.02) = 102 / 0.08 = 1275
    tv = compute_terminal_value(100.0, wacc=0.10, terminal_growth=0.02)
    assert tv == pytest.approx(1275.0, rel=1e-5)


def test_terminal_value_returns_none_when_wacc_equals_growth():
    assert compute_terminal_value(100.0, wacc=0.05, terminal_growth=0.05) is None


def test_terminal_value_returns_none_when_growth_exceeds_wacc():
    assert compute_terminal_value(100.0, wacc=0.05, terminal_growth=0.06) is None


def test_terminal_value_zero_fcf():
    tv = compute_terminal_value(0.0, wacc=0.10, terminal_growth=0.02)
    assert tv == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_present_value_fcfs
# ---------------------------------------------------------------------------


def test_pv_fcfs_single_year():
    # base_fcf=100, growth=0, wacc=0.10, years=1
    # year1_fcf = 100, pv = 100/1.10 = 90.909...
    year_fcfs, pv_sum = compute_present_value_fcfs(100.0, 0.0, 0.10, 1)
    assert year_fcfs == pytest.approx([100.0])
    assert pv_sum == pytest.approx(100.0 / 1.10, rel=1e-5)


def test_pv_fcfs_two_years_with_growth():
    # year1 = 100*1.05 = 105, year2 = 105*1.05 = 110.25
    # pv = 105/1.09 + 110.25/1.09^2
    year_fcfs, pv_sum = compute_present_value_fcfs(100.0, 0.05, 0.09, 2)
    expected_y1 = 105.0 / 1.09
    expected_y2 = 110.25 / (1.09 ** 2)
    assert year_fcfs == pytest.approx([105.0, 110.25], rel=1e-5)
    assert pv_sum == pytest.approx(expected_y1 + expected_y2, rel=1e-5)


def test_pv_fcfs_zero_years_returns_empty():
    year_fcfs, pv_sum = compute_present_value_fcfs(100.0, 0.05, 0.09, 0)
    assert year_fcfs == []
    assert pv_sum == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# enterprise_to_equity_value
# ---------------------------------------------------------------------------


def test_equity_value_full_bridge():
    eq = enterprise_to_equity_value(1000.0, net_debt=200.0, minority_interest=50.0, preferred_equity=30.0)
    assert eq == pytest.approx(720.0)


def test_equity_value_missing_components_default_zero():
    eq = enterprise_to_equity_value(1000.0, net_debt=None, minority_interest=None, preferred_equity=None)
    assert eq == pytest.approx(1000.0)


def test_equity_value_negative_net_debt():
    # net cash: net_debt = -50 (cash > debt), so equity > EV
    eq = enterprise_to_equity_value(1000.0, net_debt=-50.0, minority_interest=None, preferred_equity=None)
    assert eq == pytest.approx(1050.0)


# ---------------------------------------------------------------------------
# run_dcf_scenario — known fixture
# ---------------------------------------------------------------------------


def test_run_dcf_scenario_known_values():
    """Verify full DCF arithmetic with a manually-computed fixture.

    base_fcf=100, growth=0.05, wacc=0.09, terminal_growth=0.02, years=3
    net_debt=100, shares=50

    year1 FCF = 105,   pv = 105/1.09  = 96.330...
    year2 FCF = 110.25, pv = 110.25/1.09^2 = 92.835...
    year3 FCF = 115.7625, pv = 115.7625/1.09^3 = 89.396...
    pv_fcfs = 278.562...

    TV = 115.7625 * 1.02 / (0.09-0.02) = 118.077... / 0.07 = 1686.821...
    pv_tv = 1686.821 / 1.09^3 = 1302.634...

    EV = 278.562 + 1302.634 = 1581.196
    equity_value = 1581.196 - 100 = 1481.196
    IV/share = 1481.196 / 50 = 29.624
    """
    result = run_dcf_scenario(
        base_fcf=100.0,
        growth_rate=0.05,
        wacc=0.09,
        terminal_growth=0.02,
        forecast_years=3,
        net_debt=100.0,
        minority_interest=None,
        preferred_equity=None,
        diluted_shares=50.0,
    )
    assert result["pv_fcfs"] == pytest.approx(278.562, rel=1e-3)
    assert result["pv_terminal_value"] == pytest.approx(1302.634, rel=1e-3)
    assert result["enterprise_value"] == pytest.approx(1581.196, rel=1e-3)
    assert result["equity_value"] == pytest.approx(1481.196, rel=1e-3)
    assert result["intrinsic_value_per_share"] == pytest.approx(29.624, rel=1e-3)


def test_run_dcf_scenario_no_fcf_returns_none_iv():
    result = run_dcf_scenario(
        base_fcf=None,
        growth_rate=0.05,
        wacc=0.09,
        terminal_growth=0.02,
        forecast_years=5,
        net_debt=None,
        minority_interest=None,
        preferred_equity=None,
        diluted_shares=100.0,
    )
    assert result["intrinsic_value_per_share"] is None


def test_run_dcf_scenario_wacc_lte_zero_returns_none():
    result = run_dcf_scenario(
        base_fcf=100.0,
        growth_rate=0.05,
        wacc=0.0,
        terminal_growth=0.02,
        forecast_years=5,
        net_debt=None,
        minority_interest=None,
        preferred_equity=None,
        diluted_shares=100.0,
    )
    assert result["intrinsic_value_per_share"] is None


def test_run_dcf_scenario_terminal_growth_equals_wacc_returns_none():
    result = run_dcf_scenario(
        base_fcf=100.0,
        growth_rate=0.05,
        wacc=0.05,
        terminal_growth=0.05,
        forecast_years=5,
        net_debt=None,
        minority_interest=None,
        preferred_equity=None,
        diluted_shares=100.0,
    )
    assert result["intrinsic_value_per_share"] is None


def test_run_dcf_scenario_zero_shares_returns_none_iv():
    result = run_dcf_scenario(
        base_fcf=100.0,
        growth_rate=0.05,
        wacc=0.09,
        terminal_growth=0.02,
        forecast_years=5,
        net_debt=None,
        minority_interest=None,
        preferred_equity=None,
        diluted_shares=0.0,
    )
    assert result["intrinsic_value_per_share"] is None


# ---------------------------------------------------------------------------
# extract_base_fcf
# ---------------------------------------------------------------------------


def test_extract_base_fcf_uses_free_cash_flow_when_positive():
    stmt = {"revenue": 1000.0, "ebit": 200.0, "free_cash_flow": 150.0}
    result = extract_base_fcf([stmt])
    assert result["base_fcf"] == pytest.approx(150.0)
    assert result["direct_fcf_status"] == "positive"
    assert result["fcf_source"] == "direct"


def test_extract_base_fcf_negative_direct_fcf_returns_none():
    stmt = {"revenue": 1000.0, "ebit": 200.0, "free_cash_flow": -10.0}
    result = extract_base_fcf([stmt])
    assert result["base_fcf"] is None
    assert result["direct_fcf_status"] == "negative"
    assert result["fcf_source"] == "direct_negative"


def test_extract_base_fcf_zero_direct_fcf_returns_none():
    stmt = {"revenue": 1000.0, "ebit": 200.0, "free_cash_flow": 0.0}
    result = extract_base_fcf([stmt])
    assert result["base_fcf"] is None
    assert result["direct_fcf_status"] == "zero"
    assert result["fcf_source"] == "direct_zero"


def test_extract_base_fcf_from_ebit():
    stmt = {"revenue": 1000.0, "ebit": 200.0, "depreciation_amortization": 50.0, "capex": -80.0}
    result = extract_base_fcf([stmt], tax_rate_fallback=0.25)
    # nopat = 200*0.75=150, da=50, capex=abs(-80)=80
    # fcff = 150 + 50 - 80 = 120
    assert result["base_fcf"] == pytest.approx(120.0)
    assert result["direct_fcf_status"] == "missing"
    assert result["fcf_source"] == "synthetic_fcff"


def test_extract_base_fcf_no_statements_returns_none():
    result = extract_base_fcf([])
    assert result["base_fcf"] is None


def test_extract_base_fcf_no_ebit_and_no_fcf():
    stmt = {"revenue": 1000.0}
    result = extract_base_fcf([stmt])
    assert result["base_fcf"] is None


def test_extract_base_fcf_caps_margin():
    # EBIT / revenue = 0.8 which exceeds ebit_margin_cap=0.5
    # Should cap EBIT to revenue * 0.5
    stmt = {"revenue": 1000.0, "ebit": 800.0}
    result = extract_base_fcf([stmt], ebit_margin_cap=0.50, tax_rate_fallback=0.25)
    # capped_ebit = 500, nopat = 500*0.75 = 375
    assert result["base_fcf"] == pytest.approx(375.0)


# ---------------------------------------------------------------------------
# Multiples
# ---------------------------------------------------------------------------


def test_value_by_pe_basic():
    # With 3 values [18, 20, 22], trimming at lo=10%, hi=90%:
    # n=3, lo_idx=0, hi_idx=2 → trimmed=[18,20] → median=19; IV=5*19=95
    ratio_rows = [{"pe_ratio": 20.0}, {"pe_ratio": 18.0}, {"pe_ratio": 22.0}]
    iv = value_by_pe(current_eps=5.0, ratio_rows=ratio_rows)
    assert iv == pytest.approx(95.0)


def test_value_by_pe_negative_eps_returns_none():
    ratio_rows = [{"pe_ratio": 20.0}]
    assert value_by_pe(current_eps=-1.0, ratio_rows=ratio_rows) is None


def test_value_by_pe_no_ratio_rows_returns_none():
    assert value_by_pe(current_eps=5.0, ratio_rows=[]) is None


def test_value_by_ev_ebitda_basic():
    # With [10, 12], n=2, trimmed=[10.0] → median=10; EV=5000, equity=4800, IV=48
    ratio_rows = [{"ev_to_ebitda": 10.0}, {"ev_to_ebitda": 12.0}]
    iv = value_by_ev_ebitda(
        current_ebitda=500.0,
        net_debt=200.0,
        diluted_shares=100.0,
        ratio_rows=ratio_rows,
    )
    assert iv == pytest.approx(48.0)


def test_value_by_ev_ebitda_negative_equity_returns_none():
    ratio_rows = [{"ev_to_ebitda": 1.0}]
    # EV = 1*500=500, equity=500-1000 = -500 → None
    iv = value_by_ev_ebitda(
        current_ebitda=500.0,
        net_debt=1000.0,
        diluted_shares=100.0,
        ratio_rows=ratio_rows,
    )
    assert iv is None


def test_value_by_ps_basic():
    # [3, 4] → trimmed=[3.0] → median=3.0; IV = 20*3 = 60
    ratio_rows = [{"price_to_sales": 3.0}, {"price_to_sales": 4.0}]
    iv = value_by_ps(current_revenue_per_share=20.0, ratio_rows=ratio_rows)
    assert iv == pytest.approx(60.0)


def test_value_by_pb_basic():
    # [2.0, 2.5] → trimmed=[2.0] → median=2.0; IV = 30*2 = 60
    ratio_rows = [{"price_to_book": 2.0}, {"price_to_book": 2.5}]
    iv = value_by_pb(current_book_value_per_share=30.0, ratio_rows=ratio_rows)
    assert iv == pytest.approx(60.0)


def test_compute_multiples_value_blended():
    statement = {
        "net_income": 100.0,
        "revenue": 1000.0,
        "total_equity": 500.0,
        "ebit": 150.0,
        "depreciation_amortization": 30.0,
    }
    # Use 3 rows so trimming retains the middle value as median
    ratio_rows = [
        {"pe_ratio": 18.0, "ev_to_ebitda": 9.0, "price_to_sales": 1.8, "price_to_book": 1.8},
        {"pe_ratio": 20.0, "ev_to_ebitda": 10.0, "price_to_sales": 2.0, "price_to_book": 2.0},
        {"pe_ratio": 22.0, "ev_to_ebitda": 11.0, "price_to_sales": 2.2, "price_to_book": 2.2},
    ]
    result = compute_multiples_value(
        statement=statement,
        net_debt=100.0,
        diluted_shares=100.0,
        ratio_rows=ratio_rows,
    )
    # pe: eps=1.0, median_PE(trimmed from [18,20,22])=19 → IV=19
    assert result["pe_value"] == pytest.approx(19.0)
    # ps: rev/share=10, median_PS(trimmed)=1.9 → IV=19
    assert result["ps_value"] == pytest.approx(19.0)
    # pb: bvps=5, median_PB(trimmed)=1.9 → IV=9.5
    assert result["pb_value"] == pytest.approx(9.5)
    # ev_ebitda: ebitda=180, median_mult(trimmed)=9.5, EV=1710, equity=1610, IV/share=16.1
    assert result["ev_ebitda_value"] == pytest.approx(16.1)
    # blended = mean(19, 19, 9.5, 16.1) = 63.6/4 = 15.9
    assert result["blended_value"] == pytest.approx(15.9)


def test_compute_multiples_value_no_statement_returns_none_blended():
    result = compute_multiples_value(
        statement=None,
        net_debt=None,
        diluted_shares=100.0,
        ratio_rows=[{"pe_ratio": 20.0}],
    )
    assert result["blended_value"] is None


# ---------------------------------------------------------------------------
# DDM
# ---------------------------------------------------------------------------


def test_ddm_value_basic():
    # D0=2, g=0.03, Ke=0.09; D1=2.06; V0=2.06/0.06=34.333
    iv = compute_ddm_value(dps=2.0, growth_rate=0.03, cost_of_equity=0.09)
    assert iv == pytest.approx(2.0 * 1.03 / 0.06, rel=1e-5)


def test_ddm_zero_dps_returns_none():
    assert compute_ddm_value(dps=0.0, growth_rate=0.03, cost_of_equity=0.09) is None


def test_ddm_negative_dps_returns_none():
    assert compute_ddm_value(dps=-1.0, growth_rate=0.03, cost_of_equity=0.09) is None


def test_ddm_growth_equals_ke_returns_none():
    assert compute_ddm_value(dps=2.0, growth_rate=0.09, cost_of_equity=0.09) is None


def test_ddm_growth_exceeds_ke_returns_none():
    assert compute_ddm_value(dps=2.0, growth_rate=0.10, cost_of_equity=0.09) is None


def test_is_ddm_applicable_true():
    stmts = [
        {"dividends_paid": -50.0},
        {"dividends_paid": -45.0},
        {"dividends_paid": -40.0},
    ]
    assert is_ddm_applicable(stmts) is True


def test_is_ddm_applicable_no_dividends():
    stmts = [
        {"dividends_paid": 0.0},
        {"dividends_paid": -45.0},
        {"dividends_paid": -40.0},
    ]
    assert is_ddm_applicable(stmts) is False


def test_is_ddm_applicable_missing_dividend():
    stmts = [
        {"dividends_paid": None},
        {"dividends_paid": -45.0},
        {"dividends_paid": -40.0},
    ]
    assert is_ddm_applicable(stmts) is False


def test_is_ddm_applicable_insufficient_history():
    stmts = [{"dividends_paid": -50.0}, {"dividends_paid": -45.0}]
    assert is_ddm_applicable(stmts, years_stable=3) is False


# ---------------------------------------------------------------------------
# Financial sector
# ---------------------------------------------------------------------------


def test_is_financial_sector_true():
    assert is_financial_sector("Financials") is True
    assert is_financial_sector("banking") is True
    assert is_financial_sector("Insurance") is True
    assert is_financial_sector("Real Estate") is True


def test_is_financial_sector_false():
    assert is_financial_sector("Technology") is False
    assert is_financial_sector("Healthcare") is False
    assert is_financial_sector(None) is False
    assert is_financial_sector("") is False


def test_compute_financial_sector_value_basic():
    # ROE=0.15, Ke=0.09, BVPS=50; justified_pb=0.15/0.09=1.666; IV=83.33
    result = compute_financial_sector_value(roe=0.15, cost_of_equity=0.09, book_value_per_share=50.0)
    assert result["justified_pb"] == pytest.approx(0.15 / 0.09, rel=1e-5)
    assert result["intrinsic_value_per_share"] == pytest.approx(50.0 * 0.15 / 0.09, rel=1e-5)
    assert result["method"] == "financial_sector_placeholder_v0"


def test_compute_financial_sector_value_zero_roe():
    result = compute_financial_sector_value(roe=0.0, cost_of_equity=0.09, book_value_per_share=50.0)
    assert result["intrinsic_value_per_share"] is None


def test_compute_financial_sector_value_no_bvps():
    result = compute_financial_sector_value(roe=0.15, cost_of_equity=0.09, book_value_per_share=None)
    assert result["intrinsic_value_per_share"] is None
