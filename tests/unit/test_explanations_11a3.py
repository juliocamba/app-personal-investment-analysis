"""PR 11A.3 — Explanation redesign tests.

Verifies that build_signal_explanation() returns structured, plain-English
explanations without changing any signal/valuation/scoring logic.

Coverage:
  1.  HOLD — mixed signals (p_buy_adj and p_sell both elevated)
  2.  HOLD — buy probability just below threshold
  3.  HOLD — low confidence, missing core inputs
  4.  High uncertainty_width includes "Wide valuation range" wording
  5.  Low uncertainty_width does NOT include "Wide valuation range" wording
  6.  SELL with negative_margin_of_safety includes plain-English bearish reason
  7.  INSUFFICIENT_DATA with missing_valuation includes "valuation unavailable"
  8.  STRONG_BUY with positive MoS includes "conservative margin of safety"
  9.  BUY without quality ≥ 60 omits "supported by strong quality score"
  10. STRONG_SELL with quality_breakdown and high_leverage includes both labels
  11. Backward-compatible — call without uncertainty_width works
  12. MODEL_VERSION = "signal_rule_v0" unchanged
  13. Explanation length ≤ 300 characters for all covered cases
  14. Uncertainty note is NOT appended when uncertainty_width = 0.50 (boundary)

No network.  No Supabase.  No secrets.
"""
from __future__ import annotations

from typing import Any

import pytest

from investment_app.scoring.explanations import build_signal_explanation
from investment_app.scoring.probabilistic import MODEL_VERSION


# ---------------------------------------------------------------------------
# Minimal fixture helpers
# ---------------------------------------------------------------------------


def _val(*, mos: float = 0.20) -> dict[str, Any]:
    return {"margin_of_safety_conservative": mos, "current_price": 100.0}


def _call(
    *,
    final_signal: str,
    valuation_row: dict[str, Any] | None = None,
    quality_score: float = 55.0,
    balance_score: float = 55.0,
    freshness_flag: str = "ok",
    red_flags: list[str] | None = None,
    p_buy_adjusted: float = 0.45,
    p_sell: float = 0.35,
    uncertainty_width: float | None = None,
) -> str:
    return build_signal_explanation(
        final_signal=final_signal,
        valuation_row=valuation_row,
        quality_score=quality_score,
        balance_score=balance_score,
        freshness_flag=freshness_flag,
        red_flags=red_flags or [],
        p_buy_adjusted=p_buy_adjusted,
        p_sell=p_sell,
        uncertainty_width=uncertainty_width,
    )


# ---------------------------------------------------------------------------
# 1. MODEL_VERSION guard
# ---------------------------------------------------------------------------


class TestModelVersionUnchanged:
    def test_signal_model_version_is_signal_rule_v0(self):
        assert MODEL_VERSION == "signal_rule_v0"


# ---------------------------------------------------------------------------
# 2. HOLD sub-cases
# ---------------------------------------------------------------------------


