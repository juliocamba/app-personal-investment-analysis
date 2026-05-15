"""PR 11A.1 — Baseline audit: lock current signal model thresholds and behavior.

These tests assert the *exact current* values of:
- MODEL_VERSION string
- _quality_multiplier formula thresholds and freshness haircuts
- _risk_penalty accumulation thresholds and cap
- _sell_probability pressure accumulation at known boundary inputs
- _classify_signal decision boundaries for HOLD / SELL / STRONG_SELL / BUY / STRONG_BUY
- _build_red_flags threshold crossings

Tests call the private helper functions directly.  Python does not enforce
name-mangled access, so ``from module import _fn`` works correctly in tests.
No production code is changed.  No network access.  No Supabase.  No secrets.
"""
from __future__ import annotations

from typing import Any

import pytest

import investment_app.scoring.probabilistic as _prob_module
from investment_app.scoring.probabilistic import (
    MODEL_VERSION,
    _build_red_flags,
    _classify_signal,
    _quality_multiplier,
    _risk_penalty,
    _sell_probability,
)
from investment_app.scoring.rule_based import sigmoid


# ---------------------------------------------------------------------------
# Shared fixture helpers
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
    """Minimal valid valuation row fixture."""
    return {
        "id": "val-audit-001",
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


def _qual_row(score: float = 65.0) -> dict[str, Any]:
    return {"id": "qual-audit-001", "score_date": "2025-01-01", "final_quality_score": score}


def _ratio_row(
    *,
    leverage: float = 1.0,
    coverage: float = 8.0,
    sentiment: float = 0.10,
) -> dict[str, Any]:
    return {
        "factor_date": "2025-01-01",
        "net_debt_to_ebitda": leverage,
        "interest_coverage": coverage,
        "news_sentiment_7d": sentiment,
    }


# ---------------------------------------------------------------------------
# MODEL_VERSION — assert exact literal string
# ---------------------------------------------------------------------------


class TestModelVersion:
    def test_model_version_literal_string(self):
        """Intentionally updated from signal_rule_v0 → signal_rule_v1 in PR 11A.4."""
        assert MODEL_VERSION == "signal_rule_v1"

    def test_module_attribute_matches_import(self):
        assert _prob_module.MODEL_VERSION == "signal_rule_v1"


# ---------------------------------------------------------------------------
# _quality_multiplier — formula and freshness haircut thresholds
# ---------------------------------------------------------------------------


class TestQualityMultiplier:
    """
    Formula: 1.0 + clamp((quality_score - 50) / 200, -0.15, +0.15)
    Freshness haircuts: limited → ×0.95 | stale/missing_inputs → ×0.90
    """

    def test_neutral_quality_ok_freshness_is_exactly_one(self):
        assert _quality_multiplier(50.0, freshness_flag="ok") == pytest.approx(1.0)

    def test_high_quality_uncapped_example(self):
        # quality=70: (70-50)/200 = 0.10, within cap → multiplier = 1.10
        assert _quality_multiplier(70.0, freshness_flag="ok") == pytest.approx(1.10)

    def test_positive_cap_at_fifteen_pct(self):
        # quality=80: (80-50)/200 = 0.15, exactly at cap → multiplier = 1.15
        assert _quality_multiplier(80.0, freshness_flag="ok") == pytest.approx(1.15)

    def test_high_quality_capped_does_not_exceed_fifteen_pct(self):
        # quality=130: (130-50)/200 = 0.40, capped at 0.15 → multiplier = 1.15
        assert _quality_multiplier(130.0, freshness_flag="ok") == pytest.approx(1.15)

    def test_negative_cap_at_minus_fifteen_pct(self):
        # quality=20: (20-50)/200 = -0.15, exactly at cap → multiplier = 0.85
        assert _quality_multiplier(20.0, freshness_flag="ok") == pytest.approx(0.85)

    def test_very_low_quality_capped_does_not_drop_below_minus_fifteen_pct(self):
        # quality=0: (0-50)/200 = -0.25, capped at -0.15 → 0.85
        assert _quality_multiplier(0.0, freshness_flag="ok") == pytest.approx(0.85)

    def test_limited_freshness_applies_five_pct_haircut(self):
        assert _quality_multiplier(50.0, freshness_flag="limited") == pytest.approx(0.95)

    def test_stale_freshness_applies_ten_pct_haircut(self):
        assert _quality_multiplier(50.0, freshness_flag="stale") == pytest.approx(0.90)

    def test_missing_inputs_freshness_applies_ten_pct_haircut(self):
        assert _quality_multiplier(50.0, freshness_flag="missing_inputs") == pytest.approx(0.90)

    def test_high_quality_with_stale_freshness_combined(self):
        # quality=80 → 1.15; stale → ×0.90
        assert _quality_multiplier(80.0, freshness_flag="stale") == pytest.approx(1.15 * 0.90)


# ---------------------------------------------------------------------------
# _risk_penalty — accumulation thresholds and cap
# ---------------------------------------------------------------------------


class TestRiskPenalty:
    """
    Penalty sources:
      balance_score < 50: min(0.20, (50 - balance) / 100)
      news_score < 40:    +0.05
      freshness limited:  +0.03 | stale: +0.05 | missing_inputs: +0.10
      any hard red flag:  +0.10 (capped; only added once regardless of flag count)
    Total capped at 0.35.
    """

    def test_clean_input_produces_zero_penalty(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=[],
            freshness_flag="ok",
        ) == pytest.approx(0.0)

    def test_balance_score_just_below_50_adds_proportional_penalty(self):
        # balance=30: min(0.20, 20/100) = 0.20
        assert _risk_penalty(
            balance_score=30.0,
            news_score=50.0,
            red_flags=[],
            freshness_flag="ok",
        ) == pytest.approx(0.20)

    def test_balance_score_penalty_capped_at_twenty_pct(self):
        # balance=0: min(0.20, 50/100=0.50) → capped at 0.20
        assert _risk_penalty(
            balance_score=0.0,
            news_score=50.0,
            red_flags=[],
            freshness_flag="ok",
        ) == pytest.approx(0.20)

    def test_balance_score_at_threshold_adds_zero(self):
        assert _risk_penalty(
            balance_score=50.0,
            news_score=50.0,
            red_flags=[],
            freshness_flag="ok",
        ) == pytest.approx(0.0)

    def test_news_score_below_40_adds_five_pct(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=39.9,
            red_flags=[],
            freshness_flag="ok",
        ) == pytest.approx(0.05)

    def test_news_score_at_threshold_adds_zero(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=40.0,
            red_flags=[],
            freshness_flag="ok",
        ) == pytest.approx(0.0)

    def test_limited_freshness_adds_three_pct(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=[],
            freshness_flag="limited",
        ) == pytest.approx(0.03)

    def test_stale_freshness_adds_five_pct(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=[],
            freshness_flag="stale",
        ) == pytest.approx(0.05)

    def test_missing_inputs_freshness_adds_ten_pct(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=[],
            freshness_flag="missing_inputs",
        ) == pytest.approx(0.10)

    def test_high_leverage_flag_adds_ten_pct(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=["high_leverage"],
            freshness_flag="ok",
        ) == pytest.approx(0.10)

    def test_critical_interest_coverage_flag_adds_ten_pct(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=["critical_interest_coverage"],
            freshness_flag="ok",
        ) == pytest.approx(0.10)

    def test_quality_breakdown_flag_adds_ten_pct(self):
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=["quality_breakdown"],
            freshness_flag="ok",
        ) == pytest.approx(0.10)

    def test_multiple_hard_flags_still_only_add_ten_pct(self):
        # any() means all three flags together add the same as one
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=["high_leverage", "critical_interest_coverage", "quality_breakdown"],
            freshness_flag="ok",
        ) == pytest.approx(0.10)

    def test_non_hard_flags_do_not_add_penalty(self):
        # e.g. "negative_news_spike" is not a hard penalty flag in _risk_penalty
        assert _risk_penalty(
            balance_score=60.0,
            news_score=50.0,
            red_flags=["negative_news_spike", "freshness_stale"],
            freshness_flag="ok",
        ) == pytest.approx(0.0)

    def test_total_penalty_capped_at_thirty_five_pct(self):
        # balance=0(0.20) + news<40(0.05) + missing_inputs(0.10) + hard_flag(0.10) = 0.45 → 0.35
        assert _risk_penalty(
            balance_score=0.0,
            news_score=35.0,
            red_flags=["high_leverage"],
            freshness_flag="missing_inputs",
        ) == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# _sell_probability — pressure accumulation at boundary inputs
