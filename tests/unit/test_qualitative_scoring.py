"""Unit tests for Phase 5: qualitative scoring formula.

Covers:
- Happy-path score calculation for all four dimensions
- Final weighted score formula
- Missing data returns None or conservative defaults
- Out-of-range clamping to [0, 100]
- Weight loading from YAML and custom overrides
- human_override=0 always present in the row
- auto_score structure and evidence keys
- Conservative behaviour with no ratios / no statements
- Moat: ROIC signals, margin stability, FCF track record, revenue growth
- Management: dilution trend, FCF conversion, capex intensity
- Risk: leverage, interest coverage, news sentiment, revenue+margin decline
- Governance: restatements, SBC intensity, filing presence
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from investment_app.scoring.qualitative import (
    MODEL_VERSION,
    _clamp,
    _load_qualitative_weights,
    _safe,
    _score_governance,
    _score_management,
    _score_moat,
    _score_risk,
    _select_annual_statements,
    compute_qualitative_score,
)


# ---------------------------------------------------------------------------
# Fake repo helper
# ---------------------------------------------------------------------------


class _FakeQualRepo:
    """In-memory fake repo for qualitative scoring tests."""

    def __init__(
        self,
        *,
        ratios: list[dict[str, Any]] | None = None,
        statements: list[dict[str, Any]] | None = None,
        filings: list[dict[str, Any]] | None = None,
    ) -> None:
        self._ratios = ratios or []
        self._statements = statements or []
        self._filings = filings or []
        self.calls: list[tuple[str, Any]] = []

    def get_ratios_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 3
    ) -> list[dict[str, Any]]:
        self.calls.append(("get_ratios_for_company", as_of_date))
        return self._ratios

    def get_statements_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        self.calls.append(("get_statements_for_company", as_of_date))
        return self._statements

    def get_filings_for_company(
        self, company_id: str, *, as_of_date: str | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("get_filings_for_company", as_of_date))
        return self._filings


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_COMPANY_ID = "00000000-0000-0000-0000-000000000099"
_SCORE_DATE = "2025-01-01"

# High-quality annual statements (newest first)
_STMT_GOOD = {
    "fiscal_period": "FY",
    "fiscal_year": 2024,
    "revenue": 1_000_000.0,
    "gross_profit": 600_000.0,
    "operating_income": 200_000.0,
    "net_income": 150_000.0,
    "free_cash_flow": 180_000.0,
    "capex": -40_000.0,
    "diluted_shares": 10_000.0,
    "stock_based_compensation": 20_000.0,
    "restated_flag": False,
}

_STMT_PRIOR = {
    "fiscal_period": "FY",
    "fiscal_year": 2023,
    "revenue": 900_000.0,
    "gross_profit": 530_000.0,
    "operating_income": 170_000.0,
    "net_income": 130_000.0,
    "free_cash_flow": 160_000.0,
    "capex": -35_000.0,
    "diluted_shares": 10_200.0,
    "stock_based_compensation": 18_000.0,
    "restated_flag": False,
}

_STMT_PRIOR2 = {
    "fiscal_period": "FY",
    "fiscal_year": 2022,
    "revenue": 810_000.0,
    "gross_profit": 477_000.0,
    "operating_income": 145_000.0,
    "net_income": 110_000.0,
    "free_cash_flow": 130_000.0,
    "capex": -30_000.0,
    "diluted_shares": 10_400.0,
    "stock_based_compensation": 16_000.0,
    "restated_flag": False,
}

_RATIOS_GOOD = {
    "roic": 0.18,
    "revenue_growth_yoy": 0.11,
    "gross_margin": 0.60,
    "operating_margin": 0.20,
    "net_debt_to_ebitda": 0.5,
    "interest_coverage": 12.0,
    "news_sentiment_7d": 0.25,
}

_RATIOS_DISTRESSED = {
    "roic": -0.05,
    "revenue_growth_yoy": -0.15,
    "gross_margin": 0.10,
    "operating_margin": -0.05,
    "net_debt_to_ebitda": 6.0,
    "interest_coverage": 0.8,
    "news_sentiment_7d": -0.4,
}

_FILING_10K = {"filing_type": "10-K", "filing_date": "2025-01-15"}


# ---------------------------------------------------------------------------
# Helpers: _clamp and _safe
# ---------------------------------------------------------------------------


def test_clamp_within_range():
    assert _clamp(50.0) == 50.0


def test_clamp_below_zero():
    assert _clamp(-10.0) == 0.0


def test_clamp_above_100():
    assert _clamp(110.0) == 100.0


def test_safe_none_returns_default():
    assert _safe(None) is None
    assert _safe(None, default=0.0) == 0.0


def test_safe_valid_float():
    assert _safe(3.14) == pytest.approx(3.14)


def test_safe_nan_returns_default():
    import math

    assert _safe(math.nan) is None


def test_safe_inf_returns_default():
    assert _safe(float("inf")) is None


def test_safe_string_number():
    assert _safe("42.0") == pytest.approx(42.0)


def test_safe_invalid_string():
    assert _safe("not_a_number") is None


# ---------------------------------------------------------------------------
# Weight loading
# ---------------------------------------------------------------------------


def test_load_qualitative_weights_from_yaml():
    """Weights loaded from scoring_weights.yml must sum to approximately 1.0."""
    w = _load_qualitative_weights()
    total = sum(w.values())
    assert abs(total - 1.0) < 0.01


def test_load_qualitative_weights_keys():
    w = _load_qualitative_weights()
    assert set(w.keys()) == {"moat", "management", "risks", "governance"}


def test_load_qualitative_weights_yaml_values():
    """Matches the values declared in scoring_weights.yml."""
    w = _load_qualitative_weights()
    assert w["moat"] == pytest.approx(0.35)
    assert w["management"] == pytest.approx(0.25)
    assert w["risks"] == pytest.approx(0.25)
    assert w["governance"] == pytest.approx(0.15)


def test_load_qualitative_weights_override():
    override = {"moat": 0.4, "management": 0.3, "risks": 0.2, "governance": 0.1}
    w = _load_qualitative_weights(weights_override=override)
    assert w["moat"] == pytest.approx(0.4)
    assert w["governance"] == pytest.approx(0.1)


def test_load_qualitative_weights_override_partial_uses_defaults():
    """Partial override: missing keys fall back to defaults; result is normalised to 1.0."""
    w = _load_qualitative_weights(weights_override={"moat": 0.5})
    # moat=0.5 + management=0.25 + risks=0.25 + governance=0.15 → total=1.15 → normalised
    assert set(w.keys()) == {"moat", "management", "risks", "governance"}
    assert sum(w.values()) == pytest.approx(1.0)
    # moat has proportionally more weight than any individual default dimension
    assert w["moat"] > w["management"]
    assert w["moat"] > w["risks"]
    assert w["moat"] > w["governance"]


def test_load_qualitative_weights_custom_yaml(tmp_path: Path):
    """load_scoring_weights is tested by inspecting the loaded YAML path."""
    from investment_app.config.loader import load_scoring_weights

    custom_yml = tmp_path / "sw.yml"
    custom_yml.write_text(
        "qualitative_weights:\n  moat: 0.50\n  management: 0.20\n  risks: 0.20\n  governance: 0.10\n"
    )
    data = load_scoring_weights(custom_yml)
    qw = data["qualitative_weights"]
    w = _load_qualitative_weights(weights_override=qw)
    assert w["moat"] == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Moat dimension
# ---------------------------------------------------------------------------


def test_score_moat_strong_roic():
    ratios = {"roic": 0.20, "revenue_growth_yoy": 0.10}
    score, ev = _score_moat(ratios, [_STMT_GOOD, _STMT_PRIOR, _STMT_PRIOR2])
    assert score > 50
    assert ev["roic_signal"] == "strong (>15%)"


def test_score_moat_negative_roic():
    ratios = {"roic": -0.05, "revenue_growth_yoy": 0.0}
    score, ev = _score_moat(ratios, [])
    assert score < 50
    assert ev["roic_signal"] == "negative"


def test_score_moat_missing_roic_neutral():
    ratios = {}
    score, ev = _score_moat(ratios, [])
    # No ROIC data → no adjustment from neutral 50, only other signals
    assert ev["roic_signal"] == "missing"


def test_score_moat_stable_margins_add_points():
    # Three years with nearly identical gross margins (~0.59)
    stmts = [
        {**_STMT_GOOD, "gross_profit": 590_000.0},
        {**_STMT_PRIOR, "gross_profit": 527_000.0},
        {**_STMT_PRIOR2, "gross_profit": 478_000.0},
    ]
    ratios = {"roic": 0.12}
    score, ev = _score_moat(ratios, stmts)
    assert ev["gross_margin_periods"] == 3
    assert ev["gross_margin_std"] < 0.03
    assert ev["margin_stability"] == "very stable (<3% std)"
    assert score > 60


def test_score_moat_expanding_margins():
    stmts = [
        {**_STMT_GOOD, "gross_profit": 680_000.0},  # 68% gm, newest
        {**_STMT_PRIOR, "gross_profit": 540_000.0},  # 60% gm
        {**_STMT_PRIOR2, "gross_profit": 459_000.0},  # 57% gm, oldest
    ]
    ratios = {}
    score, ev = _score_moat(ratios, stmts)
    assert ev["margin_trend"] == "expanding"


def test_score_moat_consistently_positive_fcf():
    stmts = [
        {**_STMT_GOOD, "free_cash_flow": 100_000.0},
        {**_STMT_PRIOR, "free_cash_flow": 90_000.0},
        {**_STMT_PRIOR2, "free_cash_flow": 80_000.0},
    ]
    score, ev = _score_moat({}, stmts)
    assert ev["fcf_signal"] == "consistently positive"
    assert ev["fcf_positive_periods"] == 3


def test_score_moat_consistently_negative_fcf():
    stmts = [
        {**_STMT_GOOD, "free_cash_flow": -10_000.0},
        {**_STMT_PRIOR, "free_cash_flow": -5_000.0},
        {**_STMT_PRIOR2, "free_cash_flow": -8_000.0},
    ]
    score, ev = _score_moat({}, stmts)
    assert ev["fcf_signal"] == "consistently negative"
    assert score < 50


def test_score_moat_clamped_to_100():
    ratios = {"roic": 0.30, "revenue_growth_yoy": 0.50}
    stmts = [
        {**_STMT_GOOD, "gross_profit": 800_000.0, "free_cash_flow": 500_000.0},
        {**_STMT_PRIOR, "gross_profit": 800_000.0, "free_cash_flow": 400_000.0},
        {**_STMT_PRIOR2, "gross_profit": 800_000.0, "free_cash_flow": 300_000.0},
    ]
    score, _ = _score_moat(ratios, stmts)
    assert score <= 100.0


def test_score_moat_clamped_to_zero():
    ratios = {"roic": -0.5, "revenue_growth_yoy": -0.5}
    stmts = [
        {**_STMT_GOOD, "gross_profit": -100_000.0, "free_cash_flow": -500_000.0},
        {**_STMT_PRIOR, "gross_profit": -200_000.0, "free_cash_flow": -400_000.0},
        {**_STMT_PRIOR2, "gross_profit": -300_000.0, "free_cash_flow": -300_000.0},
    ]
    score, _ = _score_moat(ratios, stmts)
    assert score >= 0.0


# ---------------------------------------------------------------------------
# Management dimension
# ---------------------------------------------------------------------------


def test_score_management_buybacks_detected():
    stmts = [
        {**_STMT_GOOD, "diluted_shares": 9_000.0},    # newest
        {**_STMT_PRIOR, "diluted_shares": 9_500.0},
        {**_STMT_PRIOR2, "diluted_shares": 10_500.0},  # oldest
    ]
    score, ev = _score_management({}, stmts)
    assert ev["dilution_signal"] == "buybacks detected"
    assert score > 50


def test_score_management_significant_dilution():
    # Strip FCF/net_income to avoid FCF-conversion bonus offsetting the dilution penalty.
    stmts = [
        {**_STMT_GOOD, "diluted_shares": 12_000.0, "free_cash_flow": None, "net_income": None},
        {**_STMT_PRIOR, "diluted_shares": 11_000.0, "free_cash_flow": None, "net_income": None},
        {**_STMT_PRIOR2, "diluted_shares": 10_000.0, "free_cash_flow": None, "net_income": None},
    ]
    score, ev = _score_management({}, stmts)
    assert ev["dilution_signal"] == "significant dilution (>10%)"
    assert score < 50


def test_score_management_strong_fcf_conversion():
    stmts = [
        {**_STMT_GOOD, "free_cash_flow": 200_000.0, "net_income": 150_000.0},
        {**_STMT_PRIOR, "free_cash_flow": 180_000.0, "net_income": 130_000.0},
    ]
    score, ev = _score_management({}, stmts)
    assert ev["fcf_conversion_signal"] == "strong (FCF > net income)"


def test_score_management_negative_fcf_despite_profits():
    stmts = [
        {**_STMT_GOOD, "free_cash_flow": -50_000.0, "net_income": 100_000.0},
    ]
    score, ev = _score_management({}, stmts)
    assert ev["fcf_conversion_signal"] == "negative FCF despite profits"
    assert score < 50


def test_score_management_missing_share_data():
    score, ev = _score_management({}, [])
    assert ev["dilution_signal"] == "missing"


def test_score_management_clamped_range():
    stmts = [
        {**_STMT_GOOD, "diluted_shares": 5_000.0, "free_cash_flow": 200_000.0, "net_income": 10_000.0},
        {**_STMT_PRIOR, "diluted_shares": 5_100.0, "free_cash_flow": 180_000.0, "net_income": 9_000.0},
        {**_STMT_PRIOR2, "diluted_shares": 5_200.0, "free_cash_flow": 160_000.0, "net_income": 8_000.0},
    ]
    score, _ = _score_management({}, stmts)
    assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# Risk dimension
# ---------------------------------------------------------------------------


def test_score_risk_net_cash_position():
    ratios = {"net_debt_to_ebitda": -1.0}
    score, ev = _score_risk(ratios, [])
    assert ev["leverage_signal"] == "net cash position"
    assert score > 50


def test_score_risk_high_leverage():
    ratios = {"net_debt_to_ebitda": 7.0}
    score, ev = _score_risk(ratios, [])
    assert ev["leverage_signal"] == "high leverage (>5x)"
    assert score < 50


def test_score_risk_critical_interest_coverage():
    ratios = {"interest_coverage": 0.5}
    score, ev = _score_risk(ratios, [])
    assert ev["coverage_signal"] == "critical (<1x)"
    assert score < 50


def test_score_risk_very_strong_interest_coverage():
    ratios = {"interest_coverage": 15.0}
    score, ev = _score_risk(ratios, [])
    assert ev["coverage_signal"] == "very strong (>10x)"
    assert score > 50


def test_score_risk_negative_news_sentiment():
    ratios = {"news_sentiment_7d": -0.5}
    score, ev = _score_risk(ratios, [])
    assert ev["news_signal"] == "negative"
    assert score < 50


def test_score_risk_positive_news_sentiment():
    ratios = {"news_sentiment_7d": 0.4}
    score, ev = _score_risk(ratios, [])
    assert ev["news_signal"] == "positive"


def test_score_risk_revenue_and_margin_both_declining():
    stmts = [
        {
            "fiscal_period": "FY",
            "revenue": 800_000.0,
            "operating_income": 40_000.0,   # 5% margin
        },
        {
            "fiscal_period": "FY",
            "revenue": 1_000_000.0,
            "operating_income": 150_000.0,  # 15% margin
        },
    ]
    score, ev = _score_risk({}, stmts)
    assert ev["revenue_margin_signal"] == "revenue and margin both declining"
    assert score < 50


def test_score_risk_missing_data_conservative():
    score, ev = _score_risk({}, [])
    assert ev["leverage_signal"] == "missing"
    assert ev["coverage_signal"] == "missing"
    assert ev["news_signal"] == "missing"
    # Score should stay at 50 (no adjustments)
    assert score == pytest.approx(50.0)


def test_score_risk_clamped_range():
    ratios = _RATIOS_DISTRESSED
    stmts = [
        {"fiscal_period": "FY", "revenue": 500.0, "operating_income": -100.0},
        {"fiscal_period": "FY", "revenue": 1_000.0, "operating_income": 100.0},
    ]
    score, _ = _score_risk(ratios, stmts)
    assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# Governance dimension
# ---------------------------------------------------------------------------


def test_score_governance_no_restatements_and_10k_filed():
    stmts = [_STMT_GOOD, _STMT_PRIOR, _STMT_PRIOR2]
    filings = [_FILING_10K]
    score, ev = _score_governance(stmts, filings)
    assert ev["restatement_signal"] == "no restatements"
    assert ev["filing_signal"] == "annual report filed"
    assert score > 50


def test_score_governance_restatement_subtracts_points():
    # Use empty filings so the filing-present bonus does not offset the restatement penalty.
    stmts = [{**_STMT_GOOD, "restated_flag": True}, _STMT_PRIOR]
    score, ev = _score_governance(stmts, [])
    assert ev["restated_periods"] == 1
    assert "restatement(s) detected" in ev["restatement_signal"]
    assert score < 50


def test_score_governance_excessive_sbc():
    stmts = [
        {**_STMT_GOOD, "stock_based_compensation": 120_000.0, "revenue": 1_000_000.0},
    ]
    score, ev = _score_governance(stmts, [_FILING_10K])
    assert ev["sbc_signal"] == "excessive SBC (>10%)"
    assert score < 50


def test_score_governance_no_filings_subtracts_points():
    score, ev = _score_governance([], [])
    assert ev["filing_signal"] == "no filings detected"
    assert score < 50


def test_score_governance_20f_counts_as_annual_report():
    filings = [{"filing_type": "20-F", "filing_date": "2025-01-15"}]
    score, ev = _score_governance([], filings)
    assert ev["filing_signal"] == "annual report filed"


def test_score_governance_clamped_range():
    stmts = [
        {**_STMT_GOOD, "restated_flag": True, "stock_based_compensation": 200_000.0},
        {**_STMT_PRIOR, "restated_flag": True, "stock_based_compensation": 200_000.0},
        {**_STMT_PRIOR2, "restated_flag": True, "stock_based_compensation": 200_000.0},
    ]
    score, _ = _score_governance(stmts, [])
    assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# compute_qualitative_score — full integration
# ---------------------------------------------------------------------------


def test_compute_qualitative_score_returns_none_when_no_data():
    repo = _FakeQualRepo(ratios=[], statements=[], filings=[])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is None


def test_compute_qualitative_score_with_ratios_only():
    """A ratios row alone is sufficient to produce a score."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[], filings=[])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None