class TestHoldExplanations:
    def test_mixed_signals_both_elevated(self):
        """p_buy_adj ≥ 0.50 and p_sell ≥ 0.50 → 'mixed signals'."""
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.55,
            p_sell=0.55,
        )
        assert "mixed signals" in result.lower()
        assert "buy and sell pressure" in result.lower()

    def test_just_below_buy_threshold(self):
        """p_buy_adj ≥ 0.55 but p_sell < 0.50 → 'just below threshold'."""
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.58,
            p_sell=0.30,
        )
        assert "just below threshold" in result.lower()
        assert "0.58" in result

    def test_low_confidence_missing_inputs(self):
        """freshness_flag=missing_inputs → 'missing core inputs'."""
        result = _call(
            final_signal="hold",
            freshness_flag="missing_inputs",
            p_buy_adjusted=0.30,
            p_sell=0.30,
        )
        assert "missing core inputs" in result.lower()
        assert "low confidence" in result.lower()

    def test_low_confidence_stale(self):
        """freshness_flag=stale → 'stale input data'."""
        result = _call(
            final_signal="hold",
            freshness_flag="stale",
            p_buy_adjusted=0.30,
            p_sell=0.30,
        )
        assert "stale input data" in result.lower()

    def test_insufficient_conviction_mid_range(self):
        """0.40 ≤ p_buy_adj < 0.55 → 'insufficient directional conviction'."""
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.45,
            p_sell=0.30,
        )
        assert "insufficient directional conviction" in result.lower()

    def test_hold_no_case(self):
        """p_buy_adj < 0.40 → 'no strong buy or sell case'."""
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.25,
            p_sell=0.20,
        )
        assert "no strong buy or sell case" in result.lower()

    def test_limited_evidence_hold(self):
        """freshness_flag='limited' → 'limited evidence' in explanation."""
        result = _call(
            final_signal="hold",
            freshness_flag="limited",
            p_buy_adjusted=0.30,
            p_sell=0.30,
        )
        assert "limited evidence" in result.lower()

    def test_limited_evidence_does_not_override_mixed_signals(self):
        """Mixed-signal condition (both >= 0.50) takes priority over limited."""
        result = _call(
            final_signal="hold",
            freshness_flag="limited",
            p_buy_adjusted=0.55,
            p_sell=0.55,
        )
        assert "mixed signals" in result.lower()
        assert "limited evidence" not in result.lower()

    def test_limited_evidence_does_not_override_near_buy(self):
        """Near-buy condition (p_buy_adj >= 0.55, p_sell < 0.50) takes priority over limited."""
        result = _call(
            final_signal="hold",
            freshness_flag="limited",
            p_buy_adjusted=0.58,
            p_sell=0.30,
        )
        assert "just below threshold" in result.lower()
        assert "limited evidence" not in result.lower()


# ---------------------------------------------------------------------------
# 3. SELL / STRONG_SELL sub-cases
# ---------------------------------------------------------------------------


class TestSellExplanations:
    def test_sell_negative_margin_of_safety_plain_english(self):
        """SELL with negative_margin_of_safety → 'price above intrinsic value'."""
        result = _call(
            final_signal="sell",
            red_flags=["negative_margin_of_safety", "quality_breakdown"],
            p_buy_adjusted=0.20,
            p_sell=0.70,
        )
        assert "price above intrinsic value" in result.lower()
        assert result.upper().startswith("SELL")

    def test_sell_high_leverage_plain_english(self):
        result = _call(
            final_signal="sell",
            red_flags=["high_leverage"],
            p_sell=0.55,
        )
        assert "high financial leverage" in result.lower()

    def test_strong_sell_quality_breakdown_and_leverage(self):
        result = _call(
            final_signal="strong_sell",
            red_flags=["quality_breakdown", "high_leverage"],
            p_sell=0.65,
        )
        assert "quality score very low" in result.lower()
        assert "strong sell" in result.lower()

    def test_sell_negative_fcf_plain_english(self):
        result = _call(
            final_signal="sell",
            red_flags=["negative_direct_fcf"],
            p_sell=0.55,
        )
        assert "negative free cash flow" in result.lower()

    def test_sell_no_named_flags_uses_sell_pressure(self):
        result = _call(
            final_signal="sell",
            red_flags=[],
            p_sell=0.62,
            valuation_row={"margin_of_safety_conservative": -0.05},
        )
        # mos < 0 → "price above intrinsic value"
        assert "price above intrinsic value" in result.lower()

    def test_sell_no_flags_no_negative_mos_shows_probability(self):
        result = _call(
            final_signal="sell",
            red_flags=[],
            p_sell=0.62,
            valuation_row=None,
        )
        assert "elevated sell pressure" in result.lower()


# ---------------------------------------------------------------------------
# 4. BUY / STRONG_BUY sub-cases
# ---------------------------------------------------------------------------


