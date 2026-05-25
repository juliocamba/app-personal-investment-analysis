"""Focused signal_rule_v3 calibration tests.

These tests cover midpoint fair-value anchoring, uncertainty-adjusted sell
bands, and stricter strong_sell confirmation without provider or DB access.
"""
from __future__ import annotations

from typing import Any

from investment_app.scoring.probabilistic import (
    MODEL_VERSION,
    _build_red_flags,
    _classify_signal,
    _sell_probability,
    _valuation_position_bucket,
)


def _valuation(
    *,
    price: float = 100.0,
    iv_p10: float = 80.0,
    iv_p50: float = 100.0,
    iv_p75: float = 120.0,
    uncertainty_width: float = 0.20,
    mos: float | None = None,
) -> dict[str, Any]:
    if mos is None:
        mos = (iv_p10 - price) / price
    return {
        "id": "val-v3-001",
        "valuation_date": "2025-01-01",
        "iv_p10": iv_p10,
        "iv_p25": 90.0,
        "iv_p50": iv_p50,
        "iv_p75": iv_p75,
        "iv_p90": 140.0,
        "current_price": price,
        "margin_of_safety_conservative": mos,
        "uncertainty_width": uncertainty_width,
        "assumptions": {"diagnostics": {"freshness_flag": "ok", "blockers": [], "warnings": []}},
    }


def _classify(
    valuation_row: dict[str, Any],
    *,
    p_sell: float = 0.65,
    red_flags: list[str] | None = None,
    p_buy_adjusted: float = 0.30,
    quality_score: float = 65.0,
    freshness_flag: str = "ok",
    readiness_status: str = "analysis_ready",
) -> str:
    return _classify_signal(
        p_buy_adjusted=p_buy_adjusted,
        p_sell=p_sell,
        valuation_row=valuation_row,
        quality_score=quality_score,
        red_flags=red_flags or [],
        freshness_flag=freshness_flag,
        readiness_status=readiness_status,
    )


def _p_sell(valuation_row: dict[str, Any], *, red_flags: list[str] | None = None) -> float:
    return _sell_probability(
        valuation_row=valuation_row,
        quality_score=60.0,
        balance_score=60.0,
        news_score=50.0,
        market_score=50.0,
        red_flags=red_flags or [],
        freshness_flag="ok",
    )


def test_model_version_is_signal_rule_v3():
    assert MODEL_VERSION == "signal_rule_v3"


def test_slightly_above_iv_p75_without_independent_risk_is_not_strong_sell():
    val = _valuation(price=122.0, iv_p50=100.0, iv_p75=120.0, uncertainty_width=0.20)
    assert _classify(val, p_sell=0.65, red_flags=["overvalued_vs_iv_p75"]) == "sell"


def test_high_uncertainty_modest_overvaluation_is_not_strong_sell():
    val = _valuation(price=118.0, iv_p50=100.0, iv_p75=115.0, uncertainty_width=1.00)
    assert _valuation_position_bucket(val) == "modestly_overvalued"
    assert _classify(val, p_sell=0.65, red_flags=["overvalued_vs_iv_p75"]) == "sell"


def test_extreme_uncertainty_modest_overvaluation_is_not_strong_sell():
    val = _valuation(price=128.0, iv_p50=100.0, iv_p75=115.0, uncertainty_width=1.50)
    assert _valuation_position_bucket(val) == "modestly_overvalued"
    assert _classify(val, p_sell=0.65, red_flags=["overvalued_vs_iv_p75"]) == "sell"


def test_high_p_sell_with_only_valuation_red_flags_is_sell_not_strong_sell():
    val = _valuation(price=125.0, iv_p50=100.0, iv_p75=110.0, uncertainty_width=0.20)
    result = _classify(
        val,
        p_sell=0.65,
        red_flags=["negative_margin_of_safety", "overvalued_vs_iv_p75"],
    )
    assert result == "sell"