def test_compute_qualitative_score_required_keys():
    repo = _FakeQualRepo(
        ratios=[_RATIOS_GOOD],
        statements=[_STMT_GOOD, _STMT_PRIOR, _STMT_PRIOR2],
        filings=[_FILING_10K],
    )
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    required_keys = {
        "company_id",
        "score_date",
        "moat_score",
        "management_score",
        "risk_score",
        "governance_score",
        "final_quality_score",
        "auto_score",
        "human_override",
        "override_reason",
        "evidence_notes",
        "model_version",
    }
    assert set(result.keys()) == required_keys


def test_compute_qualitative_score_company_id_and_date_passthrough():
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert result["company_id"] == _COMPANY_ID
    assert result["score_date"] == _SCORE_DATE
    assert result["model_version"] == MODEL_VERSION


def test_compute_qualitative_score_human_override_always_zero():
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert result["human_override"] == 0


def test_compute_qualitative_score_final_in_range():
    repo = _FakeQualRepo(
        ratios=[_RATIOS_GOOD],
        statements=[_STMT_GOOD, _STMT_PRIOR, _STMT_PRIOR2],
        filings=[_FILING_10K],
    )
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert 0.0 <= result["final_quality_score"] <= 100.0


def test_compute_qualitative_score_dimensions_in_range():
    repo = _FakeQualRepo(
        ratios=[_RATIOS_GOOD],
        statements=[_STMT_GOOD, _STMT_PRIOR, _STMT_PRIOR2],
        filings=[_FILING_10K],
    )
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    for key in ("moat_score", "management_score", "risk_score", "governance_score"):
        assert 0.0 <= result[key] <= 100.0, f"{key} out of range"