# ---------------------------------------------------------------------------


class TestSellProbability:
    """
    Base pressure = 35.0.  sigmoid((pressure - 50) / 12.0).
    Key adjustments tested here (full table in probabilistic.py).
    """

    def _compute(self, **kwargs: Any) -> float:
        defaults: dict[str, Any] = dict(
            valuation_row=None,
            quality_score=50.0,
            balance_score=50.0,
            news_score=50.0,
            market_score=50.0,
            red_flags=[],
            freshness_flag="ok",
        )
        defaults.update(kwargs)
        return _sell_probability(**defaults)

    def test_baseline_all_neutral_matches_expected_sigmoid(self):
        # pressure=35, sigmoid((35-50)/12) = sigmoid(-1.25)
        expected = sigmoid(-15.0 / 12.0)
        assert self._compute() == pytest.approx(expected, abs=1e-5)

    def test_mos_below_minus_twenty_pct_adds_eighteen_to_pressure(self):
        # pressure = 35 + 18 = 53
        expected = sigmoid(3.0 / 12.0)
        assert self._compute(valuation_row=_val_row(mos=-0.25)) == pytest.approx(expected, abs=1e-5)

    def test_mos_between_minus_twenty_and_minus_ten_adds_ten_to_pressure(self):
        # pressure = 35 + 10 = 45
        expected = sigmoid(-5.0 / 12.0)
        assert self._compute(valuation_row=_val_row(mos=-0.15)) == pytest.approx(expected, abs=1e-5)

    def test_mos_between_minus_ten_and_zero_adds_five_to_pressure(self):
        # pressure = 35 + 5 = 40
        expected = sigmoid(-10.0 / 12.0)
        assert self._compute(valuation_row=_val_row(mos=-0.05)) == pytest.approx(expected, abs=1e-5)

    def test_quality_at_or_below_30_adds_eighteen_to_pressure(self):
        # pressure = 35 + 18 = 53
        expected = sigmoid(3.0 / 12.0)
        assert self._compute(quality_score=28.0) == pytest.approx(expected, abs=1e-5)

    def test_quality_below_40_adds_twelve_to_pressure(self):
        # pressure = 35 + 12 = 47
        expected = sigmoid(-3.0 / 12.0)
        assert self._compute(quality_score=38.0) == pytest.approx(expected, abs=1e-5)

    def test_quality_below_50_adds_five_to_pressure(self):
        # pressure = 35 + 5 = 40
        expected = sigmoid(-10.0 / 12.0)
        assert self._compute(quality_score=45.0) == pytest.approx(expected, abs=1e-5)

    def test_high_leverage_flag_adds_twenty_to_pressure(self):
        # pressure = 35 + 20 = 55
        expected = sigmoid(5.0 / 12.0)
        assert self._compute(red_flags=["high_leverage"]) == pytest.approx(expected, abs=1e-5)

    def test_output_is_bounded_between_zero_and_one(self):
        result = self._compute(
            valuation_row=_val_row(mos=-0.30, price=300.0, iv_p75=100.0, iv_p50=80.0),
            quality_score=20.0,
            balance_score=20.0,
            news_score=25.0,
            market_score=25.0,
            red_flags=["high_leverage", "critical_interest_coverage", "quality_breakdown"],
            freshness_flag="missing_inputs",
        )
        assert 0.0 <= result <= 1.0

    def test_severe_inputs_produce_p_sell_well_above_sixty_pct(self):
        # Enough combined pressure that result exceeds strong_sell threshold
        result = self._compute(
            valuation_row=_val_row(mos=-0.25),
            red_flags=["high_leverage"],
        )
        assert result > 0.60