class TestBuyExplanations:
    def test_strong_buy_positive_mos_includes_mos_text(self):
        """STRONG_BUY must mention 'conservative margin of safety'."""
        result = _call(
            final_signal="strong_buy",
            valuation_row=_val(mos=0.30),
            quality_score=70.0,
            red_flags=[],
            p_buy_adjusted=0.75,
            p_sell=0.20,
        )
        assert "conservative margin of safety" in result.lower()
        assert "30%" in result

    def test_strong_buy_high_quality_includes_quality_text(self):
        result = _call(
            final_signal="strong_buy",
            valuation_row=_val(mos=0.20),
            quality_score=72.0,
            red_flags=[],
            p_buy_adjusted=0.75,
        )
        assert "strong quality score" in result.lower()

    def test_strong_buy_no_red_flags_includes_no_major_red_flags(self):
        result = _call(
            final_signal="strong_buy",
            valuation_row=_val(mos=0.20),
            quality_score=72.0,
            red_flags=[],
            p_buy_adjusted=0.75,
        )
        assert "no major red flags" in result.lower()

    def test_buy_low_quality_omits_strong_quality_text(self):
        """quality_score < 60.0 → 'supported by strong quality score' absent."""
        result = _call(
            final_signal="buy",
            valuation_row=_val(mos=0.15),
            quality_score=55.0,
            red_flags=[],
            p_buy_adjusted=0.62,
        )
        assert "conservative margin of safety" in result.lower()
        assert "strong quality score" not in result.lower()

    def test_buy_no_valuation_row_shows_probability(self):
        result = _call(
            final_signal="buy",
            valuation_row=None,
            p_buy_adjusted=0.65,
        )
        assert "buy probability" in result.lower()
        assert "0.65" in result


# ---------------------------------------------------------------------------
# 5. INSUFFICIENT_DATA
# ---------------------------------------------------------------------------


class TestInsufficientDataExplanations:
    def test_missing_valuation_flag_gives_valuation_unavailable(self):
        result = _call(
            final_signal="insufficient_data",
            red_flags=["missing_valuation", "missing_qualitative_score", "missing_ratio_factors"],
        )
        assert "valuation unavailable" in result.lower()
        assert "margin of safety" in result.lower()

    def test_no_missing_valuation_flag_gives_core_inputs_text(self):
        result = _call(
            final_signal="insufficient_data",
            red_flags=["missing_qualitative_score"],
        )
        assert "core inputs missing" in result.lower()


# ---------------------------------------------------------------------------
# 6. Uncertainty wording
# ---------------------------------------------------------------------------


class TestUncertaintyWording:
    def test_high_uncertainty_includes_wide_range_note(self):
        """uncertainty_width > 0.50 → 'Wide valuation range' appended."""
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.45,
            p_sell=0.30,
            uncertainty_width=0.80,
        )
        assert "wide valuation range" in result.lower()
        assert "high uncertainty" in result.lower()

    def test_low_uncertainty_no_wide_range_note(self):
        """uncertainty_width = 0.20 → no uncertainty note."""
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.45,
            p_sell=0.30,
            uncertainty_width=0.20,
        )
        assert "wide valuation range" not in result.lower()

    def test_uncertainty_at_boundary_no_wide_range_note(self):
        """uncertainty_width = 0.50 exactly → boundary is non-inclusive (> 0.50)."""
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.45,
            uncertainty_width=0.50,
        )
        assert "wide valuation range" not in result.lower()

    def test_uncertainty_just_above_boundary_includes_note(self):
        result = _call(
            final_signal="hold",
            p_buy_adjusted=0.45,
            uncertainty_width=0.501,
        )
        assert "wide valuation range" in result.lower()

    def test_uncertainty_none_no_wide_range_note(self):
        """Default uncertainty_width=None → no uncertainty note."""
        result = _call(final_signal="hold", p_buy_adjusted=0.45)
        assert "wide valuation range" not in result.lower()

    def test_uncertainty_note_appended_to_sell(self):
        result = _call(
            final_signal="sell",
            red_flags=["high_leverage"],
            p_sell=0.55,
            uncertainty_width=0.80,
        )
        assert "wide valuation range" in result.lower()

    def test_uncertainty_note_appended_to_strong_buy(self):
        result = _call(
            final_signal="strong_buy",
            valuation_row=_val(mos=0.25),
            quality_score=68.0,
            red_flags=[],
            p_buy_adjusted=0.75,
            uncertainty_width=0.80,
        )
        assert "wide valuation range" in result.lower()

    def test_uncertainty_note_appended_to_insufficient_data(self):
        result = _call(
            final_signal="insufficient_data",
            red_flags=["missing_valuation"],
            uncertainty_width=0.80,
        )
        assert "wide valuation range" in result.lower()