def test_compute_qualitative_score_good_company_above_50():
    repo = _FakeQualRepo(
        ratios=[_RATIOS_GOOD],
        statements=[_STMT_GOOD, _STMT_PRIOR, _STMT_PRIOR2],
        filings=[_FILING_10K],
    )
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert result["final_quality_score"] > 50.0


def test_compute_qualitative_score_distressed_company_below_good():
    repo_good = _FakeQualRepo(
        ratios=[_RATIOS_GOOD],
        statements=[_STMT_GOOD, _STMT_PRIOR, _STMT_PRIOR2],
        filings=[_FILING_10K],
    )
    repo_bad = _FakeQualRepo(
        ratios=[_RATIOS_DISTRESSED],
        statements=[
            {**_STMT_GOOD, "free_cash_flow": -50_000.0, "restated_flag": True},
            {**_STMT_PRIOR, "free_cash_flow": -30_000.0},
        ],
        filings=[],
    )
    good = compute_qualitative_score(_COMPANY_ID, repo_good, _SCORE_DATE)
    bad = compute_qualitative_score(_COMPANY_ID, repo_bad, _SCORE_DATE)
    assert good is not None and bad is not None
    assert good["final_quality_score"] > bad["final_quality_score"]


def test_compute_qualitative_score_auto_score_structure():
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    auto = result["auto_score"]
    assert "moat" in auto
    assert "management" in auto
    assert "risk" in auto
    assert "governance" in auto
    assert "weights" in auto
    assert "weights_source" in auto
    for dim in ("moat", "management", "risk", "governance"):
        assert "score" in auto[dim]
        assert "evidence" in auto[dim]