# ---------------------------------------------------------------------------
# _classify_signal — decision-boundary assertions
# ---------------------------------------------------------------------------


class TestClassifySignal:
    """
    Decision tree (signal_rule_v1, PR 11A.4):
      1. all three core flags missing → insufficient_data
      2. p_sell >= 0.60 AND confirming bearish flag → strong_sell
      3. any hard red flag OR p_sell >= 0.60 (no confirming flag) → sell
      4. freshness==ok AND valuation present AND mos present:
           p_buy >= 0.70 AND mos >= 0.15 AND no flags → strong_buy (demoted to hold when partial_analysis)
           p_buy >= 0.60 AND mos >= 0.10 AND not missing_qualitative → buy (demoted to hold when partial_analysis)
      5. otherwise → hold
    """

    _VAL_ROW = _val_row()  # used in most tests; never mutated

    def _classify(self, **kwargs: Any) -> str:
        defaults: dict[str, Any] = dict(
            p_buy_adjusted=0.55,
            p_sell=0.30,
            valuation_row=self._VAL_ROW,
            quality_score=65.0,
            red_flags=[],
            freshness_flag="ok",
        )
        defaults.update(kwargs)
        return _classify_signal(**defaults)

    # ------------------------------------------------------------------
    # Path 1: insufficient_data requires ALL THREE core flags
    # ------------------------------------------------------------------

    def test_all_three_core_missing_flags_produce_insufficient_data(self):
        signal = self._classify(
            red_flags=["missing_valuation", "missing_qualitative_score", "missing_ratio_factors"],
            valuation_row=None,
        )
        assert signal == "insufficient_data"

    def test_only_missing_valuation_does_not_produce_insufficient_data(self):
        signal = self._classify(red_flags=["missing_valuation"], valuation_row=None)
        assert signal != "insufficient_data"

    def test_two_of_three_core_flags_not_sufficient_for_insufficient_data(self):
        signal = self._classify(
            red_flags=["missing_valuation", "missing_qualitative_score"],
            valuation_row=None,
        )
        assert signal != "insufficient_data"

    # ------------------------------------------------------------------
    # Path 2: hard red flags → sell (not strong_sell or worse)
    # ------------------------------------------------------------------

    def test_quality_breakdown_flag_produces_sell(self):
        assert self._classify(red_flags=["quality_breakdown"]) == "sell"

    def test_high_leverage_flag_produces_sell(self):
        assert self._classify(red_flags=["high_leverage"]) == "sell"

    def test_critical_interest_coverage_flag_produces_sell(self):
        assert self._classify(red_flags=["critical_interest_coverage"]) == "sell"

    def test_negative_direct_fcf_flag_produces_sell(self):
        assert self._classify(red_flags=["negative_direct_fcf"]) == "sell"

    def test_zero_direct_fcf_flag_produces_sell(self):
        assert self._classify(red_flags=["zero_direct_fcf"]) == "sell"

    def test_non_hard_red_flag_does_not_produce_sell(self):
        # "negative_news_spike" is not in the hard-flag list
        signal = self._classify(red_flags=["negative_news_spike"])
        assert signal not in {"sell", "strong_sell"}

    # ------------------------------------------------------------------
    # Path 2 (v1): p_sell >= 0.60 AND confirming flag → strong_sell
    # ------------------------------------------------------------------

    def test_p_sell_at_sixty_pct_with_confirming_flag_produces_strong_sell(self):
        """p_sell=0.60 + confirming flag → strong_sell."""
        assert self._classify(p_sell=0.60, red_flags=["high_leverage"]) == "strong_sell"

    def test_p_sell_above_sixty_pct_with_negative_mos_produces_strong_sell(self):
        assert self._classify(p_sell=0.75, red_flags=["negative_margin_of_safety"]) == "strong_sell"

    def test_p_sell_at_sixty_pct_without_confirming_flag_produces_sell_not_strong_sell(self):
        """PR 11A.4: p_sell >= 0.60 alone is no longer sufficient for strong_sell."""
        assert self._classify(p_sell=0.60, red_flags=[]) == "sell"

    def test_p_sell_above_sixty_pct_without_confirming_flag_produces_sell(self):
        assert self._classify(p_sell=0.75, red_flags=[]) == "sell"

    def test_p_sell_just_below_sixty_pct_does_not_produce_strong_sell(self):
        signal = self._classify(p_sell=0.599, red_flags=[])
        assert signal != "strong_sell"

    # ------------------------------------------------------------------
    # Valuation-based strong_sell path REMOVED in PR 11A.4
    # price > iv_p75 AND quality < 50 alone no longer produces strong_sell.
    # Strong sell requires p_sell >= 0.60 AND a confirming flag.
    # ------------------------------------------------------------------

    def test_price_above_iv_p75_and_low_quality_without_confirming_flag_is_not_strong_sell(self):
        """PR 11A.4: shortcut removed. price > iv_p75 + quality < 50 without
        elevated p_sell and a confirming flag produces sell (hard_red_flag or
        fall-through), not strong_sell."""
        row = _val_row(price=200.0, iv_p75=180.0)
        # red_flags=[], p_sell=0.30 (default) — no confirming flag, low p_sell
        signal = self._classify(valuation_row=row, quality_score=45.0)
        assert signal != "strong_sell"

    def test_price_above_iv_p75_but_quality_gte_50_does_not_produce_strong_sell(self):
        row = _val_row(price=200.0, iv_p75=180.0)
        signal = self._classify(valuation_row=row, quality_score=55.0)
        assert signal != "strong_sell"

    def test_price_below_iv_p75_with_low_quality_does_not_trigger_this_path(self):
        row = _val_row(price=100.0, iv_p75=180.0)
        signal = self._classify(valuation_row=row, quality_score=45.0)
        assert signal != "strong_sell"

    # ------------------------------------------------------------------
    # Path 5a: strong_buy — requires p_buy >= 0.70, mos >= 0.15, no flags, fresh
    # ------------------------------------------------------------------

    def test_strong_buy_with_all_conditions_met(self):
        assert self._classify(
            p_buy_adjusted=0.72,
            p_sell=0.10,
            valuation_row=_val_row(mos=0.20),
            red_flags=[],
            freshness_flag="ok",
        ) == "strong_buy"

    def test_strong_buy_requires_p_buy_gte_seventy_pct(self):
        # 0.69 < 0.70 → cannot be strong_buy; also < 0.60 so not buy; returns hold
        signal = self._classify(
            p_buy_adjusted=0.69,
            p_sell=0.10,
            valuation_row=_val_row(mos=0.20),
            red_flags=[],
            freshness_flag="ok",
        )
        assert signal != "strong_buy"

    def test_strong_buy_requires_mos_gte_fifteen_pct(self):
        # mos=0.14 just below threshold
        signal = self._classify(
            p_buy_adjusted=0.75,
            p_sell=0.10,
            valuation_row=_val_row(mos=0.14),
            red_flags=[],
            freshness_flag="ok",
        )
        assert signal != "strong_buy"

    def test_strong_buy_blocked_when_any_red_flag_present(self):
        # "negative_news_spike" is not a hard flag but still blocks strong_buy
        signal = self._classify(
            p_buy_adjusted=0.75,
            p_sell=0.10,
            valuation_row=_val_row(mos=0.20),
            red_flags=["negative_news_spike"],
            freshness_flag="ok",
        )
        assert signal != "strong_buy"

    def test_strong_buy_blocked_by_stale_freshness(self):
        signal = self._classify(
            p_buy_adjusted=0.75,
            p_sell=0.10,
            valuation_row=_val_row(mos=0.20),
            red_flags=[],
            freshness_flag="stale",
        )
        assert signal != "strong_buy"

    # ------------------------------------------------------------------
    # Path 5b: buy — requires p_buy >= 0.60, mos >= 0.10, fresh, no missing_qual
    # ------------------------------------------------------------------

    def test_buy_with_conditions_met(self):
        assert self._classify(
            p_buy_adjusted=0.62,
            p_sell=0.20,
            valuation_row=_val_row(mos=0.12),
            red_flags=[],
            freshness_flag="ok",
        ) == "buy"

    def test_buy_requires_p_buy_gte_sixty_pct(self):
        signal = self._classify(
            p_buy_adjusted=0.59,
            p_sell=0.20,
            valuation_row=_val_row(mos=0.12),
            red_flags=[],
            freshness_flag="ok",
        )
        assert signal != "buy"

    def test_buy_requires_mos_gte_ten_pct(self):
        signal = self._classify(
            p_buy_adjusted=0.65,
            p_sell=0.20,
            valuation_row=_val_row(mos=0.09),
            red_flags=[],
            freshness_flag="ok",
        )
        assert signal != "buy"

    def test_buy_blocked_by_stale_freshness(self):
        signal = self._classify(
            p_buy_adjusted=0.65,
            p_sell=0.20,
            valuation_row=_val_row(mos=0.12),
            red_flags=[],
            freshness_flag="stale",
        )
        assert signal == "hold"

    def test_buy_blocked_by_missing_qualitative_flag(self):
        signal = self._classify(
            p_buy_adjusted=0.65,
            p_sell=0.20,
            valuation_row=_val_row(mos=0.12),
            red_flags=["missing_qualitative_score"],
            freshness_flag="ok",
        )
        assert signal != "buy"

    def test_buy_blocked_when_valuation_row_is_none(self):
        # No valuation → mos=None → cannot qualify for buy
        signal = self._classify(
            p_buy_adjusted=0.65,
            p_sell=0.20,
            valuation_row=None,
            red_flags=["missing_valuation"],
            freshness_flag="ok",
        )
        assert signal == "hold"

    # ------------------------------------------------------------------
    # Path 6: HOLD — default when no other condition is met
    # ------------------------------------------------------------------

    def test_mid_range_inputs_produce_hold(self):
        assert self._classify(
            p_buy_adjusted=0.55,
            p_sell=0.30,
            valuation_row=_val_row(mos=0.05),
            red_flags=[],
            freshness_flag="ok",
        ) == "hold"

    # ------------------------------------------------------------------
    # Known gap: both p_buy and p_sell elevated (documented current behavior)
    # ------------------------------------------------------------------

    def test_both_elevated_buy_and_sell_below_sixty_pct_sell_threshold_resolves_to_buy(self):
        """signal_rule_v1 (PR 11A.4): analysis_ready + p_sell < 0.60 and buy conditions
        met → 'buy' is preserved.  Partial-analysis demotion does not apply here
        because readiness_status defaults to 'analysis_ready'.
        """
        signal = self._classify(
            p_buy_adjusted=0.65,
            p_sell=0.55,  # elevated but below strong_sell threshold
            valuation_row=_val_row(mos=0.12),
            red_flags=[],
            freshness_flag="ok",
        )
        assert signal == "buy"


