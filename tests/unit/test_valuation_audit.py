"""PR 11A.1 — Baseline audit: lock current valuation model constants and helpers.

Asserts the exact current values of:
- MODEL_VERSION string
- Scenario growth/WACC spread constants
- Default method weights
- _normalize_weights behavior
- _build_diagnostics status/blocker/warning outputs for representative inputs
- _weighted_percentiles correctness

All tests use deterministic in-memory fixtures.  No network, no Supabase, no secrets.
Private helpers are imported directly (Python does not enforce ``_`` name-mangling).
"""
from __future__ import annotations

from typing import Any

import pytest

import investment_app.valuation.scenarios as _scenarios_module
from investment_app.valuation.scenarios import (
    MODEL_VERSION,
    _BEAR_GROWTH_HAIRCUT,
    _BEAR_MARGIN_HAIRCUT,
    _BEAR_WACC_SPREAD,
    _BULL_GROWTH_PREMIUM,
    _BULL_WACC_SPREAD,
    _DEFAULT_METHOD_WEIGHTS,
    _build_diagnostics,
    _normalize_weights,
    _weighted_percentiles,
)


# ---------------------------------------------------------------------------
# MODEL_VERSION — assert exact literal string
# ---------------------------------------------------------------------------


class TestModelVersion:
    def test_model_version_literal_string(self):
        """Fails if the version is bumped without a deliberate change."""
        assert MODEL_VERSION == "valuation_v1"

    def test_module_attribute_matches_import(self):
        assert _scenarios_module.MODEL_VERSION == "valuation_v1"


# ---------------------------------------------------------------------------
# Scenario constants — exact values
# ---------------------------------------------------------------------------


class TestScenarioConstants:
    def test_bear_growth_haircut(self):
        assert _BEAR_GROWTH_HAIRCUT == 0.50

    def test_bull_growth_premium(self):
        assert _BULL_GROWTH_PREMIUM == 1.50

    def test_bear_wacc_spread(self):
        # 150 bps added to base WACC in bear scenario
        assert _BEAR_WACC_SPREAD == pytest.approx(0.015)

    def test_bull_wacc_spread(self):
        # 100 bps subtracted from base WACC in bull scenario
        assert _BULL_WACC_SPREAD == pytest.approx(-0.010)

    def test_bear_margin_haircut(self):
        assert _BEAR_MARGIN_HAIRCUT == pytest.approx(0.90)

    def test_default_method_weights_exact_values(self):
        assert _DEFAULT_METHOD_WEIGHTS == {"dcf": 0.50, "multiples": 0.30, "ddm": 0.20}

    def test_default_method_weights_sum_to_one(self):
        assert sum(_DEFAULT_METHOD_WEIGHTS.values()) == pytest.approx(1.0)

    def test_dcf_is_dominant_weight(self):
        # DCF weight must be the largest single method weight
        assert _DEFAULT_METHOD_WEIGHTS["dcf"] > _DEFAULT_METHOD_WEIGHTS["multiples"]
        assert _DEFAULT_METHOD_WEIGHTS["dcf"] > _DEFAULT_METHOD_WEIGHTS["ddm"]


# ---------------------------------------------------------------------------
# _normalize_weights
# ---------------------------------------------------------------------------