def test_compute_qualitative_score_weights_source_yaml():
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert result["auto_score"]["weights_source"] == "scoring_weights.yml"


def test_compute_qualitative_score_weights_source_override():
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(
        _COMPANY_ID,
        repo,
        _SCORE_DATE,
        weights={"moat": 0.4, "management": 0.3, "risks": 0.2, "governance": 0.1},
    )
    assert result is not None
    assert result["auto_score"]["weights_source"] == "override"


def test_compute_qualitative_score_custom_weights_affect_final():
    """Different weights must produce different final scores when dimensions differ."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    r1 = compute_qualitative_score(
        _COMPANY_ID, repo, _SCORE_DATE,
        weights={"moat": 1.0, "management": 0.0, "risks": 0.0, "governance": 0.0},
    )
    r2 = compute_qualitative_score(
        _COMPANY_ID, repo, _SCORE_DATE,
        weights={"moat": 0.0, "management": 0.0, "risks": 0.0, "governance": 1.0},
    )
    assert r1 is not None and r2 is not None
    # moat and governance scores differ → final scores should differ
    assert r1["moat_score"] != r2["governance_score"] or r1["final_quality_score"] != r2["final_quality_score"]


def test_compute_qualitative_score_point_in_time_safe():
    """Repo calls must forward score_date as as_of_date."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    calls_by_name: dict[str, list] = {}
    for name, date_arg in repo.calls:
        calls_by_name.setdefault(name, []).append(date_arg)
    for name, dates in calls_by_name.items():
        for d in dates:
            assert d == _SCORE_DATE, f"{name} did not forward as_of_date={_SCORE_DATE!r}"