# ---------------------------------------------------------------------------
# 7. Backward compatibility — omitting uncertainty_width
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_call_without_uncertainty_width_kwarg_works(self):
        """Old callers that omit uncertainty_width must not raise an error."""
        result = build_signal_explanation(
            final_signal="hold",
            valuation_row=None,
            quality_score=50.0,
            balance_score=50.0,
            freshness_flag="ok",
            red_flags=[],
            p_buy_adjusted=0.45,
            p_sell=0.30,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_call_with_uncertainty_width_zero_omits_note(self):
        """Passing uncertainty_width=0.0 (falsy) must not show the note."""
        result = build_signal_explanation(
            final_signal="hold",
            valuation_row=None,
            quality_score=50.0,
            balance_score=50.0,
            freshness_flag="ok",
            red_flags=[],
            p_buy_adjusted=0.45,
            p_sell=0.30,
            uncertainty_width=0.0,
        )
        assert "wide valuation range" not in result.lower()


# ---------------------------------------------------------------------------
# 8. Explanation length ≤ 300 characters for standard cases
# ---------------------------------------------------------------------------


class TestExplanationLength:
    @pytest.mark.parametrize("case", [
        {"final_signal": "hold",             "p_buy_adjusted": 0.55, "p_sell": 0.55},
        {"final_signal": "hold",             "p_buy_adjusted": 0.58, "p_sell": 0.25},
        {"final_signal": "hold",             "p_buy_adjusted": 0.30, "freshness_flag": "missing_inputs"},
        {"final_signal": "sell",             "red_flags": ["negative_margin_of_safety"]},
        {"final_signal": "strong_sell",      "red_flags": ["quality_breakdown", "high_leverage"]},
        {"final_signal": "insufficient_data","red_flags": ["missing_valuation"]},
    ])
    def test_length_within_300(self, case: dict) -> None:
        # Merge case with defaults
        params = {
            "final_signal": case.get("final_signal", "hold"),
            "valuation_row": case.get("valuation_row"),
            "quality_score": case.get("quality_score", 55.0),
            "balance_score": 55.0,
            "freshness_flag": case.get("freshness_flag", "ok"),
            "red_flags": case.get("red_flags", []),
            "p_buy_adjusted": case.get("p_buy_adjusted", 0.45),
            "p_sell": case.get("p_sell", 0.35),
            "uncertainty_width": 0.80,  # worst-case: note appended
        }
        result = build_signal_explanation(**params)
        assert len(result) <= 300, f"Explanation too long ({len(result)} chars): {result}"

    def test_strong_buy_with_all_extras_within_300(self) -> None:
        result = build_signal_explanation(
            final_signal="strong_buy",
            valuation_row=_val(mos=0.30),
            quality_score=75.0,
            balance_score=70.0,
            freshness_flag="ok",
            red_flags=[],
            p_buy_adjusted=0.78,
            p_sell=0.15,
            uncertainty_width=0.80,
        )
        assert len(result) <= 300
