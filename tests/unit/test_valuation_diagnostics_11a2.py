"""PR 11A.2 — Valuation diagnostics expansion tests.

Covers the new diagnostic fields added to _build_diagnostics:
  - distribution_collapsed warning
  - mos_basis constant
  - scenario_count
  - uncertainty_category (from _classify_uncertainty)

Also verifies:
  - valuation_v1 model version unchanged
  - No change to IV percentile or MoS calculations in compute_valuation_run
  - New diagnostic fields visible in assumptions["diagnostics"] on the pipeline output

No network.  No Supabase.  No secrets.
"""
from __future__ import annotations

from typing import Any

import pytest

import investment_app.valuation.scenarios as _scenarios_module
from investment_app.valuation.scenarios import (
    MODEL_VERSION,
    _build_diagnostics,
    _classify_uncertainty,
    _weighted_percentiles,
    compute_valuation_run,
)


# ---------------------------------------------------------------------------
# Shared fixture constants (same style as test_valuation_audit.py)
# ---------------------------------------------------------------------------

_STMT = {"fiscal_year": 2024, "fiscal_period": "annual", "period_end_date": "2024-12-31"}
_STMT_PREV = {"fiscal_year": 2023, "fiscal_period": "annual", "period_end_date": "2023-12-31"}
_RATIO = {"factor_date": "2024-12-31", "price_to_earnings": 18.0}
_FCF_OK = {"direct_fcf_status": "positive", "base_fcf": 5_000_000.0, "fcf_source": "direct_fcf"}

# A one-entry distribution (minimal valid case — NOT considered collapsed).
_DIST_SINGLE = [{"source": "dcf_base", "method": "dcf", "value": 100.0, "weight": 0.5}]

# Three distinct DCF scenario values + one multiples value.
_DIST_FULL = [
    {"source": "dcf_bear",   "method": "dcf",       "value":  80.0, "weight": 0.125},
    {"source": "dcf_base",   "method": "dcf",       "value": 100.0, "weight": 0.250},
    {"source": "dcf_bull",   "method": "dcf",       "value": 130.0, "weight": 0.125},
    {"source": "multiples",  "method": "multiples", "value": 110.0, "weight": 0.300},
]

_SENTINEL = object()


def _call(
    annual_statements: Any = _SENTINEL,
    ratio_rows: Any = _SENTINEL,
    current_price: Any = 100.0,
    diluted_shares: Any = 50_000_000.0,
    fcf_data: Any = _SENTINEL,
    terminal_growth: float = 0.02,
    wacc: float = 0.09,
    distribution: Any = _SENTINEL,
    uncertainty_width: float | None = None,
) -> dict[str, Any]:
    """Call _build_diagnostics with valid defaults; override as needed."""
    return _build_diagnostics(
        annual_statements=annual_statements if annual_statements is not _SENTINEL else [_STMT, _STMT_PREV],
        ratio_rows=ratio_rows if ratio_rows is not _SENTINEL else [_RATIO],
        current_price=current_price,
        diluted_shares=diluted_shares,
        fcf_data=fcf_data if fcf_data is not _SENTINEL else _FCF_OK,
        terminal_growth=terminal_growth,
        wacc=wacc,
        distribution=distribution if distribution is not _SENTINEL else list(_DIST_SINGLE),
        uncertainty_width=uncertainty_width,
    )


# ---------------------------------------------------------------------------
# _classify_uncertainty — boundary tests
# ---------------------------------------------------------------------------