class TestNormalizeWeights:
    def test_two_positive_weights_sum_to_one(self):
        result = _normalize_weights({"a": 2.0, "b": 3.0})
        assert sum(result.values()) == pytest.approx(1.0)

    def test_proportions_are_correct(self):
        result = _normalize_weights({"a": 2.0, "b": 3.0})
        assert result["a"] == pytest.approx(0.4)
        assert result["b"] == pytest.approx(0.6)

    def test_zero_weight_key_is_dropped(self):
        result = _normalize_weights({"a": 2.0, "b": 0.0, "c": 3.0})
        assert "b" not in result
        assert result["a"] == pytest.approx(0.4)
        assert result["c"] == pytest.approx(0.6)

    def test_empty_dict_returns_empty(self):
        assert _normalize_weights({}) == {}

    def test_all_zero_weights_returns_empty(self):
        assert _normalize_weights({"a": 0.0, "b": 0.0}) == {}

    def test_negative_weights_are_excluded(self):
        result = _normalize_weights({"a": 3.0, "b": -1.0})
        assert "b" not in result
        assert result == {"a": pytest.approx(1.0)}

    def test_single_positive_weight_normalizes_to_one(self):
        assert _normalize_weights({"only": 7.5}) == {"only": pytest.approx(1.0)}

    def test_equal_weights_produce_equal_fractions(self):
        result = _normalize_weights({"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0})
        for v in result.values():
            assert v == pytest.approx(0.25)

    def test_output_always_sums_to_one_when_nonempty(self):
        result = _normalize_weights({"x": 10.0, "y": 0.1, "z": 5.0})
        assert sum(result.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _build_diagnostics — status flags and blocker/warning classification
# ---------------------------------------------------------------------------

_STMT = {"fiscal_year": 2024, "fiscal_period": "annual", "period_end_date": "2024-12-31"}
_STMT_PREV = {"fiscal_year": 2023, "fiscal_period": "annual", "period_end_date": "2023-12-31"}
_RATIO = {"factor_date": "2024-12-31", "price_to_earnings": 18.0}
_FCF_OK = {"direct_fcf_status": "positive", "base_fcf": 5_000_000.0, "fcf_source": "direct_fcf"}
_DIST = [{"source": "dcf_base", "method": "dcf", "value": 100.0, "weight": 0.5}]


_SENTINEL = object()  # distinguishes "not provided" from explicit None


def _call(
    annual_statements: Any = _SENTINEL,
    ratio_rows: Any = _SENTINEL,
    current_price: Any = 100.0,
    diluted_shares: Any = 50_000_000.0,
    fcf_data: Any = _SENTINEL,
    terminal_growth: float = 0.02,
    wacc: float = 0.09,
    distribution: Any = _SENTINEL,
) -> dict[str, Any]:
    """Call _build_diagnostics with valid defaults; individual params override.

    Use the sentinel to distinguish "caller wants the default" from "caller
    explicitly passes None" (which is a meaningful value for fcf_data etc.).
    """
    return _build_diagnostics(
        annual_statements=annual_statements if annual_statements is not _SENTINEL else [_STMT, _STMT_PREV],
        ratio_rows=ratio_rows if ratio_rows is not _SENTINEL else [_RATIO],
        current_price=current_price,
        diluted_shares=diluted_shares,
        fcf_data=fcf_data if fcf_data is not _SENTINEL else _FCF_OK,
        terminal_growth=terminal_growth,
        wacc=wacc,
        distribution=distribution if distribution is not _SENTINEL else list(_DIST),
    )


class TestBuildDiagnosticsStatus:
    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_valid_minimal_input_produces_ok_status(self):
        result = _call()
        assert result["valuation_status"] == "ok"
        assert result["freshness_flag"] == "ok"
        assert result["data_quality_flag"] == "ok"
        assert result["blockers"] == []
        assert result["warnings"] == []

    # ------------------------------------------------------------------
    # diluted_shares blockers
    # ------------------------------------------------------------------

    def test_none_shares_produces_partial_status_with_blocker(self):
        result = _call(diluted_shares=None)
        assert result["valuation_status"] == "partial"
        assert "missing_shares_outstanding" in result["blockers"]

    def test_zero_shares_treated_as_missing(self):
        result = _call(diluted_shares=0.0)
        assert "missing_shares_outstanding" in result["blockers"]

    def test_positive_shares_does_not_produce_blocker(self):
        result = _call(diluted_shares=1.0)
        assert "missing_shares_outstanding" not in result["blockers"]

    # ------------------------------------------------------------------
    # statement blockers / warnings
    # ------------------------------------------------------------------

    def test_empty_statements_produces_missing_statements_blocker(self):
        result = _call(annual_statements=[])
        assert "missing_statements" in result["blockers"]

    def test_empty_statements_produces_missing_inputs_freshness(self):
        result = _call(annual_statements=[])
        assert result["freshness_flag"] == "missing_inputs"

    def test_single_statement_produces_warning_not_blocker(self):
        result = _call(annual_statements=[_STMT])
        assert "limited_statement_history" in result["warnings"]
        assert "missing_statements" not in result["blockers"]

    def test_two_statements_produces_no_statement_warning(self):
        result = _call(annual_statements=[_STMT, _STMT_PREV])
        assert "limited_statement_history" not in result["warnings"]
        assert "missing_statements" not in result["blockers"]

    # ------------------------------------------------------------------
    # current_price blockers
    # ------------------------------------------------------------------

    def test_none_price_produces_blocker_and_missing_inputs_freshness(self):
        result = _call(current_price=None)
        assert "missing_latest_price" in result["blockers"]
        assert result["freshness_flag"] == "missing_inputs"

    def test_zero_price_produces_missing_price_blocker(self):
        result = _call(current_price=0.0)
        assert "missing_latest_price" in result["blockers"]

    def test_positive_price_does_not_produce_blocker(self):
        result = _call(current_price=1.0)
        assert "missing_latest_price" not in result["blockers"]

    # ------------------------------------------------------------------
    # ratio_rows blockers / warnings
    # ------------------------------------------------------------------

    def test_empty_ratio_rows_produces_blocker_and_multiples_warning(self):
        result = _call(ratio_rows=[])
        assert "missing_ratio_factor_history" in result["blockers"]
        assert "multiples_unavailable" in result["warnings"]

    def test_nonempty_ratio_rows_produces_no_ratio_blocker(self):
        result = _call(ratio_rows=[_RATIO])
        assert "missing_ratio_factor_history" not in result["blockers"]

    # ------------------------------------------------------------------
    # FCF blockers / warnings
    # ------------------------------------------------------------------

    def test_none_fcf_data_produces_missing_fcf_blocker(self):
        result = _call(fcf_data=None)
        assert "missing_fcf" in result["blockers"]
        assert "dcf_unavailable" in result["warnings"]

    def test_negative_fcf_status_produces_blocker_and_warning(self):
        result = _call(fcf_data={"direct_fcf_status": "negative", "base_fcf": -1_000.0, "fcf_source": "direct_fcf"})
        assert "negative_direct_fcf" in result["blockers"]
        assert "dcf_unavailable" in result["warnings"]

    def test_zero_fcf_status_produces_zero_fcf_blocker(self):
        result = _call(fcf_data={"direct_fcf_status": "zero", "base_fcf": 0.0, "fcf_source": "direct_fcf"})
        assert "zero_direct_fcf" in result["blockers"]
        assert "dcf_unavailable" in result["warnings"]

    def test_none_base_fcf_with_non_negative_status_produces_missing_fcf_blocker(self):
        result = _call(fcf_data={"direct_fcf_status": "positive", "base_fcf": None, "fcf_source": "direct_fcf"})
        assert "missing_fcf" in result["blockers"]
        assert "dcf_unavailable" in result["warnings"]

    def test_synthetic_fcf_source_produces_warning_not_blocker(self):
        result = _call(fcf_data={"direct_fcf_status": "estimated", "base_fcf": 1_000.0, "fcf_source": "synthetic_fcff"})
        assert "dcf_uses_synthetic_fcff" in result["warnings"]
        assert "missing_fcf" not in result["blockers"]

    # ------------------------------------------------------------------
    # terminal_growth vs WACC
    # ------------------------------------------------------------------

    def test_terminal_growth_equal_to_wacc_produces_blocker(self):
        result = _call(terminal_growth=0.09, wacc=0.09)
        assert "invalid_terminal_growth_gte_discount_rate" in result["blockers"]

    def test_terminal_growth_exceeds_wacc_produces_blocker(self):
        result = _call(terminal_growth=0.10, wacc=0.09)
        assert "invalid_terminal_growth_gte_discount_rate" in result["blockers"]

    def test_terminal_growth_below_wacc_does_not_produce_blocker(self):
        result = _call(terminal_growth=0.02, wacc=0.09)
        assert "invalid_terminal_growth_gte_discount_rate" not in result["blockers"]

    # ------------------------------------------------------------------
    # distribution-driven valuation_status
    # ------------------------------------------------------------------

    def test_empty_distribution_produces_blocked_status_and_insufficient_quality(self):
        result = _call(distribution=[])
        assert result["valuation_status"] == "blocked"
        assert result["data_quality_flag"] == "insufficient"

    def test_nonempty_distribution_with_no_blockers_produces_ok_status(self):
        result = _call(distribution=list(_DIST))
        assert result["valuation_status"] == "ok"

    def test_nonempty_distribution_with_blockers_produces_partial_status(self):
        # missing shares → blocker but distribution has values → partial
        result = _call(diluted_shares=None, distribution=list(_DIST))
        assert result["valuation_status"] == "partial"

    # ------------------------------------------------------------------
    # Output structure guarantees
    # ------------------------------------------------------------------

    def test_all_required_keys_present(self):
        result = _call()
        assert set(result.keys()) == {
            "valuation_status",
            "freshness_flag",
            "data_quality_flag",
            "blockers",
            "warnings",
        }

    def test_blockers_list_is_sorted(self):
        # Trigger several blockers simultaneously and confirm sort order
        result = _call(diluted_shares=None, current_price=None, annual_statements=[])
        assert result["blockers"] == sorted(result["blockers"])

    def test_warnings_list_is_sorted(self):
        result = _call(annual_statements=[_STMT], ratio_rows=[])
        assert result["warnings"] == sorted(result["warnings"])

    def test_no_duplicate_blockers(self):
        result = _call(diluted_shares=None, current_price=None, annual_statements=[])
        assert len(result["blockers"]) == len(set(result["blockers"]))

    def test_no_duplicate_warnings(self):
        result = _call(annual_statements=[_STMT], ratio_rows=[])
        assert len(result["warnings"]) == len(set(result["warnings"]))


# ---------------------------------------------------------------------------
# _weighted_percentiles — correctness assertions
# ---------------------------------------------------------------------------


class TestWeightedPercentiles:
    def _uniform(self, values: list[float]) -> list[dict[str, Any]]:
        return [{"value": v, "weight": 1.0} for v in values]

    def test_empty_distribution_returns_all_none(self):
        result = _weighted_percentiles([])
        assert all(v is None for v in result.values())

    def test_returns_all_five_percentile_keys(self):
        result = _weighted_percentiles(self._uniform([50.0]))
        assert set(result.keys()) == {"iv_p10", "iv_p25", "iv_p50", "iv_p75", "iv_p90"}

    def test_single_point_all_percentiles_equal_that_value(self):
        result = _weighted_percentiles([{"value": 42.0, "weight": 1.0}])
        assert result["iv_p10"] == pytest.approx(42.0)
        assert result["iv_p25"] == pytest.approx(42.0)
        assert result["iv_p50"] == pytest.approx(42.0)
        assert result["iv_p75"] == pytest.approx(42.0)
        assert result["iv_p90"] == pytest.approx(42.0)

    def test_five_equal_weight_points_produce_expected_discrete_percentiles(self):
        # values: [10, 20, 30, 40, 50], equal weights, total=5
        # Algorithm: pick smallest item where cumulative weight >= target × total
        # p10 → 0.5: item[0] weight=1 ≥ 0.5 → 10
        # p25 → 1.25: items 0+1=2 ≥ 1.25 → 20
        # p50 → 2.5: items 0+1+2=3 ≥ 2.5 → 30
        # p75 → 3.75: items 0+1+2+3=4 ≥ 3.75 → 40
        # p90 → 4.5: items 0+1+2+3=4 < 4.5, item[4]=5 ≥ 4.5 → 50
        result = _weighted_percentiles(self._uniform([10.0, 20.0, 30.0, 40.0, 50.0]))
        assert result["iv_p10"] == pytest.approx(10.0)
        assert result["iv_p25"] == pytest.approx(20.0)
        assert result["iv_p50"] == pytest.approx(30.0)
        assert result["iv_p75"] == pytest.approx(40.0)
        assert result["iv_p90"] == pytest.approx(50.0)

    def test_percentiles_are_monotonically_non_decreasing(self):
        result = _weighted_percentiles(self._uniform([100.0, 200.0, 50.0, 300.0, 150.0]))
        ordered = [result["iv_p10"], result["iv_p25"], result["iv_p50"], result["iv_p75"], result["iv_p90"]]
        for a, b in zip(ordered, ordered[1:]):
            assert a <= b

    def test_heavy_weight_on_low_value_shifts_median_toward_it(self):
        # 9× weight on 10.0 vs 1× weight on 100.0 → p50 should be 10.0
        dist = [{"value": 10.0, "weight": 9.0}, {"value": 100.0, "weight": 1.0}]
        result = _weighted_percentiles(dist)
        assert result["iv_p50"] == pytest.approx(10.0)

    def test_heavy_weight_on_high_value_shifts_median_toward_it(self):
        dist = [{"value": 10.0, "weight": 1.0}, {"value": 100.0, "weight": 9.0}]
        result = _weighted_percentiles(dist)
        assert result["iv_p50"] == pytest.approx(100.0)

    def test_unsorted_input_produces_same_result_as_sorted(self):
        # The implementation sorts internally; input order must not matter
        sorted_input = self._uniform([10.0, 20.0, 30.0])
        unsorted_input = self._uniform([30.0, 10.0, 20.0])
        assert _weighted_percentiles(sorted_input) == _weighted_percentiles(unsorted_input)

    def test_three_point_distribution_p50_is_middle_value(self):
        result = _weighted_percentiles(self._uniform([50.0, 100.0, 200.0]))
        assert result["iv_p50"] == pytest.approx(100.0)

    def test_zero_total_weight_returns_all_none(self):
        dist = [{"value": 50.0, "weight": 0.0}, {"value": 100.0, "weight": 0.0}]
        result = _weighted_percentiles(dist)
        assert all(v is None for v in result.values())
