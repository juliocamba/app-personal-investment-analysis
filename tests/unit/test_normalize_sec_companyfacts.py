"""Unit tests for investment_app.etl.normalize_sec_companyfacts.

All tests use static mock payloads — no live API calls.
"""
from __future__ import annotations

from typing import Any

import pytest

from investment_app.etl.normalize_sec_companyfacts import (
    _count_usable_annual_rows,
    _discover_fiscal_years,
    _extract_concept_value,
    _fact_rank_key,
    _normalize_capex,
    _select_best_fact_for_year,
    fmp_statements_need_fallback,
    normalize_sec_companyfacts_annual,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_ID = "company-uuid-sec-001"
TICKER = "MU"
CIK = "0000723254"


def _annual_fact(
    fy: int,
    val: float,
    filed: str = "2024-01-15",
    end: str = "2023-09-30",
    form: str = "10-K",
    fp: str = "FY",
    accn: str = "0000723254-24-000001",
) -> dict[str, Any]:
    return {
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
        "start": f"{fy - 1}-10-01",
        "end": end,
        "val": val,
    }


def _make_companyfacts(
    *,
    revenue: float = 25_000_000_000,
    net_income: float = 3_000_000_000,
    operating_income: float = 4_000_000_000,
    cfo: float = 5_000_000_000,
    capex: float = 2_000_000_000,  # positive — SEC reports as payment
    cash: float = 1_500_000_000,
    total_assets: float = 40_000_000_000,
    liabilities: float = 20_000_000_000,
    equity: float = 20_000_000_000,
    total_debt: float = 8_000_000_000,
    diluted_shares: float = 1_100_000_000,
    gross_profit: float = 10_000_000_000,
    fy: int = 2023,
    extra_concepts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal but realistic companyfacts payload for testing."""
    us_gaap: dict[str, Any] = {
        "Revenues": {"units": {"USD": [_annual_fact(fy, revenue)]}},
        "GrossProfit": {"units": {"USD": [_annual_fact(fy, gross_profit)]}},
        "OperatingIncomeLoss": {
            "units": {"USD": [_annual_fact(fy, operating_income)]}
        },
        "NetIncomeLoss": {"units": {"USD": [_annual_fact(fy, net_income)]}},
        "NetCashProvidedByUsedInOperatingActivities": {
            "units": {"USD": [_annual_fact(fy, cfo)]}
        },
        "PaymentsToAcquirePropertyPlantAndEquipment": {
            "units": {"USD": [_annual_fact(fy, capex)]}
        },
        "CashAndCashEquivalentsAtCarryingValue": {
            "units": {"USD": [_annual_fact(fy, cash)]}
        },
        "Assets": {"units": {"USD": [_annual_fact(fy, total_assets)]}},
        "Liabilities": {"units": {"USD": [_annual_fact(fy, liabilities)]}},
        "StockholdersEquity": {"units": {"USD": [_annual_fact(fy, equity)]}},
        "DebtLongtermAndShorttermCombinedAmount": {
            "units": {"USD": [_annual_fact(fy, total_debt)]}
        },
        "WeightedAverageNumberOfDilutedSharesOutstanding": {
            "units": {"shares": [_annual_fact(fy, diluted_shares)]}
        },
    }
    if extra_concepts:
        us_gaap.update(extra_concepts)
    return {"facts": {"us-gaap": us_gaap}}


def _append_fact(
    us_gaap: dict[str, Any],
    concept: str,
    unit: str,
    fy: int,
    val: float,
    *,
    form: str = "10-K",
) -> None:
    concept_payload = us_gaap.setdefault(concept, {"units": {}})
    unit_facts = concept_payload.setdefault("units", {}).setdefault(unit, [])
    unit_facts.append(
        _annual_fact(
            fy,
            val,
            filed=f"{fy + 1}-02-15",
            end=f"{fy}-12-31",
            form=form,
            accn=f"sec-{fy}-{concept}",
        )
    )


def _stale_revenues_fresh_core_payload(
    years: tuple[int, ...] = (2025, 2024),
    *,
    omit_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Build a SEC payload where Revenues is stale but other core facts are fresh."""
    omit_fields = omit_fields or set()
    us_gaap: dict[str, Any] = {
        "Revenues": {
            "units": {
                "USD": [
                    _annual_fact(
                        2018,
                        30_000_000_000,
                        filed="2019-02-15",
                        end="2018-12-31",
                        accn="sec-2018-stale-revenue",
                    )
                ]
            }
        }
    }
    for idx, fy in enumerate(years):
        scale = float(idx + 1)
        if "revenue" not in omit_fields:
            _append_fact(
                us_gaap,
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "USD",
                fy,
                40_000_000_000 - scale,
            )
        if "gross_profit" not in omit_fields:
            _append_fact(us_gaap, "GrossProfit", "USD", fy, 12_000_000_000 - scale)
        if "operating_income" not in omit_fields:
            _append_fact(us_gaap, "OperatingIncomeLoss", "USD", fy, 5_000_000_000 - scale)
        if "net_income" not in omit_fields:
            _append_fact(us_gaap, "NetIncomeLoss", "USD", fy, 4_000_000_000 - scale)
        if "cfo" not in omit_fields:
            _append_fact(
                us_gaap,
                "NetCashProvidedByUsedInOperatingActivities",
                "USD",
                fy,
                6_000_000_000 - scale,
            )
        if "capex" not in omit_fields:
            _append_fact(
                us_gaap,
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "USD",
                fy,
                1_500_000_000 + scale,
            )
        if "cash_and_equivalents" not in omit_fields:
            _append_fact(
                us_gaap,
                "CashAndCashEquivalentsAtCarryingValue",
                "USD",
                fy,
                2_000_000_000,
            )
        if "total_debt" not in omit_fields:
            _append_fact(
                us_gaap,
                "DebtLongtermAndShorttermCombinedAmount",
                "USD",
                fy,
                8_000_000_000,
            )
        if "total_assets" not in omit_fields:
            _append_fact(us_gaap, "Assets", "USD", fy, 60_000_000_000 + scale)
        if "total_liabilities" not in omit_fields:
            _append_fact(us_gaap, "Liabilities", "USD", fy, 25_000_000_000 + scale)
        if "total_equity" not in omit_fields:
            _append_fact(us_gaap, "StockholdersEquity", "USD", fy, 35_000_000_000 + scale)
        if "diluted_shares" not in omit_fields:
            _append_fact(
                us_gaap,
                "WeightedAverageNumberOfDilutedSharesOutstanding",
                "shares",
                fy,
                1_000_000_000 + scale,
            )
    return {"facts": {"us-gaap": us_gaap}}


# ---------------------------------------------------------------------------
# _fact_rank_key
# ---------------------------------------------------------------------------


def test_fact_rank_key_prefers_later_filed():
    f1 = _annual_fact(2023, 100, filed="2024-01-01")
    f2 = _annual_fact(2023, 200, filed="2024-02-01")
    assert _fact_rank_key(f2) > _fact_rank_key(f1)


def test_fact_rank_key_does_not_encode_form_preference():
    """_fact_rank_key no longer distinguishes form — form selection is
    handled by _select_best_fact_for_year before ranking."""
    f1 = _annual_fact(2023, 100, form="10-K/A", filed="2024-01-01", end="2023-09-30")
    f2 = _annual_fact(2023, 200, form="10-K",   filed="2024-01-01", end="2023-09-30")
    # Same filed, same end, same accn prefix — only accn differs; form is irrelevant.
    # Neither should be strictly greater based solely on form.
    assert _fact_rank_key(f1)[:2] == _fact_rank_key(f2)[:2]  # filed and end match


def test_select_best_fact_10k_beats_later_filed_non_10k():
    """A later-filed non-10-K FY fact must NOT beat an earlier 10-K fact."""
    f_10k = _annual_fact(2023, 25_000_000_000, form="10-K",   filed="2023-11-01", accn="000-01")
    f_other = _annual_fact(2023, 20_000_000_000, form="10-K/A", filed="2024-03-01", accn="000-02")
    result = _select_best_fact_for_year([f_10k, f_other], 2023)
    assert result["form"] == "10-K"
    assert result["val"] == 25_000_000_000


def test_select_best_fact_falls_back_to_non_10k_when_no_10k_exists():
    """When no 10-K fact is available any annual FY fact is acceptable."""
    f_20f = _annual_fact(2023, 15_000_000_000, form="20-F", filed="2024-01-01", accn="000-01")
    result = _select_best_fact_for_year([f_20f], 2023)
    assert result is not None
    assert result["form"] == "20-F"


def test_select_best_fact_10k_tiebreak_by_filed_date():
    """Within 10-K facts, the latest filed date wins."""
    f_old = _annual_fact(2023, 100, form="10-K", filed="2023-11-01", accn="000-01")
    f_new = _annual_fact(2023, 200, form="10-K", filed="2024-01-15", accn="000-02")
    result = _select_best_fact_for_year([f_old, f_new], 2023)
    assert result["val"] == 200


def test_select_best_fact_10k_tiebreak_all_same_filed_uses_end_date():
    """Within 10-K facts with same filed date, later end date wins."""
    f1 = _annual_fact(2023, 100, form="10-K", filed="2024-01-15", end="2023-08-31", accn="000-01")
    f2 = _annual_fact(2023, 200, form="10-K", filed="2024-01-15", end="2023-09-30", accn="000-02")
    result = _select_best_fact_for_year([f1, f2], 2023)
    assert result["val"] == 200


def test_select_best_fact_non_10k_beats_earlier_10k_when_only_non_10k():
    """With two non-10-K facts and no 10-K, latest-filed wins."""
    f_old = _annual_fact(2023, 100, form="20-F", filed="2023-11-01", accn="000-01")
    f_new = _annual_fact(2023, 200, form="20-F", filed="2024-01-15", accn="000-02")
    result = _select_best_fact_for_year([f_old, f_new], 2023)
    assert result["val"] == 200


def test_fact_rank_key_same_filed_same_form_later_end_wins():
    f1 = _annual_fact(2023, 100, end="2023-08-31")
    f2 = _annual_fact(2023, 200, end="2023-09-30")
    assert _fact_rank_key(f2) > _fact_rank_key(f1)


# ---------------------------------------------------------------------------
# _select_best_fact_for_year
# ---------------------------------------------------------------------------


def test_select_best_fact_returns_none_for_wrong_year():
    facts = [_annual_fact(2022, 100)]
    result = _select_best_fact_for_year(facts, 2023)
    assert result is None


def test_select_best_fact_returns_none_for_non_annual():
    facts = [_annual_fact(2023, 100, fp="Q1")]
    result = _select_best_fact_for_year(facts, 2023)
    assert result is None


def test_select_best_fact_prefers_latest_filed():
    f_old = _annual_fact(2023, 100, filed="2023-10-01", accn="000-01")
    f_new = _annual_fact(2023, 200, filed="2024-01-15", accn="000-02")
    result = _select_best_fact_for_year([f_old, f_new], 2023)
    assert result["val"] == 200


def test_select_best_fact_prefers_10k():
    f_amendment = _annual_fact(2023, 100, form="10-K/A", filed="2024-01-15", accn="000-01")
    f_original = _annual_fact(2023, 200, form="10-K", filed="2024-01-15", accn="000-02")
    result = _select_best_fact_for_year([f_amendment, f_original], 2023)
    assert result["val"] == 200


# ---------------------------------------------------------------------------
# _normalize_capex
# ---------------------------------------------------------------------------


def test_normalize_capex_makes_negative():
    assert _normalize_capex(2_000_000_000) == -2_000_000_000


def test_normalize_capex_negative_stays_negative():
    assert _normalize_capex(-2_000_000_000) == -2_000_000_000


def test_normalize_capex_none_returns_none():
    assert _normalize_capex(None) is None


def test_normalize_capex_zero():
    assert _normalize_capex(0) == 0


# ---------------------------------------------------------------------------
# _extract_concept_value
# ---------------------------------------------------------------------------


def test_extract_concept_value_returns_first_match():
    us_gaap = {
        "Revenues": {"units": {"USD": [_annual_fact(2023, 25_000_000_000)]}},
    }
    val, concept, fact = _extract_concept_value(
        us_gaap, ["Revenues", "SalesRevenueNet"], "USD", 2023
    )
    assert val == 25_000_000_000
    assert concept == "Revenues"
    assert fact is not None


def test_extract_concept_value_falls_back_to_second_concept():
    us_gaap = {
        "SalesRevenueNet": {"units": {"USD": [_annual_fact(2023, 10_000_000)]}},
    }
    val, concept, _ = _extract_concept_value(
        us_gaap,
        ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "USD",
        2023,
    )
    assert val == 10_000_000
    assert concept == "SalesRevenueNet"


def test_extract_concept_value_returns_none_when_all_absent():
    val, concept, fact = _extract_concept_value({}, ["Revenues"], "USD", 2023)
    assert val is None
    assert concept is None
    assert fact is None


def test_extract_concept_value_wrong_unit_returns_none():
    us_gaap = {
        "Revenues": {"units": {"EUR": [_annual_fact(2023, 25_000_000)]}},
    }
    val, _, _ = _extract_concept_value(us_gaap, ["Revenues"], "USD", 2023)
    assert val is None


# ---------------------------------------------------------------------------
# _discover_fiscal_years
# ---------------------------------------------------------------------------


def test_discover_fiscal_years_finds_correct_years():
    payload = _make_companyfacts(fy=2023)
    # Add a second year
    us_gaap = payload["facts"]["us-gaap"]
    us_gaap["Revenues"]["units"]["USD"].append(_annual_fact(2022, 20_000_000_000))
    years = _discover_fiscal_years(us_gaap)
    assert 2023 in years
    assert 2022 in years


def test_discover_fiscal_years_excludes_quarterly():
    us_gaap = {
        "Revenues": {
            "units": {
                "USD": [
                    _annual_fact(2023, 100, fp="Q1"),
                    _annual_fact(2023, 100, fp="Q2"),
                ]
            }
        }
    }
    years = _discover_fiscal_years(us_gaap)
    assert years == []


def test_discover_fiscal_years_returns_sorted_descending():
    us_gaap = {
        "Revenues": {
            "units": {
                "USD": [
                    _annual_fact(2021, 100),
                    _annual_fact(2023, 300),
                    _annual_fact(2022, 200),
                ]
            }
        }
    }
    years = _discover_fiscal_years(us_gaap)
    assert years == [2023, 2022, 2021]


def test_discover_fiscal_years_unions_stale_revenue_and_fresh_core_concepts():
    payload = _stale_revenues_fresh_core_payload(years=(2025, 2024, 2023))
    us_gaap = payload["facts"]["us-gaap"]
    years = _discover_fiscal_years(us_gaap)
    assert years[:4] == [2025, 2024, 2023, 2018]


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — core field mapping
# ---------------------------------------------------------------------------


def test_normalizer_returns_rows_for_valid_payload():
    payload = _make_companyfacts()
    rows, diag = normalize_sec_companyfacts_annual(
        payload, COMPANY_ID, TICKER, CIK
    )
    assert len(rows) == 1
    assert diag["rows_normalized"] == 1


def test_normalizer_source_is_sec_edgar():
    payload = _make_companyfacts()
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["source"] == "sec_edgar"


def test_normalizer_maps_revenue():
    payload = _make_companyfacts(revenue=25_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["revenue"] == 25_000_000_000


def test_normalizer_maps_gross_profit():
    payload = _make_companyfacts(gross_profit=10_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["gross_profit"] == 10_000_000_000


def test_normalizer_maps_operating_income():
    payload = _make_companyfacts(operating_income=4_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["operating_income"] == 4_000_000_000


def test_normalizer_maps_net_income():
    payload = _make_companyfacts(net_income=3_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["net_income"] == 3_000_000_000


def test_normalizer_maps_cfo():
    payload = _make_companyfacts(cfo=5_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["cfo"] == 5_000_000_000


def test_normalizer_maps_total_assets():
    payload = _make_companyfacts(total_assets=40_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["total_assets"] == 40_000_000_000


def test_normalizer_maps_total_equity():
    payload = _make_companyfacts(equity=20_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["total_equity"] == 20_000_000_000


def test_normalizer_maps_total_liabilities():
    payload = _make_companyfacts(liabilities=20_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["total_liabilities"] == 20_000_000_000


def test_normalizer_maps_cash():
    payload = _make_companyfacts(cash=1_500_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["cash_and_equivalents"] == 1_500_000_000


def test_normalizer_maps_total_debt():
    payload = _make_companyfacts(total_debt=8_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["total_debt"] == 8_000_000_000


def test_normalizer_maps_diluted_shares():
    payload = _make_companyfacts(diluted_shares=1_100_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["diluted_shares"] == 1_100_000_000


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — capex normalisation
# ---------------------------------------------------------------------------


def test_normalizer_capex_is_negative():
    """SEC reports capex as a positive payment; normaliser must make it negative."""
    payload = _make_companyfacts(capex=2_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["capex"] == -2_000_000_000


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — free_cash_flow derivation
# ---------------------------------------------------------------------------


def test_normalizer_derives_fcf_correctly():
    payload = _make_companyfacts(cfo=5_000_000_000, capex=2_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["free_cash_flow"] == 3_000_000_000


def test_normalizer_fcf_when_cfo_missing_is_none():
    payload = _make_companyfacts()
    del payload["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]
    rows, diag = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["free_cash_flow"] is None
    assert "free_cash_flow" in diag["missing_fields"]


def test_normalizer_fcf_when_capex_missing_is_none():
    payload = _make_companyfacts()
    del payload["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
    rows, diag = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["free_cash_flow"] is None
    assert "free_cash_flow" in diag["missing_fields"]


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — ebit/ebitda derivation
# ---------------------------------------------------------------------------


def test_normalizer_ebit_equals_operating_income():
    payload = _make_companyfacts(operating_income=4_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["ebit"] == 4_000_000_000


def test_normalizer_ebitda_derived_when_da_available():
    da_concept = {
        "DepreciationDepletionAndAmortization": {
            "units": {"USD": [_annual_fact(2023, 1_000_000_000)]}
        }
    }
    payload = _make_companyfacts(
        operating_income=4_000_000_000, extra_concepts=da_concept
    )
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["ebitda"] == 5_000_000_000


def test_normalizer_ebitda_is_none_when_no_da():
    payload = _make_companyfacts()
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["ebitda"] is None


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — annual/FY/10-K filtering
# ---------------------------------------------------------------------------


def test_normalizer_excludes_quarterly_facts():
    payload = _make_companyfacts(fy=2023)
    us_gaap = payload["facts"]["us-gaap"]
    # Replace annual revenue with quarterly-only facts
    us_gaap["Revenues"]["units"]["USD"] = [_annual_fact(2023, 99_000, fp="Q1")]
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    # Revenue must be None since only quarterly facts exist
    if rows:
        assert rows[0]["revenue"] is None


def test_normalizer_prefers_10k_over_10k_amendment():
    payload = _make_companyfacts()
    us_gaap = payload["facts"]["us-gaap"]
    us_gaap["Revenues"]["units"]["USD"] = [
        _annual_fact(2023, 20_000_000_000, form="10-K/A", filed="2024-02-01", accn="000-02"),
        _annual_fact(2023, 25_000_000_000, form="10-K", filed="2024-02-01", accn="000-01"),
    ]
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["revenue"] == 25_000_000_000


def test_normalizer_prefers_latest_filed_for_duplicate_fy():
    payload = _make_companyfacts()
    us_gaap = payload["facts"]["us-gaap"]
    us_gaap["Revenues"]["units"]["USD"] = [
        _annual_fact(2023, 20_000_000_000, filed="2023-11-01", accn="000-01"),
        _annual_fact(2023, 25_000_000_000, filed="2024-02-01", accn="000-02"),
    ]
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["revenue"] == 25_000_000_000


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — diluted shares weak fallback
# ---------------------------------------------------------------------------


def test_normalizer_diluted_shares_weak_fallback_flagged():
    payload = _make_companyfacts()
    us_gaap = payload["facts"]["us-gaap"]
    # Remove strong diluted shares concepts
    del us_gaap["WeightedAverageNumberOfDilutedSharesOutstanding"]
    # Add weak fallback concept
    us_gaap["EntityCommonStockSharesOutstanding"] = {
        "units": {"shares": [_annual_fact(2023, 900_000_000)]}
    }
    rows, diag = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["diluted_shares"] == 900_000_000
    assert "diluted_shares" in diag["weak_fallbacks"]


def test_normalizer_diluted_shares_missing_flagged_in_diagnostics():
    payload = _make_companyfacts()
    us_gaap = payload["facts"]["us-gaap"]
    del us_gaap["WeightedAverageNumberOfDilutedSharesOutstanding"]
    rows, diag = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["diluted_shares"] is None
    assert "diluted_shares" in diag["missing_fields"]


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — missing concepts
# ---------------------------------------------------------------------------


def test_normalizer_missing_concept_does_not_crash():
    payload = _make_companyfacts()
    del payload["facts"]["us-gaap"]["GrossProfit"]
    rows, diag = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert len(rows) == 1
    assert rows[0]["gross_profit"] is None
    assert "gross_profit" in diag["missing_fields"]


def test_normalizer_returns_empty_for_empty_payload():
    rows, diag = normalize_sec_companyfacts_annual(None, COMPANY_ID, TICKER, CIK)
    assert rows == []
    assert "all" in diag["missing_fields"]


def test_normalizer_returns_empty_for_no_us_gaap():
    rows, diag = normalize_sec_companyfacts_annual(
        {"facts": {}}, COMPANY_ID, TICKER, CIK
    )
    assert rows == []


def test_normalizer_returns_empty_for_no_annual_facts():
    payload = {"facts": {"us-gaap": {}}}
    rows, diag = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows == []


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — multiple years
# ---------------------------------------------------------------------------


def test_normalizer_multiple_years_produce_multiple_rows():
    payload = _make_companyfacts(fy=2023)
    us_gaap = payload["facts"]["us-gaap"]
    for concept in list(us_gaap):
        units = us_gaap[concept]["units"]
        unit_key = next(iter(units))  # use whatever unit key exists (USD or shares)
        units[unit_key].append(
            _annual_fact(2022, 20_000_000_000)
        )
    rows, diag = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert len(rows) == 2
    assert diag["rows_normalized"] == 2
    fiscal_years = [r["fiscal_year"] for r in rows]
    assert 2023 in fiscal_years
    assert 2022 in fiscal_years


def test_normalizer_respects_max_years():
    payload = _make_companyfacts(fy=2023)
    us_gaap = payload["facts"]["us-gaap"]
    # Add more years
    for fy in [2022, 2021, 2020, 2019]:
        us_gaap["Revenues"]["units"]["USD"].append(_annual_fact(fy, 1_000_000))
    rows, _ = normalize_sec_companyfacts_annual(
        payload, COMPANY_ID, TICKER, CIK, max_years=2
    )
    assert len(rows) <= 2


def test_normalizer_mu_like_payload_uses_recent_years_from_union_discovery():
    payload = _stale_revenues_fresh_core_payload(years=(2025, 2024, 2023))
    rows, diag = normalize_sec_companyfacts_annual(
        payload,
        COMPANY_ID,
        "MU",
        CIK,
        fallback_reason="fmp_402",
        max_years=2,
    )

    assert [row["fiscal_year"] for row in rows] == [2025, 2024]
    assert rows[0]["period_end_date"] == "2025-12-31"
    assert rows[0]["revenue"] == pytest.approx(39_999_999_999.0)
    assert diag["rows_normalized"] == 2


def test_normalizer_vrtx_like_payload_does_not_stop_at_stale_revenues():
    payload = _stale_revenues_fresh_core_payload(years=(2025, 2024, 2023, 2022, 2021))
    rows, diag = normalize_sec_companyfacts_annual(
        payload,
        COMPANY_ID,
        "VRTX",
        CIK,
        fallback_reason="fmp_402",
    )

    assert [row["fiscal_year"] for row in rows] == [2025, 2024, 2023, 2022, 2021]
    assert rows[0]["source"] == "sec_edgar"
    assert rows[0]["free_cash_flow"] is not None
    assert diag["rows_normalized"] == 5


def test_normalizer_wldn_like_payload_keeps_recent_rows_and_missing_field_diagnostics():
    payload = _stale_revenues_fresh_core_payload(
        years=(2025, 2024),
        omit_fields={"gross_profit", "net_income", "cash_and_equivalents"},
    )
    rows, diag = normalize_sec_companyfacts_annual(
        payload,
        COMPANY_ID,
        "WLDN",
        CIK,
        fallback_reason="fmp_402",
    )

    assert [row["fiscal_year"] for row in rows[:2]] == [2025, 2024]
    assert rows[0]["net_income"] is None
    assert rows[0]["revenue"] is not None
    assert rows[0]["total_assets"] is not None
    assert "net_income" in diag["missing_fields"]
    assert "gross_profit" in diag["missing_fields"]
    assert "cash_and_equivalents" in diag["missing_fields"]


def test_normalizer_mfc_like_no_us_gaap_remains_unsupported():
    rows, diag = normalize_sec_companyfacts_annual(
        {"facts": {"ifrs-full": {"Revenue": {"units": {"USD": []}}}}},
        COMPANY_ID,
        "MFC",
        "0001086888",
        fallback_reason="fmp_402",
    )

    assert rows == []
    assert diag["rows_normalized"] == 0
    assert diag["missing_fields"] == ["all"]


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — provenance metadata
# ---------------------------------------------------------------------------


def test_normalizer_row_has_metadata_field():
    payload = _make_companyfacts()
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert "metadata" in rows[0]


def test_normalizer_metadata_has_source_provider():
    payload = _make_companyfacts()
    rows, _ = normalize_sec_companyfacts_annual(
        payload, COMPANY_ID, TICKER, CIK, fallback_reason="fmp_402"
    )
    meta = rows[0]["metadata"]
    assert meta["source_provider"] == "sec_edgar"
    assert meta["fallback_reason"] == "fmp_402"


def test_normalizer_metadata_field_sources_contains_concept():
    payload = _make_companyfacts()
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    field_sources = rows[0]["metadata"]["field_sources"]
    assert "revenue" in field_sources
    assert field_sources["revenue"]["concept"] == "Revenues"


def test_normalizer_metadata_fcf_marked_derived():
    payload = _make_companyfacts(cfo=5_000_000_000, capex=2_000_000_000)
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    dq = rows[0]["metadata"]["data_quality"]
    assert dq.get("free_cash_flow") == "derived"


def test_normalizer_metadata_weak_shares_marked():
    payload = _make_companyfacts()
    del payload["facts"]["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"]
    payload["facts"]["us-gaap"]["EntityCommonStockSharesOutstanding"] = {
        "units": {"shares": [_annual_fact(2023, 900_000_000)]}
    }
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    dq = rows[0]["metadata"]["data_quality"]
    assert dq.get("diluted_shares") == "entity_common_stock_shares"


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — restated_flag
# ---------------------------------------------------------------------------


def test_normalizer_restated_flag_is_false():
    payload = _make_companyfacts()
    rows, _ = normalize_sec_companyfacts_annual(payload, COMPANY_ID, TICKER, CIK)
    assert rows[0]["restated_flag"] is False


# ---------------------------------------------------------------------------
# fmp_statements_need_fallback
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, status_code: int = 200, payload: Any = None):
        self.status_code = status_code
        self.payload = payload
        self.success = status_code == 200


def _usable_fmp_row() -> dict[str, Any]:
    return {
        "fiscal_year": 2023,
        "fiscal_period": "annual",
        "period_end_date": "2023-09-30",
        "revenue": 100_000,
        "net_income": 10_000,
        "total_assets": None,
        "operating_income": None,
        "cfo": None,
        "free_cash_flow": None,
        "total_equity": None,
    }


def test_fallback_not_triggered_when_fmp_succeeds():
    rows = [_usable_fmp_row()]
    inc = _MockResponse(200, [{"calendarYear": "2023"}])
    bal = _MockResponse(200, [{}])
    cf = _MockResponse(200, [{}])
    needs, reason = fmp_statements_need_fallback(inc, bal, cf, rows)
    assert needs is False
    assert reason == ""


def test_fallback_triggered_on_fmp_402():
    inc = _MockResponse(402, None)
    bal = _MockResponse(402, None)
    cf = _MockResponse(402, None)
    needs, reason = fmp_statements_need_fallback(inc, bal, cf, [])
    assert needs is True
    assert reason == "fmp_402"


def test_fallback_triggered_on_fmp_403():
    inc = _MockResponse(403, None)
    bal = _MockResponse(200, [{}])
    cf = _MockResponse(200, [{}])
    needs, reason = fmp_statements_need_fallback(inc, bal, cf, [])
    assert needs is True
    assert reason == "fmp_403"


def test_fallback_triggered_on_empty_payload():
    inc = _MockResponse(200, [])
    bal = _MockResponse(200, [])
    cf = _MockResponse(200, [])
    needs, reason = fmp_statements_need_fallback(inc, bal, cf, [])
    assert needs is True
    assert reason in ("fmp_empty_payload", "fmp_normalized_zero_rows")


def test_fallback_triggered_on_zero_usable_rows():
    inc = _MockResponse(200, [{"calendarYear": "2023"}])
    bal = _MockResponse(200, [{}])
    cf = _MockResponse(200, [{}])
    needs, reason = fmp_statements_need_fallback(inc, bal, cf, [])
    assert needs is True
    assert reason == "fmp_normalized_zero_rows"


def test_fallback_not_triggered_with_partial_fmp_success():
    """Even with only one usable annual row, FMP is considered authoritative."""
    rows = [_usable_fmp_row()]
    inc = _MockResponse(200, [{"calendarYear": "2023"}])
    bal = _MockResponse(200, [{}])
    cf = _MockResponse(200, [{}])
    needs, _ = fmp_statements_need_fallback(inc, bal, cf, rows)
    assert needs is False


# ---------------------------------------------------------------------------
# _count_usable_annual_rows
# ---------------------------------------------------------------------------


def test_count_usable_rows_counts_correctly():
    rows = [
        _usable_fmp_row(),  # has revenue and period info
        {"fiscal_year": 2022, "fiscal_period": "annual", "period_end_date": "2022-09-30",
         "revenue": None, "net_income": None, "total_assets": None,
         "operating_income": None, "cfo": None, "free_cash_flow": None, "total_equity": None},
        {"fiscal_period": "Q1"},  # quarterly — excluded
    ]
    assert _count_usable_annual_rows(rows) == 1


def test_count_usable_rows_empty():
    assert _count_usable_annual_rows([]) == 0


# ---------------------------------------------------------------------------
# normalize_sec_companyfacts_annual — non-USD company currency (Fix 10A-2)
# ---------------------------------------------------------------------------


def test_normalizer_non_usd_company_currency_still_extracts_usd_facts():
    """A non-USD company (e.g. EUR) must still extract SEC USD monetary facts.

    SEC companyfacts monetary facts are always denominated in USD.  Passing
    a non-USD company currency must not cause monetary facts to be missed.
    """
    payload = _make_companyfacts(revenue=25_000_000_000)
    rows, diag = normalize_sec_companyfacts_annual(
        payload, COMPANY_ID, TICKER, CIK, currency="EUR"
    )
    assert len(rows) == 1, "Should produce one row despite non-USD company currency"
    assert rows[0]["revenue"] == 25_000_000_000
    assert "revenue" not in diag["missing_fields"]


def test_normalizer_row_currency_is_always_usd():
    """Normalized row currency must be USD regardless of company.currency.

    The stored currency reflects the SEC monetary unit (USD), not the
    company's reporting currency.
    """
    payload = _make_companyfacts()
    for company_currency in ("EUR", "JPY", "CHF", "GBP", "USD"):
        rows, _ = normalize_sec_companyfacts_annual(
            payload, COMPANY_ID, TICKER, CIK, currency=company_currency
        )
        assert rows[0]["currency"] == "USD", (
            f"Row currency must be USD; got {rows[0]['currency']!r} "
            f"when company_currency={company_currency!r}"
        )


def test_normalizer_share_units_always_shares_regardless_of_currency():
    """Share concepts always use 'shares' unit, not company currency."""
    payload = _make_companyfacts(diluted_shares=1_100_000_000)
    rows, _ = normalize_sec_companyfacts_annual(
        payload, COMPANY_ID, TICKER, CIK, currency="EUR"
    )
    assert rows[0]["diluted_shares"] == 1_100_000_000


def test_normalizer_eur_company_extracts_full_row_from_usd_sec_facts():
    """All monetary fields are populated from USD SEC facts for a EUR company."""
    payload = _make_companyfacts(
        revenue=10_000_000_000,
        net_income=1_000_000_000,
        total_assets=20_000_000_000,
    )
    rows, diag = normalize_sec_companyfacts_annual(
        payload, COMPANY_ID, TICKER, CIK, currency="EUR"
    )
    assert rows[0]["revenue"] == 10_000_000_000
    assert rows[0]["net_income"] == 1_000_000_000
    assert rows[0]["total_assets"] == 20_000_000_000
    assert rows[0]["currency"] == "USD"