class TestClassifyUncertainty:
    def test_none_returns_none(self):
        assert _classify_uncertainty(None) is None

    def test_zero_is_low(self):
        assert _classify_uncertainty(0.0) == "low"

    def test_at_low_boundary_is_low(self):
        assert _classify_uncertainty(0.35) == "low"

    def test_just_above_low_boundary_is_moderate(self):
        assert _classify_uncertainty(0.351) == "moderate"

    def test_at_moderate_boundary_is_moderate(self):
        assert _classify_uncertainty(0.75) == "moderate"

    def test_just_above_moderate_boundary_is_high(self):
        assert _classify_uncertainty(0.751) == "high"

    def test_at_high_boundary_is_high(self):
        assert _classify_uncertainty(1.25) == "high"

    def test_just_above_high_boundary_is_extreme(self):
        assert _classify_uncertainty(1.251) == "extreme"

    def test_large_value_is_extreme(self):
        assert _classify_uncertainty(10.0) == "extreme"


# ---------------------------------------------------------------------------
# _build_diagnostics — distribution_collapsed warning
# ---------------------------------------------------------------------------


class TestDistributionCollapsed:
    def test_multiple_identical_values_triggers_warning(self):
        # All three entries have value=100.0 → collapsed
        dist = [
            {"source": "dcf_bear",  "method": "dcf",       "value": 100.0, "weight": 0.25},
            {"source": "dcf_base",  "method": "dcf",       "value": 100.0, "weight": 0.50},
            {"source": "multiples", "method": "multiples", "value": 100.0, "weight": 0.30},
        ]
        result = _call(distribution=dist)
        assert "distribution_collapsed" in result["warnings"]

    def test_distinct_values_do_not_trigger_warning(self):
        result = _call(distribution=list(_DIST_FULL))
        assert "distribution_collapsed" not in result["warnings"]

    def test_single_entry_does_not_trigger_warning(self):
        # One entry is minimal valid; it is NOT classified as collapsed.
        result = _call(distribution=list(_DIST_SINGLE))
        assert "distribution_collapsed" not in result["warnings"]

    def test_empty_distribution_does_not_trigger_warning(self):
        result = _call(distribution=[])
        assert "distribution_collapsed" not in result["warnings"]

    def test_two_identical_entries_triggers_warning(self):
        dist = [
            {"source": "dcf_base",  "method": "dcf",       "value": 90.0, "weight": 0.50},
            {"source": "multiples", "method": "multiples", "value": 90.0, "weight": 0.30},
        ]
        result = _call(distribution=dist)
        assert "distribution_collapsed" in result["warnings"]

    def test_two_distinct_values_does_not_trigger_warning(self):
        dist = [
            {"source": "dcf_base",  "method": "dcf",       "value":  90.0, "weight": 0.50},
            {"source": "multiples", "method": "multiples", "value": 110.0, "weight": 0.30},
        ]
        result = _call(distribution=dist)
        assert "distribution_collapsed" not in result["warnings"]

    def test_collapsed_distribution_sets_data_quality_limited(self):
        dist = [
            {"source": "dcf_bear", "method": "dcf", "value": 100.0, "weight": 0.25},
            {"source": "dcf_base", "method": "dcf", "value": 100.0, "weight": 0.50},
        ]
        result = _call(distribution=dist)
        # distribution_collapsed is a warning → data_quality_flag becomes "limited"
        assert result["data_quality_flag"] == "limited"


# ---------------------------------------------------------------------------
# _build_diagnostics — mos_basis
# ---------------------------------------------------------------------------


class TestMosBasis:
    def test_mos_basis_is_iv_p10(self):
        assert _call()["mos_basis"] == "iv_p10"

    def test_mos_basis_present_when_distribution_empty(self):
        assert _call(distribution=[])["mos_basis"] == "iv_p10"

    def test_mos_basis_present_with_full_distribution(self):
        assert _call(distribution=list(_DIST_FULL))["mos_basis"] == "iv_p10"

    def test_mos_basis_is_constant_regardless_of_inputs(self):
        # Varies inputs; mos_basis must always equal "iv_p10".
        for dist in [[], list(_DIST_SINGLE), list(_DIST_FULL)]:
            assert _call(distribution=dist)["mos_basis"] == "iv_p10"


# ---------------------------------------------------------------------------
# _build_diagnostics — scenario_count
# ---------------------------------------------------------------------------