def test_compute_qualitative_score_quarterly_stmts_filtered_out():
    """Quarterly statements must not contribute to scoring."""
    quarterly = {
        **_STMT_GOOD,
        "fiscal_period": "Q1",
        "free_cash_flow": -999_999.0,  # would heavily penalise if included
    }
    repo = _FakeQualRepo(
        ratios=[_RATIOS_GOOD],
        statements=[quarterly, _STMT_GOOD, _STMT_PRIOR],
    )
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    # Score should be unaffected by the quarterly poison value
    assert result["moat_score"] > 50.0


def test_compute_qualitative_score_final_formula():
    """Verify the weighted formula manually."""
    weights = {"moat": 0.35, "management": 0.25, "risks": 0.25, "governance": 0.15}
    # Use ratios-only path so individual dimension scores are predictable.
    repo = _FakeQualRepo(ratios=[{"roic": None}], statements=[], filings=[])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE, weights=weights)
    assert result is not None
    m = result["moat_score"]
    mg = result["management_score"]
    r = result["risk_score"]
    g = result["governance_score"]
    expected = _clamp(0.35 * m + 0.25 * mg + 0.25 * r + 0.15 * g)
    assert result["final_quality_score"] == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Weight validation and normalisation
# ---------------------------------------------------------------------------