# ---------------------------------------------------------------------------
# _build_red_flags — key threshold crossings
# ---------------------------------------------------------------------------


class TestBuildRedFlags:
    def _flags(self, **overrides: Any) -> list[str]:
        defaults: dict[str, Any] = dict(
            valuation_row=None,
            qualitative_row=_qual_row(65.0),
            ratio_row=_ratio_row(),
            freshness_flag="ok",
        )
        defaults.update(overrides)
        return _build_red_flags(**defaults)

    # ---- valuation flags ----

    def test_mos_below_minus_fifteen_pct_adds_negative_mos_flag(self):
        flags = self._flags(valuation_row=_val_row(mos=-0.20))
        assert "negative_margin_of_safety" in flags

    def test_mos_at_minus_fifteen_pct_boundary_adds_flag(self):
        # mos < -0.15: -0.16 is below the threshold
        flags = self._flags(valuation_row=_val_row(mos=-0.16))
        assert "negative_margin_of_safety" in flags

    def test_mos_at_exactly_minus_fifteen_pct_does_not_add_flag(self):
        # condition is mos < -0.15; -0.15 is NOT less than -0.15
        flags = self._flags(valuation_row=_val_row(mos=-0.15))
        assert "negative_margin_of_safety" not in flags

    def test_missing_valuation_row_adds_missing_valuation_flag(self):
        assert "missing_valuation" in self._flags(valuation_row=None)

    # ---- ratio flags ----

    def test_leverage_gte_five_adds_high_leverage_flag(self):
        assert "high_leverage" in self._flags(ratio_row=_ratio_row(leverage=5.0))

    def test_leverage_below_five_does_not_add_flag(self):
        assert "high_leverage" not in self._flags(ratio_row=_ratio_row(leverage=4.9))

    def test_interest_coverage_at_one_adds_critical_coverage_flag(self):
        assert "critical_interest_coverage" in self._flags(ratio_row=_ratio_row(coverage=1.0))

    def test_interest_coverage_above_one_does_not_add_flag(self):
        assert "critical_interest_coverage" not in self._flags(ratio_row=_ratio_row(coverage=1.01))

    def test_sentiment_at_minus_thirty_adds_negative_news_flag(self):
        assert "negative_news_spike" in self._flags(ratio_row=_ratio_row(sentiment=-0.30))

    def test_sentiment_above_minus_thirty_does_not_add_flag(self):
        assert "negative_news_spike" not in self._flags(ratio_row=_ratio_row(sentiment=-0.29))

    def test_missing_ratio_row_adds_missing_ratio_factors_flag(self):
        assert "missing_ratio_factors" in self._flags(ratio_row=None)

    # ---- qualitative flags ----

    def test_quality_at_or_below_30_adds_quality_breakdown(self):
        assert "quality_breakdown" in self._flags(qualitative_row=_qual_row(30.0))

    def test_quality_between_30_and_40_adds_weak_quality_not_breakdown(self):
        flags = self._flags(qualitative_row=_qual_row(35.0))
        assert "weak_quality" in flags
        assert "quality_breakdown" not in flags

    def test_quality_at_40_boundary_does_not_add_weak_quality(self):
        # condition is quality_score < 40.0; 40.0 is not < 40.0
        flags = self._flags(qualitative_row=_qual_row(40.0))
        assert "weak_quality" not in flags
        assert "quality_breakdown" not in flags

    def test_missing_qualitative_row_adds_missing_qualitative_flag(self):
        assert "missing_qualitative_score" in self._flags(qualitative_row=None)

    # ---- freshness flags ----

    def test_stale_freshness_adds_freshness_stale_flag(self):
        assert "freshness_stale" in self._flags(freshness_flag="stale")

    def test_missing_inputs_freshness_adds_freshness_missing_inputs_flag(self):
        assert "freshness_missing_inputs" in self._flags(freshness_flag="missing_inputs")

    def test_ok_freshness_adds_no_freshness_flags(self):
        flags = self._flags(freshness_flag="ok")
        assert "freshness_stale" not in flags
        assert "freshness_missing_inputs" not in flags

    # ---- structural guarantees ----

    def test_flags_list_is_sorted_and_deduplicated(self):
        flags = self._flags(
            valuation_row=None,       # missing_valuation
            qualitative_row=None,     # missing_qualitative_score
            ratio_row=None,           # missing_ratio_factors
            freshness_flag="stale",   # freshness_stale
        )
        assert flags == sorted(set(flags))