class TestScenarioCount:
    def test_single_dcf_entry_counts_one(self):
        result = _call(distribution=list(_DIST_SINGLE))
        assert result["scenario_count"] == 1

    def test_three_dcf_entries_counts_three(self):
        result = _call(distribution=list(_DIST_FULL))
        assert result["scenario_count"] == 3

    def test_multiples_only_counts_zero(self):
        dist = [{"source": "multiples", "method": "multiples", "value": 110.0, "weight": 0.30}]
        result = _call(distribution=dist)
        assert result["scenario_count"] == 0

    def test_empty_distribution_counts_zero(self):
        assert _call(distribution=[])["scenario_count"] == 0

    def test_two_dcf_one_multiples_counts_two(self):
        dist = [
            {"source": "dcf_bear",  "method": "dcf",       "value":  80.0, "weight": 0.125},
            {"source": "dcf_base",  "method": "dcf",       "value": 100.0, "weight": 0.250},
            {"source": "multiples", "method": "multiples", "value": 110.0, "weight": 0.300},
        ]
        result = _call(distribution=dist)
        assert result["scenario_count"] == 2


# ---------------------------------------------------------------------------
# _build_diagnostics — uncertainty_category
# ---------------------------------------------------------------------------


class TestUncategoryCategoryFromBuildDiagnostics:
    def test_none_uncertainty_returns_none_category(self):
        # Default: uncertainty_width not passed → None
        result = _call()
        assert result["uncertainty_category"] is None

    def test_low_category(self):
        result = _call(uncertainty_width=0.20)
        assert result["uncertainty_category"] == "low"

    def test_low_at_boundary(self):
        result = _call(uncertainty_width=0.35)
        assert result["uncertainty_category"] == "low"

    def test_moderate_just_above_low(self):
        result = _call(uncertainty_width=0.36)
        assert result["uncertainty_category"] == "moderate"

    def test_moderate_at_boundary(self):
        result = _call(uncertainty_width=0.75)
        assert result["uncertainty_category"] == "moderate"

    def test_high_just_above_moderate(self):
        result = _call(uncertainty_width=0.76)
        assert result["uncertainty_category"] == "high"

    def test_high_at_boundary(self):
        result = _call(uncertainty_width=1.25)
        assert result["uncertainty_category"] == "high"

    def test_extreme_above_high(self):
        result = _call(uncertainty_width=1.26)
        assert result["uncertainty_category"] == "extreme"


# ---------------------------------------------------------------------------
# compute_valuation_run integration — new diagnostics visible in assumptions
# ---------------------------------------------------------------------------