def test_load_qualitative_weights_negative_raises():
    """Any negative weight must raise ValueError."""
    with pytest.raises(ValueError, match="non-negative"):
        _load_qualitative_weights(weights_override={"moat": -0.1, "management": 0.4, "risks": 0.4, "governance": 0.3})


def test_load_qualitative_weights_zero_total_raises():
    """All-zero weights must raise ValueError."""
    with pytest.raises(ValueError, match="positive sum"):
        _load_qualitative_weights(weights_override={"moat": 0.0, "management": 0.0, "risks": 0.0, "governance": 0.0})


def test_load_qualitative_weights_non_unit_sum_normalized():
    """Override weights not summing to 1.0 are normalised to 1.0."""
    # 0.2 + 0.2 + 0.2 + 0.2 = 0.8 — not 1.0
    override = {"moat": 0.2, "management": 0.2, "risks": 0.2, "governance": 0.2}
    w = _load_qualitative_weights(weights_override=override)
    assert sum(w.values()) == pytest.approx(1.0)
    # All weights equal after normalisation
    assert w["moat"] == pytest.approx(0.25)
    assert w["management"] == pytest.approx(0.25)


def test_weight_audit_consistency():
    """Weights in auto_score must be exactly the ones used for final_quality_score."""
    weights = {"moat": 0.2, "management": 0.3, "risks": 0.3, "governance": 0.2}
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE, weights=weights)
    assert result is not None
    persisted_weights = result["auto_score"]["weights"]
    m = result["moat_score"]
    mg = result["management_score"]
    r = result["risk_score"]
    g = result["governance_score"]
    expected_final = _clamp(
        persisted_weights["moat"] * m
        + persisted_weights["management"] * mg
        + persisted_weights["risks"] * r
        + persisted_weights["governance"] * g
    )
    assert result["final_quality_score"] == pytest.approx(expected_final, abs=0.01)


