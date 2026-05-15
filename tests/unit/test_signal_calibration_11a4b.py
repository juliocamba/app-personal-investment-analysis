"""PR 11A.4b — Near Fair Value Band Calibration.

Verifies the fair-value MoS epsilon introduced in signal_rule_v2:

1.  _FAIR_VALUE_MOS_EPSILON constant equals 0.005 (±0.5 %).
2.  _normalized_mos_for_signal clamps |mos| <= epsilon to 0.0.
3.  _sell_probability with near-zero negative MoS (e.g. -1e-10) behaves
    identically to mos=0.0 — no spurious bearish pressure.
4.  _sell_probability with mos=-0.02 (outside band) still adds +5 pressure.
5.  MODEL_VERSION == "signal_rule_v2".

Background: ORCL and TMDX manual-validation runs produced MoS values like
-1.5e-16 (machine-epsilon noise from floating-point subtraction when price ≈
intrinsic value).  Without normalisation these fall into the ``mos < 0.0``
pressure bracket and add +5 sell pressure spuriously.

No network.  No Supabase.  No secrets.
"""
from __future__ import annotations

from typing import Any

import pytest

import investment_app.scoring.probabilistic as _prob_module
from investment_app.scoring.probabilistic import (
    MODEL_VERSION,
    _FAIR_VALUE_MOS_EPSILON,
    _normalized_mos_for_signal,
    _sell_probability,
)
from investment_app.scoring.rule_based import sigmoid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _val_row(
    *,
    mos: float = 0.0,
    price: float = 100.0,
    iv_p50: float = 150.0,
    iv_p75: float = 180.0,
) -> dict[str, Any]:
    """Minimal valuation row with price well below IV percentiles (no overvalued flags)."""
    return {
        "margin_of_safety_conservative": mos,
        "current_price": price,
        "iv_p50": iv_p50,
        "iv_p75": iv_p75,
    }


def _p_sell(
    mos: float | None = None,
    *,
    val_row_override: dict[str, Any] | None = None,
    **kwargs: Any,
) -> float:
    """Compute _sell_probability with all-neutral inputs; override MoS via *mos* keyword."""
    if val_row_override is not None:
        vrow = val_row_override
    else:
        vrow = None if mos is None else _val_row(mos=mos)
    defaults: dict[str, Any] = dict(
        valuation_row=vrow,
        quality_score=50.0,
        balance_score=50.0,
        news_score=50.0,
        market_score=50.0,
        red_flags=[],
        freshness_flag="ok",
    )
    defaults.update(kwargs)
    return _sell_probability(**defaults)


# ---------------------------------------------------------------------------
# 1. MODEL_VERSION guard
# ---------------------------------------------------------------------------


class TestModelVersionV2:
    def test_model_version_is_signal_rule_v2(self):
        """PR 11A.4b intentionally bumps MODEL_VERSION from signal_rule_v1."""
        assert MODEL_VERSION == "signal_rule_v2"

    def test_module_attribute_matches_import(self):
        assert _prob_module.MODEL_VERSION == "signal_rule_v2"


# ---------------------------------------------------------------------------
# 2. _FAIR_VALUE_MOS_EPSILON constant
# ---------------------------------------------------------------------------


def test_fair_value_epsilon_constant_value():
    """Constant is exactly 0.005 (±0.5 %)."""
    assert _FAIR_VALUE_MOS_EPSILON == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# 3. _normalized_mos_for_signal
# ---------------------------------------------------------------------------


class TestNormalizedMosForSignal:
    def test_none_returns_none(self):
        assert _normalized_mos_for_signal(None) is None

    def test_zero_returns_zero(self):
        assert _normalized_mos_for_signal(0.0) == pytest.approx(0.0)

    def test_small_positive_within_band_clamped_to_zero(self):
        # 0.004 < epsilon → clamped
        assert _normalized_mos_for_signal(0.004) == pytest.approx(0.0)

    def test_small_negative_within_band_clamped_to_zero(self):
        # -0.004, abs = 0.004 < epsilon → clamped
        assert _normalized_mos_for_signal(-0.004) == pytest.approx(0.0)

    def test_at_positive_epsilon_boundary_clamped_to_zero(self):
        # abs(0.005) <= 0.005 → clamped (boundary is inclusive)
        assert _normalized_mos_for_signal(0.005) == pytest.approx(0.0)

    def test_at_negative_epsilon_boundary_clamped_to_zero(self):
        assert _normalized_mos_for_signal(-0.005) == pytest.approx(0.0)

    def test_positive_outside_band_unchanged(self):
        # 0.006 > epsilon → not clamped
        assert _normalized_mos_for_signal(0.006) == pytest.approx(0.006)

    def test_negative_outside_band_unchanged(self):
        assert _normalized_mos_for_signal(-0.006) == pytest.approx(-0.006)

    def test_large_negative_unchanged(self):
        assert _normalized_mos_for_signal(-0.30) == pytest.approx(-0.30)

    def test_floating_point_noise_orcl_tmdx(self):
        """Real-world case: near-zero noise from ORCL and TMDX validation runs."""
        assert _normalized_mos_for_signal(-1.467e-13) == pytest.approx(0.0)
        assert _normalized_mos_for_signal(-1.134e-13) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 4. Sell pressure with near-fair-value MoS
# ---------------------------------------------------------------------------


class TestSellPressureNearFairValue:
    def test_tiny_negative_mos_behaves_same_as_zero_mos(self):
        """mos=-1e-10 is inside the epsilon band → clamped → same pressure as mos=0."""
        assert _p_sell(mos=-1e-10) == pytest.approx(_p_sell(mos=0.0), abs=1e-9)

    def test_mos_minus_0_004_behaves_same_as_zero(self):
        """mos=-0.004 is within the band → clamped to zero."""
        assert _p_sell(mos=-0.004) == pytest.approx(_p_sell(mos=0.0), abs=1e-9)

    def test_near_zero_negative_mos_does_not_exceed_zero_mos_pressure(self):
        """Every MoS value within the band must match the zero-MoS baseline exactly."""
        baseline = _p_sell(mos=0.0)
        for sample in (0.0, -1e-15, -0.001, -0.003, 0.001, 0.003, 0.005, -0.005):
            assert _p_sell(mos=sample) == pytest.approx(baseline, abs=1e-9), (
                f"mos={sample} should not add pressure over zero-MoS baseline"
            )

    def test_mos_minus_0_02_still_adds_bearish_pressure(self):
        """mos=-0.02 is outside the band → not clamped → falls in <0.0 bracket (+5 pressure)."""
        result = _p_sell(mos=-0.02)
        baseline = _p_sell(mos=0.0)
        # pressure = 35 + 5 = 40 → sigmoid(-10/12)
        expected = sigmoid(-10.0 / 12.0)
        assert result == pytest.approx(expected, abs=1e-5)
        assert result > baseline

    def test_mos_minus_0_25_retains_full_bearish_pressure(self):
        """Deep negative MoS is well outside the band and retains full pressure (+18)."""
        result = _p_sell(mos=-0.25)
        expected = sigmoid(3.0 / 12.0)  # pressure = 35 + 18 = 53
        assert result == pytest.approx(expected, abs=1e-5)

    def test_p_sell_none_valuation_equals_p_sell_within_band(self):
        """mos=None (no valuation) and mos=-0.004 (within band) both add zero MoS pressure."""
        assert _p_sell(mos=None) == pytest.approx(_p_sell(mos=-0.004), abs=1e-9)
