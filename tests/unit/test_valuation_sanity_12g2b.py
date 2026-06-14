"""Phase 12G Slice 2B: valuation sanity core diagnostics tests."""
from __future__ import annotations

from typing import Any

from investment_app.valuation.scenarios import _build_diagnostics


_STMT = {"fiscal_year": 2024, "fiscal_period": "annual", "period_end_date": "2024-12-31"}
_STMT_PREV = {"fiscal_year": 2023, "fiscal_period": "annual", "period_end_date": "2023-12-31"}
_RATIO = {"factor_date": "2024-12-31", "price_to_earnings": 18.0}
_FCF_OK = {"direct_fcf_status": "positive", "base_fcf": 5_000_000.0, "fcf_source": "direct_fcf"}
_SENTINEL = object()


def _dist(values: list[float], methods: list[str] | None = None) -> list[dict[str, Any]]:
    if methods is None:
        methods = ["dcf"] * len(values)
    out: list[dict[str, Any]] = []
    for i, value in enumerate(values):
        out.append(
            {
                "source": f"src_{i}",
                "method": methods[i],
                "value": value,
                "weight": 1.0 / max(1, len(values)),
            }
        )
    return out


def _call(
    *,
    distribution: list[dict[str, Any]] | None = None,
    method_estimates: dict[str, float] | None = None,
    dcf_output: dict[str, Any] | None = None,
    current_price: float | None = 100.0,
    iv_p10: float | None = 80.0,
    iv_p25: float | None = 90.0,
    iv_p50: float | None = 100.0,
    iv_p75: float | None = 120.0,
    iv_p90: float | None = 140.0,
    uncertainty_width: float | None = 0.35,
    fcf_data: dict[str, Any] | None = _SENTINEL,
    terminal_growth: float = 0.02,
    wacc: float = 0.09,
) -> dict[str, Any]:
    return _build_diagnostics(
        annual_statements=[_STMT, _STMT_PREV],
        ratio_rows=[_RATIO],
        current_price=current_price,
        diluted_shares=10_000_000.0,
        fcf_data=_FCF_OK if fcf_data is _SENTINEL else fcf_data,
        terminal_growth=terminal_growth,
        wacc=wacc,
        distribution=distribution if distribution is not None else _dist([80.0, 100.0, 120.0], ["dcf", "dcf", "multiples"]),
        uncertainty_width=uncertainty_width,
        iv_p10=iv_p10,
        iv_p25=iv_p25,
        iv_p50=iv_p50,
        iv_p75=iv_p75,
        iv_p90=iv_p90,
        method_estimates=method_estimates if method_estimates is not None else {"dcf": 105.0, "multiples": 100.0},
        dcf_output=dcf_output,
    )


def test_usable_when_ordered_finite_and_multi_method() -> None:
    diagnostics = _call()
    assert diagnostics["valuation_sanity_status"] == "usable"
    assert diagnostics["valuation_evidence_usable"] is True
    assert diagnostics["valuation_method_coverage"] == "multi_method"


def test_high_uncertainty_for_wide_but_plausible_iv_span() -> None:
    diagnostics = _call(iv_p10=40.0, iv_p25=60.0, iv_p50=100.0, iv_p75=140.0, iv_p90=170.0)
    assert diagnostics["iv_range_ratio_p90_p10"] == 4.25
    assert diagnostics["valuation_sanity_status"] == "high_uncertainty"
    assert "wide_intrinsic_value_span" in diagnostics["valuation_sanity_reason_codes"]


def test_unreliable_for_severe_iv_span() -> None:
    diagnostics = _call(iv_p10=10.0, iv_p25=20.0, iv_p50=40.0, iv_p75=60.0, iv_p90=80.0)
    assert diagnostics["iv_range_ratio_p90_p10"] == 8.0
    assert diagnostics["valuation_sanity_status"] == "unreliable"


def test_model_failure_for_non_monotonic_percentiles() -> None:
    diagnostics = _call(iv_p10=80.0, iv_p25=90.0, iv_p50=120.0, iv_p75=110.0, iv_p90=140.0)
    assert diagnostics["valuation_sanity_status"] == "model_failure"
    assert "non_monotonic_percentiles" in diagnostics["valuation_sanity_reason_codes"]


def test_model_failure_for_missing_finite_percentiles() -> None:
    diagnostics = _call(iv_p10=80.0, iv_p25=None, iv_p50=100.0, iv_p75=120.0, iv_p90=140.0)
    assert diagnostics["valuation_sanity_status"] == "model_failure"
    assert "missing_finite_percentiles" in diagnostics["valuation_sanity_reason_codes"]


def test_high_uncertainty_for_missing_multiples_with_dcf() -> None:
    diagnostics = _call(method_estimates={"dcf": 100.0})
    assert diagnostics["valuation_method_coverage"] == "dcf_only"
    assert diagnostics["valuation_sanity_status"] == "high_uncertainty"
    assert "missing_multiples_component" in diagnostics["valuation_sanity_reason_codes"]


def test_unreliable_for_missing_dcf_and_multiples() -> None:
    diagnostics = _call(method_estimates={"ddm": 100.0})
    assert diagnostics["valuation_method_coverage"] == "ddm_only"
    assert diagnostics["valuation_sanity_status"] == "unreliable"
    assert diagnostics["valuation_signal_influence_blocked"] is True


def test_unreliable_for_severe_dcf_multiples_divergence() -> None:
    diagnostics = _call(method_estimates={"dcf": 350.0, "multiples": 90.0})
    assert diagnostics["dcf_multiples_gap_ratio"] > 3.5
    assert diagnostics["valuation_sanity_status"] == "unreliable"


def test_high_uncertainty_for_terminal_dominance() -> None:
    dcf_output = {
        "scenarios": {
            "base": {
                "pv_terminal_value": 90.0,
                "enterprise_value": 100.0,
            }
        }
    }
    diagnostics = _call(dcf_output=dcf_output)
    assert diagnostics["max_terminal_value_share"] == 0.9
    assert diagnostics["valuation_sanity_status"] == "high_uncertainty"


def test_unreliable_for_severe_terminal_dominance() -> None:
    dcf_output = {
        "scenarios": {
            "base": {
                "pv_terminal_value": 98.0,
                "enterprise_value": 100.0,
            }
        }
    }
    diagnostics = _call(dcf_output=dcf_output)
    assert diagnostics["valuation_sanity_status"] == "unreliable"


def test_model_failure_for_invalid_terminal_spread() -> None:
    diagnostics = _call(terminal_growth=0.09, wacc=0.09)
    assert diagnostics["valuation_sanity_status"] == "model_failure"


def test_unreliable_for_negative_or_zero_fcf_path_when_distribution_exists() -> None:
    diagnostics = _call(fcf_data={"direct_fcf_status": "negative", "base_fcf": -1.0, "fcf_source": "direct_negative"})
    assert diagnostics["valuation_sanity_status"] == "unreliable"
    assert "negative_or_zero_fcf_path" in diagnostics["valuation_sanity_reason_codes"]


def test_high_uncertainty_for_extreme_uncertainty_category_alone() -> None:
    diagnostics = _call(uncertainty_width=1.26)
    assert diagnostics["uncertainty_category"] == "extreme"
    assert diagnostics["valuation_sanity_status"] == "high_uncertainty"