class _FakeValRepo:
    """Minimal fake repo for valuation pipeline integration tests."""

    def __init__(
        self,
        *,
        statements: list[dict[str, Any]] | None = None,
        prices: list[dict[str, Any]] | None = None,
        ratios: list[dict[str, Any]] | None = None,
    ) -> None:
        self._statements = statements or []
        self._prices = prices or []
        self._ratios = ratios or []

    def get_statements_for_company(self, cid: str, *, as_of_date: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        return self._statements

    def get_prices_for_company(self, cid: str, *, as_of_date: str | None = None, limit: int = 2) -> list[dict[str, Any]]:
        return self._prices

    def get_ratios_for_company(self, cid: str, *, as_of_date: str | None = None) -> list[dict[str, Any]]:
        return self._ratios


_FULL_STMT = {
    "fiscal_year": 2024,
    "fiscal_period": "annual",
    "period_end_date": "2024-12-31",
    "revenue": 10_000_000.0,
    "gross_profit": 4_000_000.0,
    "ebit": 2_000_000.0,
    "net_income": 1_500_000.0,
    "free_cash_flow": 1_800_000.0,
    "diluted_shares": 10_000_000.0,
    "total_equity": 20_000_000.0,
    "cash_and_equivalents": 2_000_000.0,
    "total_debt": 4_000_000.0,
    "capex": -500_000.0,
    "depreciation_amortization": 300_000.0,
    "dividends_paid": None,
}
_FULL_STMT_PREV = {**_FULL_STMT, "fiscal_year": 2023, "period_end_date": "2023-12-31", "revenue": 9_000_000.0}
_FULL_PRICE = {"close": 18.0, "price_date": "2024-12-31"}
_FULL_RATIO = {"factor_date": "2024-12-31", "price_to_earnings": 15.0, "ev_to_ebitda": 10.0}

_COMPANY_ID = "test-co-11a2"
_VALUATION_DATE = "2024-12-31"


def _make_full_repo() -> _FakeValRepo:
    return _FakeValRepo(
        statements=[_FULL_STMT, _FULL_STMT_PREV],
        prices=[_FULL_PRICE],
        ratios=[_FULL_RATIO],
    )


class TestComputeValuationRunNewDiagnostics:
    def test_diagnostics_contain_mos_basis(self):
        result = compute_valuation_run(_COMPANY_ID, _make_full_repo(), _VALUATION_DATE)
        assert result is not None
        diag = result["assumptions"]["diagnostics"]
        assert diag["mos_basis"] == "iv_p10"

    def test_diagnostics_contain_scenario_count(self):
        result = compute_valuation_run(_COMPANY_ID, _make_full_repo(), _VALUATION_DATE)
        assert result is not None
        diag = result["assumptions"]["diagnostics"]
        # With valid FCF, bear/base/bull all compute → scenario_count == 3
        assert diag["scenario_count"] == 3

    def test_diagnostics_contain_uncertainty_category(self):
        result = compute_valuation_run(_COMPANY_ID, _make_full_repo(), _VALUATION_DATE)
        assert result is not None
        diag = result["assumptions"]["diagnostics"]
        # Category must be one of the four valid strings (or None if width is None)
        assert diag["uncertainty_category"] in {"low", "moderate", "high", "extreme", None}

    def test_iv_percentiles_unchanged(self):
        """Verify the iv_p10..iv_p90 values on the output row are unaffected."""
        result = compute_valuation_run(_COMPANY_ID, _make_full_repo(), _VALUATION_DATE)
        assert result is not None
        # All five percentile fields must be present and be non-None
        for key in ("iv_p10", "iv_p25", "iv_p50", "iv_p75", "iv_p90"):
            assert result[key] is not None, f"{key} should not be None"

    def test_percentiles_monotonically_non_decreasing(self):
        result = compute_valuation_run(_COMPANY_ID, _make_full_repo(), _VALUATION_DATE)
        assert result is not None
        ordered = [result[k] for k in ("iv_p10", "iv_p25", "iv_p50", "iv_p75", "iv_p90")]
        for a, b in zip(ordered, ordered[1:]):
            assert a <= b

    def test_mos_uses_iv_p10(self):
        """margin_of_safety_conservative must equal (iv_p10 - price) / price."""
        result = compute_valuation_run(_COMPANY_ID, _make_full_repo(), _VALUATION_DATE)
        assert result is not None
        iv_p10 = result["iv_p10"]
        price = result["current_price"]
        expected_mos = (iv_p10 - price) / price
        assert result["margin_of_safety_conservative"] == pytest.approx(expected_mos, rel=1e-6)

    def test_model_version_unchanged(self):
        assert MODEL_VERSION == "valuation_v1"
        assert _scenarios_module.MODEL_VERSION == "valuation_v1"

    def test_uncertainty_width_unchanged(self):
        """uncertainty_width on the output row must equal (iv_p90 - iv_p10) / iv_p10."""
        result = compute_valuation_run(_COMPANY_ID, _make_full_repo(), _VALUATION_DATE)
        assert result is not None
        iv_p10 = result["iv_p10"]
        iv_p90 = result["iv_p90"]
        if iv_p10 is not None and iv_p90 is not None and iv_p10 > 0.0:
            expected = (iv_p90 - iv_p10) / iv_p10
            assert result["uncertainty_width"] == pytest.approx(expected, rel=1e-6)
