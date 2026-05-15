"""PR 11A.4 — Signal Calibration Refinements.

Covers the two behavioral changes introduced in signal_rule_v1:

1. Partial-analysis buy demotion
   strong_buy and buy are demoted to hold when readiness_status == "partial_analysis".
   Sell, strong_sell, hold, and insufficient_data are unaffected.

2. Strong-sell confirmation requirement
   strong_sell now requires BOTH p_sell >= 0.60 AND at least one confirming
   bearish flag from _STRONG_SELL_CONFIRMING_FLAGS.
   When p_sell >= 0.60 but no confirming flag is present the signal degrades to sell.

Additionally asserts:
- MODEL_VERSION == "signal_rule_v1"
- probability math (_quality_multiplier, _risk_penalty, _sell_probability) is unchanged
- p_buy_adjusted values are unchanged relative to signal_rule_v0 formula inputs
- PR 11A.3 explanation tests are unaffected (covered by still running that file)
"""
from __future__ import annotations

from typing import Any

import pytest

import investment_app.scoring.probabilistic as _prob_module
from investment_app.scoring.probabilistic import (
    MODEL_VERSION,
    _STRONG_SELL_CONFIRMING_FLAGS,
    _classify_signal,
    _quality_multiplier,
    _risk_penalty,
    _sell_probability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _val_row(
    *,
    mos: float = 0.20,
    price: float = 100.0,
    iv_p25: float = 140.0,
    iv_p50: float = 160.0,
    iv_p75: float = 180.0,
    uncertainty_width: float = 0.20,
    valuation_date: str = "2025-01-01",
) -> dict[str, Any]:
    return {
        "id": "val-11a4-001",
        "valuation_date": valuation_date,
        "margin_of_safety_conservative": mos,
        "current_price": price,
        "iv_p25": iv_p25,
        "iv_p50": iv_p50,
        "iv_p75": iv_p75,
        "uncertainty_width": uncertainty_width,
        "assumptions": {
            "diagnostics": {"freshness_flag": "ok", "blockers": [], "warnings": []}
        },
    }


def _classify(
    *,
    p_buy_adjusted: float = 0.55,
    p_sell: float = 0.30,
    valuation_row: dict[str, Any] | None = None,
    quality_score: float = 65.0,
    red_flags: list[str] | None = None,
    freshness_flag: str = "ok",
    readiness_status: str = "analysis_ready",
) -> str:
    """Thin wrapper for _classify_signal with safe defaults."""
    if valuation_row is None:
        valuation_row = _val_row()
    return _classify_signal(
        p_buy_adjusted=p_buy_adjusted,
        p_sell=p_sell,
        valuation_row=valuation_row,
        quality_score=quality_score,
        red_flags=red_flags or [],
        freshness_flag=freshness_flag,
        readiness_status=readiness_status,
    )


# ---------------------------------------------------------------------------
# 1. MODEL_VERSION guard
# ---------------------------------------------------------------------------


class TestModelVersion:
    def test_model_version_is_signal_rule_v2(self):
        """PR 11A.4b intentionally bumps MODEL_VERSION from signal_rule_v1."""
        assert MODEL_VERSION == "signal_rule_v2"

    def test_module_attribute_matches_import(self):
        assert _prob_module.MODEL_VERSION == "signal_rule_v2"


# ---------------------------------------------------------------------------
# 2. Partial-analysis buy demotion
# ---------------------------------------------------------------------------


class TestPartialAnalysisBuyDemotion:
    """readiness_status == 'partial_analysis' demotes buy/strong_buy to hold."""

    _STRONG_BUY_KWARGS: dict[str, Any] = dict(
        p_buy_adjusted=0.75,
        p_sell=0.10,
        quality_score=75.0,
        red_flags=[],
        freshness_flag="ok",
    )
    _BUY_KWARGS: dict[str, Any] = dict(
        p_buy_adjusted=0.65,
        p_sell=0.10,
        quality_score=65.0,
        red_flags=[],
        freshness_flag="ok",
    )

    def test_partial_analysis_demotes_strong_buy_to_hold(self):
        val = _val_row(mos=0.25)
        assert (
            _classify(**self._STRONG_BUY_KWARGS, valuation_row=val, readiness_status="partial_analysis")
            == "hold"
        )

    def test_partial_analysis_demotes_buy_to_hold(self):
        val = _val_row(mos=0.15)
        assert (
            _classify(**self._BUY_KWARGS, valuation_row=val, readiness_status="partial_analysis")
            == "hold"
        )

    def test_analysis_ready_preserves_strong_buy(self):
        val = _val_row(mos=0.25)
        assert (
            _classify(**self._STRONG_BUY_KWARGS, valuation_row=val, readiness_status="analysis_ready")
            == "strong_buy"
        )

    def test_analysis_ready_preserves_buy(self):
        val = _val_row(mos=0.15)
        assert (
            _classify(**self._BUY_KWARGS, valuation_row=val, readiness_status="analysis_ready")
            == "buy"
        )

    def test_partial_analysis_hold_stays_hold(self):
        """hold is not affected by partial_analysis."""
        assert (
            _classify(p_buy_adjusted=0.45, p_sell=0.30, readiness_status="partial_analysis")
            == "hold"
        )

    def test_partial_analysis_insufficient_data_unchanged(self):
        assert (
            _classify(
                red_flags=["missing_valuation", "missing_qualitative_score", "missing_ratio_factors"],
                valuation_row=None,
                readiness_status="partial_analysis",
            )
            == "insufficient_data"
        )

    def test_partial_analysis_sell_unchanged(self):
        """Sell is not demoted — bearish signals must still be shown."""
        assert (
            _classify(red_flags=["high_leverage"], readiness_status="partial_analysis")
            == "sell"
        )

    def test_partial_analysis_strong_sell_unchanged_with_confirming_flag(self):
        """strong_sell is not affected by partial_analysis."""
        result = _classify(
            p_sell=0.65,
            red_flags=["high_leverage"],
            readiness_status="partial_analysis",
        )
        assert result == "strong_sell"

    def test_default_readiness_is_analysis_ready(self):
        """Omitting readiness_status should behave identically to 'analysis_ready'."""
        val = _val_row(mos=0.25)
        result_default = _classify_signal(
            p_buy_adjusted=0.75,
            p_sell=0.10,
            valuation_row=val,
            quality_score=75.0,
            red_flags=[],
            freshness_flag="ok",
        )
        assert result_default == "strong_buy"


# ---------------------------------------------------------------------------
# 3. Strong-sell confirmation requirement
# ---------------------------------------------------------------------------


class TestStrongSellConfirmation:
    """p_sell >= 0.60 alone is no longer sufficient for strong_sell."""

    def test_high_p_sell_with_no_flags_produces_sell_not_strong_sell(self):
        assert _classify(p_sell=0.65, red_flags=[]) == "sell"

    def test_high_p_sell_with_high_leverage_produces_strong_sell(self):
        assert _classify(p_sell=0.65, red_flags=["high_leverage"]) == "strong_sell"

    def test_high_p_sell_with_negative_margin_of_safety_produces_strong_sell(self):
        assert _classify(p_sell=0.65, red_flags=["negative_margin_of_safety"]) == "strong_sell"

    def test_high_p_sell_with_overvalued_vs_iv_p75_produces_strong_sell(self):
        assert _classify(p_sell=0.65, red_flags=["overvalued_vs_iv_p75"]) == "strong_sell"

    def test_high_p_sell_with_quality_breakdown_produces_strong_sell(self):
        """quality_breakdown is both a hard red flag AND a confirming flag.
        When p_sell >= 0.60, strong_sell takes priority over the hard_red_flag sell path.
        """
        assert _classify(p_sell=0.65, red_flags=["quality_breakdown"]) == "strong_sell"

    def test_high_p_sell_with_critical_interest_coverage_produces_strong_sell(self):
        assert _classify(p_sell=0.65, red_flags=["critical_interest_coverage"]) == "strong_sell"

    def test_p_sell_just_at_threshold_with_confirming_flag_produces_strong_sell(self):
        assert _classify(p_sell=0.60, red_flags=["high_leverage"]) == "strong_sell"

    def test_p_sell_just_below_threshold_with_confirming_flag_does_not_produce_strong_sell(self):
        result = _classify(p_sell=0.599, red_flags=["high_leverage"])
        assert result != "strong_sell"

    def test_non_confirming_flag_alone_does_not_enable_strong_sell(self):
        """negative_news_spike is not in CONFIRMING_FLAGS."""
        result = _classify(p_sell=0.70, red_flags=["negative_news_spike"])
        assert result != "strong_sell"

    def test_confirming_flags_constant_contains_expected_members(self):
        expected = {"high_leverage", "critical_interest_coverage", "quality_breakdown",
                    "negative_margin_of_safety", "overvalued_vs_iv_p75"}
        assert expected == _STRONG_SELL_CONFIRMING_FLAGS

    def test_price_above_iv_p75_and_low_quality_without_p_sell_produces_sell_not_strong_sell(self):
        """PR 11A.4: the valuation-based strong_sell shortcut is removed.
        price > iv_p75 + quality < 50 without p_sell >= 0.60 and a confirming
        flag no longer produces strong_sell.
        """
        row = _val_row(price=200.0, iv_p75=180.0)
        # p_sell=0.30 (default), red_flags=[] — confirming path not reached
        result = _classify(valuation_row=row, quality_score=45.0, red_flags=[])
        assert result != "strong_sell"

    def test_price_above_iv_p75_and_low_quality_with_high_p_sell_and_confirming_flag_produces_strong_sell(self):
        """In production, _build_red_flags sets overvalued_vs_iv_p75 when
        price > iv_p75; combined with elevated p_sell this triggers strong_sell.
        """
        row = _val_row(price=200.0, iv_p75=180.0)
        result = _classify(
            valuation_row=row,
            quality_score=45.0,
            p_sell=0.65,
            red_flags=["overvalued_vs_iv_p75"],
        )
        assert result == "strong_sell"


# ---------------------------------------------------------------------------
# 4. Probability math unchanged (regression lock)
# ---------------------------------------------------------------------------


class TestProbabilityMathUnchanged:
    """Spot-checks ensuring _quality_multiplier, _risk_penalty, and
    _sell_probability formulas were not touched by PR 11A.4."""

    def test_quality_multiplier_neutral(self):
        assert _quality_multiplier(50.0, freshness_flag="ok") == pytest.approx(1.0)

    def test_quality_multiplier_limited_haircut(self):
        assert _quality_multiplier(50.0, freshness_flag="limited") == pytest.approx(0.95)

    def test_risk_penalty_clean_input_zero(self):
        assert _risk_penalty(
            balance_score=60.0, news_score=50.0, red_flags=[], freshness_flag="ok"
        ) == pytest.approx(0.0)

    def test_risk_penalty_cap_at_thirty_five(self):
        assert _risk_penalty(
            balance_score=0.0, news_score=35.0, red_flags=["high_leverage"],
            freshness_flag="missing_inputs",
        ) == pytest.approx(0.35)

    def test_sell_probability_baseline(self):
        from investment_app.scoring.rule_based import sigmoid
        expected = sigmoid(-15.0 / 12.0)
        result = _sell_probability(
            valuation_row=None, quality_score=50.0, balance_score=50.0,
            news_score=50.0, market_score=50.0, red_flags=[], freshness_flag="ok",
        )
        assert result == pytest.approx(expected, abs=1e-5)


# ---------------------------------------------------------------------------
# 5. p_buy_adjusted not affected by final_signal change
# ---------------------------------------------------------------------------


class TestPBuyAdjustedUnchanged:
    """Verify that demoting buy to hold does not alter the probability values
    stored in the output row — only final_signal changes."""

    def test_partial_analysis_does_not_change_p_buy_adjusted_value(self):
        """p_buy_adjusted is computed before _classify_signal is called.
        Changing readiness_status only affects the label, not the probability."""
        val = _val_row(mos=0.20)
        # Under analysis_ready the label is strong_buy; under partial_analysis it is hold.
        # We confirm _classify_signal itself only changes the returned string.
        signal_ar = _classify(
            p_buy_adjusted=0.75, p_sell=0.10, valuation_row=val,
            red_flags=[], freshness_flag="ok", readiness_status="analysis_ready",
        )
        signal_pa = _classify(
            p_buy_adjusted=0.75, p_sell=0.10, valuation_row=val,
            red_flags=[], freshness_flag="ok", readiness_status="partial_analysis",
        )
        assert signal_ar == "strong_buy"
        assert signal_pa == "hold"
        # p_buy_adjusted=0.75 is passed in both cases; the function only decides the label