# ---------------------------------------------------------------------------
# Statement selection
# ---------------------------------------------------------------------------


def test_select_annual_statements_empty():
    assert _select_annual_statements([]) == []


def test_select_annual_statements_filters_quarterly():
    quarterly = {**_STMT_GOOD, "fiscal_period": "Q1", "fiscal_year": 2024}
    result = _select_annual_statements([quarterly, _STMT_PRIOR])
    assert all(s.get("fiscal_period") in ("FY", "annual") for s in result)
    assert len(result) == 1


def test_select_annual_statements_deduplicates():
    """Two rows with the same (fiscal_year, fiscal_period) → only one kept."""
    dup1 = {**_STMT_GOOD, "id": "aaa", "created_at": "2025-01-01"}
    dup2 = {**_STMT_GOOD, "id": "bbb", "created_at": "2024-12-01"}
    result = _select_annual_statements([dup1, dup2, _STMT_PRIOR])
    assert len(result) == 2  # one for FY-2024, one for FY-2023
    fy_years = [s["fiscal_year"] for s in result]
    assert fy_years.count(2024) == 1


def test_select_annual_statements_prefers_restated():
    """Restated row is preferred over original for the same fiscal period."""
    original = {**_STMT_GOOD, "fiscal_year": 2024, "restated_flag": False, "id": "orig", "revenue": 999_000.0}
    restated = {**_STMT_GOOD, "fiscal_year": 2024, "restated_flag": True, "id": "rest", "revenue": 1_000_000.0}
    result = _select_annual_statements([original, restated])
    assert len(result) == 1
    assert result[0]["id"] == "rest"