def test_severe_midpoint_premium_low_uncertainty_can_be_strong_sell():
    val = _valuation(price=132.0, iv_p50=100.0, iv_p75=115.0, uncertainty_width=0.20)
    assert _valuation_position_bucket(val) == "severely_overvalued"
    assert _classify(val, p_sell=_p_sell(val), red_flags=["overvalued_vs_iv_p75"]) == "strong_sell"


def test_severe_midpoint_premium_moderate_uncertainty_can_be_strong_sell():
    val = _valuation(price=145.0, iv_p50=100.0, iv_p75=120.0, uncertainty_width=0.60)
    assert _valuation_position_bucket(val) == "severely_overvalued"
    assert _classify(val, p_sell=_p_sell(val), red_flags=["overvalued_vs_iv_p75"]) == "strong_sell"


def test_extreme_uncertainty_valuation_only_evidence_is_capped_at_sell():
    val = _valuation(price=180.0, iv_p50=100.0, iv_p75=120.0, uncertainty_width=1.60)
    assert _valuation_position_bucket(val) == "modestly_overvalued"
    assert _classify(val, p_sell=0.80, red_flags=["overvalued_vs_iv_p75"]) == "sell"


def test_independent_hard_risk_plus_elevated_sell_pressure_can_be_strong_sell():
    val = _valuation(price=108.0, iv_p50=100.0, iv_p75=120.0, uncertainty_width=1.60)
    assert _classify(val, p_sell=0.65, red_flags=["high_leverage"]) == "strong_sell"


def test_sell_pressure_is_monotonic_across_midpoint_buckets():
    near = _valuation(price=103.0, iv_p50=100.0, uncertainty_width=0.20)
    modest = _valuation(price=112.0, iv_p50=100.0, uncertainty_width=0.20)
    severe = _valuation(price=132.0, iv_p50=100.0, uncertainty_width=0.20)

    assert _valuation_position_bucket(near) == "near_fair_value"
    assert _valuation_position_bucket(modest) == "modestly_overvalued"
    assert _valuation_position_bucket(severe) == "severely_overvalued"
    assert _p_sell(near) < _p_sell(modest) < _p_sell(severe)


def test_valuation_warnings_remain_visible_red_flags():
    val = _valuation(price=125.0, iv_p50=100.0, iv_p75=110.0, uncertainty_width=0.20)
    flags = _build_red_flags(
        valuation_row=val,
        qualitative_row={"final_quality_score": 65.0},
        ratio_row={"net_debt_to_ebitda": 1.0, "interest_coverage": 8.0},
        freshness_flag="ok",
    )
    assert "negative_margin_of_safety" in flags
    assert "overvalued_vs_iv_p75" in flags


def test_partial_analysis_buy_demotion_remains_unchanged():
    val = _valuation(price=100.0, iv_p10=130.0, iv_p50=170.0, iv_p75=190.0, mos=0.30)
    result = _classify(
        val,
        p_sell=0.10,
        p_buy_adjusted=0.75,
        red_flags=[],
        readiness_status="partial_analysis",
    )
    assert result == "hold"


def test_output_shape_remains_unchanged():
    from tests.unit.test_probabilistic_signal import (
        _COMPANY_ID,
        _FILING_10K,
        _PRICE_GOOD,
        _QUAL_GOOD,
        _RATIO_GOOD,
        _SIGNAL_DATE,
        _VALUATION_GOOD,
        _FakeSignalRepo,
    )
    from investment_app.scoring.probabilistic import compute_signal_run

    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert set(result.keys()) == {
        "company_id",
        "signal_date",
        "model_version",
        "valuation_run_id",
        "qualitative_score_id",
        "p_buy",
        "p_buy_adjusted",
        "p_sell",
        "final_signal",
        "uncertainty_penalty",
        "red_flags",
        "top_feature_contributors",
        "explanation",
        "freshness_flag",
    }
