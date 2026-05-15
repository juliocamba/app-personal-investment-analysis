"""PR 11A.2 — Qualitative outlier diagnostics tests.

Covers the new diagnostic evidence added to _score_moat:
  - ROIC outlier flagging (roic_outlier, roic_raw, roic_diagnostic_bound)
  - Gross-margin std outlier flagging (gross_margin_std_outlier)

Verifies:
  - qual_v0 model version unchanged
  - Outlier flags do NOT change the score (purely diagnostic)
  - Normal ROIC produces no outlier evidence
  - Normal gross-margin std produces no outlier evidence

No network.  No Supabase.  No secrets.
"""
from __future__ import annotations

from typing import Any

import pytest

import investment_app.scoring.qualitative as _qual_module
from investment_app.scoring.qualitative import (
    MODEL_VERSION,
    _ROIC_DIAGNOSTIC_HI,
    _ROIC_DIAGNOSTIC_LO,
    _score_moat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ratios(roic: float | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if roic is not None:
        row["roic"] = roic
    return row


def _stmts_with_gm(gm_values: list[float]) -> list[dict[str, Any]]:
    """Build minimal annual statement list for gross-margin computation.

    Each gm_value is treated as gross_profit when revenue=1.0, so
    gross_margin = gm_value for each period.
    """
    return [{"revenue": 1.0, "gross_profit": gm} for gm in gm_values]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestQualModelVersion:
    def test_model_version_unchanged(self):
        assert MODEL_VERSION == "qual_v0"

    def test_module_attribute_matches_import(self):
        assert _qual_module.MODEL_VERSION == "qual_v0"


class TestRoicDiagnosticBounds:
    def test_lo_bound_is_minus_two(self):
        assert _ROIC_DIAGNOSTIC_LO == pytest.approx(-2.0)

    def test_hi_bound_is_five(self):
        assert _ROIC_DIAGNOSTIC_HI == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# ROIC outlier diagnostics
# ---------------------------------------------------------------------------


class TestRoicOutlierDiagnostics:
    """
    Outlier bounds: lo < -2.0, hi > 5.0.
    Score impact: NONE — only evidence keys change.
    """

    def test_extreme_positive_roic_adds_outlier_evidence(self):
        _, ev = _score_moat(_ratios(roic=6.0), [])
        assert ev.get("roic_outlier") is True
        assert ev.get("roic_diagnostic_bound") == "high"
        assert ev.get("roic_raw") == pytest.approx(6.0)

    def test_extreme_negative_roic_adds_outlier_evidence(self):
        _, ev = _score_moat(_ratios(roic=-3.0), [])
        assert ev.get("roic_outlier") is True
        assert ev.get("roic_diagnostic_bound") == "low"
        assert ev.get("roic_raw") == pytest.approx(-3.0)

    def test_normal_positive_roic_no_outlier_evidence(self):
        # 0.20 is well within bounds
        _, ev = _score_moat(_ratios(roic=0.20), [])
        assert "roic_outlier" not in ev

    def test_roic_at_hi_bound_no_outlier(self):
        # Exactly 5.0 is NOT outside the bound (> not >=)
        _, ev = _score_moat(_ratios(roic=5.0), [])
        assert "roic_outlier" not in ev

    def test_roic_just_above_hi_bound_is_outlier(self):
        _, ev = _score_moat(_ratios(roic=5.001), [])
        assert ev.get("roic_outlier") is True
        assert ev.get("roic_diagnostic_bound") == "high"

    def test_roic_at_lo_bound_no_outlier(self):
        # Exactly -2.0 is NOT outside the bound (< not <=)
        _, ev = _score_moat(_ratios(roic=-2.0), [])
        assert "roic_outlier" not in ev

    def test_roic_just_below_lo_bound_is_outlier(self):
        _, ev = _score_moat(_ratios(roic=-2.001), [])
        assert ev.get("roic_outlier") is True
        assert ev.get("roic_diagnostic_bound") == "low"

    def test_missing_roic_no_outlier_evidence(self):
        _, ev = _score_moat(_ratios(roic=None), [])
        assert "roic_outlier" not in ev

    def test_extreme_roic_does_not_change_score_vs_non_extreme(self):
        """Score for roic=6.0 must equal score for roic=0.20 (strong >15%)
        because both trigger the same branch (roic > 0.15 → +15 pts).
        The outlier flag is diagnostic only."""
        score_extreme, _ = _score_moat(_ratios(roic=6.0), [])
        score_normal, _  = _score_moat(_ratios(roic=0.20), [])
        # Both have roic > 0.15 → same +15 adjustment from neutral 50
        assert score_extreme == pytest.approx(score_normal)

    def test_extreme_negative_roic_score_equals_normal_negative_roic_score(self):
        """roic=-3.0 triggers same branch as roic=-0.01 (roic < 0 → -15 pts)."""
        score_extreme, _ = _score_moat(_ratios(roic=-3.0), [])
        score_normal, _  = _score_moat(_ratios(roic=-0.01), [])
        assert score_extreme == pytest.approx(score_normal)


# ---------------------------------------------------------------------------
# Gross-margin std outlier diagnostics
# ---------------------------------------------------------------------------


class TestGrossMarginStdOutlier:
    """
    Outlier threshold: std_gm > 0.50.
    Score impact: NONE — score uses the existing >0.10 volatile branch only.
    """

    def test_extreme_gross_margin_volatility_adds_outlier_evidence(self):
        # gm values [1.5, 0.0, 0.0]: avg=0.5, std≈0.707 > 0.50
        stmts = _stmts_with_gm([1.5, 0.0, 0.0])
        _, ev = _score_moat({}, stmts)
        assert ev.get("gross_margin_std_outlier") is True

    def test_normal_gross_margin_volatility_no_outlier(self):
        # gm values [0.50, 0.55, 0.52]: small variance, std << 0.50
        stmts = _stmts_with_gm([0.50, 0.55, 0.52])
        _, ev = _score_moat({}, stmts)
        assert "gross_margin_std_outlier" not in ev

    def test_moderate_volatility_below_threshold_no_outlier(self):
        # gm values [0.70, 0.40, 0.55]: std ≈ 0.122, well below 0.50
        stmts = _stmts_with_gm([0.70, 0.40, 0.55])
        _, ev = _score_moat({}, stmts)
        assert "gross_margin_std_outlier" not in ev

    def test_insufficient_periods_no_outlier_evidence(self):
        # < 3 periods: gross_margin_std is not computed at all
        stmts = _stmts_with_gm([0.50, 0.0])
        _, ev = _score_moat({}, stmts)
        assert "gross_margin_std_outlier" not in ev
        assert "gross_margin_std" not in ev

    def test_extreme_std_score_equals_score_without_outlier_flag(self):
        """Outlier flag must not change the moat score.

        Fixtures are designed to hold margin_trend constant (flat) by using
        identical first and last gm values, so only std differs between the
        two fixtures:

          Outlier fixture : [1.2, 0.0, 1.2] — std ≈ 0.566 > 0.50  → flag set
          Normal  fixture : [0.5, 0.2, 0.5] — std ≈ 0.141 ∈ (0.10, 0.50] → no flag

        Both fixtures have std > 0.10 → same volatile branch (-5 pts).
        Both fixtures have gm_ratios[0] == gm_ratios[-1] → margin_trend = 'flat'.
        Therefore both moat scores must be identical; the flag is purely diagnostic.
        """
        # Outlier fixture: std ≈ 0.566 > 0.50; gm[0] == gm[-1] → flat trend
        stmts_outlier = _stmts_with_gm([1.2, 0.0, 1.2])
        # Normal fixture: std ≈ 0.141 ∈ (0.10, 0.50]; gm[0] == gm[-1] → flat trend
        stmts_normal  = _stmts_with_gm([0.5, 0.2, 0.5])

        score_outlier, ev_outlier = _score_moat({}, stmts_outlier)
        score_normal,  ev_normal  = _score_moat({}, stmts_normal)

        # 1. Outlier fixture must include the diagnostic flag.
        assert ev_outlier.get("gross_margin_std_outlier") is True

        # 2. Normal fixture must NOT include the diagnostic flag.
        assert "gross_margin_std_outlier" not in ev_normal

        # 3. Scores must be equal — the flag is diagnostic only, zero score impact.
        assert score_outlier == pytest.approx(score_normal)