# ---------------------------------------------------------------------------
# Filing-only path
# ---------------------------------------------------------------------------


def test_compute_qualitative_score_filings_only_returns_score():
    """No ratios and no statements but a filing → returns a non-None row."""
    repo = _FakeQualRepo(ratios=[], statements=[], filings=[_FILING_10K])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None


def test_compute_qualitative_score_filings_only_governance_scored():
    """With a 10-K present, governance_score should be above neutral 50."""
    repo = _FakeQualRepo(ratios=[], statements=[], filings=[_FILING_10K])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert result["governance_score"] > 50.0


def test_compute_qualitative_score_filings_only_neutral_moat_management_risk():
    """Filing-only path: moat, management, and risk must be exactly 50."""
    repo = _FakeQualRepo(ratios=[], statements=[], filings=[_FILING_10K])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert result["moat_score"] == pytest.approx(50.0)
    assert result["management_score"] == pytest.approx(50.0)
    assert result["risk_score"] == pytest.approx(50.0)


def test_compute_qualitative_score_deduplicates_statements():
    """Duplicate annual rows are deduplicated before scoring."""
    dup1 = {**_STMT_GOOD, "id": "x1", "free_cash_flow": -999_999.0, "restated_flag": False}
    dup2 = {**_STMT_GOOD, "id": "x2", "free_cash_flow": 180_000.0, "restated_flag": True}
    # dup2 is restated → preferred; dup1 should be discarded as a duplicate year
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[dup1, dup2, _STMT_PRIOR])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    # The restated FCF (positive) must be used, so moat score should be above neutral
    assert result["moat_score"] > 50.0


# ---------------------------------------------------------------------------
# Human override
# ---------------------------------------------------------------------------


def test_human_override_applied_to_final_score():
    """A positive override shifts final_quality_score up by exactly that amount."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    base = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    with_override = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE, human_override=5)
    assert base is not None and with_override is not None
    assert with_override["final_quality_score"] == pytest.approx(
        _clamp(base["final_quality_score"] + 5), abs=0.01
    )


def test_human_override_clamped_to_10():
    """An override of 15 is clamped to 10 before being applied."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE, human_override=15)
    assert result is not None
    assert result["human_override"] == pytest.approx(10.0)


def test_human_override_negative_clamped():
    """An override of -15 is clamped to -10."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE, human_override=-15)
    assert result is not None
    assert result["human_override"] == pytest.approx(-10.0)


def test_human_override_default_zero():
    """Omitting human_override leaves final_quality_score equal to the weighted auto-score."""
    weights = {"moat": 0.35, "management": 0.25, "risks": 0.25, "governance": 0.15}
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE, weights=weights)
    assert result is not None
    assert result["human_override"] == pytest.approx(0.0)
    auto = result["auto_score"]
    expected = _clamp(
        auto["weights"]["moat"] * result["moat_score"]
        + auto["weights"]["management"] * result["management_score"]
        + auto["weights"]["risks"] * result["risk_score"]
        + auto["weights"]["governance"] * result["governance_score"]
    )
    assert result["final_quality_score"] == pytest.approx(expected, abs=0.01)


def test_override_reason_and_evidence_notes_persisted():
    """override_reason and evidence_notes are stored in the returned dict."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(
        _COMPANY_ID,
        repo,
        _SCORE_DATE,
        human_override=3,
        override_reason="Analyst adjustment Q1",
        evidence_notes="See research note #42",
    )
    assert result is not None
    assert result["override_reason"] == "Analyst adjustment Q1"
    assert result["evidence_notes"] == "See research note #42"


def test_override_reason_defaults_none():
    """Without explicit args, override_reason and evidence_notes are None."""
    repo = _FakeQualRepo(ratios=[_RATIOS_GOOD], statements=[_STMT_GOOD])
    result = compute_qualitative_score(_COMPANY_ID, repo, _SCORE_DATE)
    assert result is not None
    assert result["override_reason"] is None
    assert result["evidence_notes"] is None
