"""Unit tests for Phase 6 probabilistic signal scoring."""
from __future__ import annotations

import math
from typing import Any

import pytest

from investment_app.scoring.probabilistic import MODEL_VERSION, compute_signal_run
from investment_app.scoring.rule_based import load_rule_score_weights


class _FakeSignalRepo:
    """In-memory repo fake for signal computation tests."""

    def __init__(
        self,
        *,
        valuation: dict[str, Any] | None = None,
        qualitative: dict[str, Any] | None = None,
        ratios: list[dict[str, Any]] | None = None,
        prices: list[dict[str, Any]] | None = None,
        filings: list[dict[str, Any]] | None = None,
    ) -> None:
        self._valuation = valuation
        self._qualitative = qualitative
        self._ratios = ratios or []
        self._prices = prices or []
        self._filings = filings or []
        self.calls: list[tuple[str, Any]] = []

    def get_latest_valuation_run(
        self, company_id: str, *, as_of_date: str | None = None
    ) -> dict[str, Any] | None:
        self.calls.append(("get_latest_valuation_run", as_of_date))
        return self._valuation

    def get_latest_qualitative_score(
        self, company_id: str, *, as_of_date: str | None = None
    ) -> dict[str, Any] | None:
        self.calls.append(("get_latest_qualitative_score", as_of_date))
        return self._qualitative

    def get_ratios_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 1
    ) -> list[dict[str, Any]]:
        self.calls.append(("get_ratios_for_company", as_of_date))
        return self._ratios

    def get_prices_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 1
    ) -> list[dict[str, Any]]:
        self.calls.append(("get_prices_for_company", as_of_date))
        return self._prices

    def get_filings_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        self.calls.append(("get_filings_for_company", as_of_date))
        return self._filings


_COMPANY_ID = "00000000-0000-0000-0000-000000000111"
_SIGNAL_DATE = "2025-01-01"

_VALUATION_GOOD = {
    "id": "val-001",
    "valuation_date": _SIGNAL_DATE,
    "iv_p10": 130.0,
    "iv_p25": 150.0,
    "iv_p50": 170.0,
    "iv_p75": 190.0,
    "iv_p90": 200.0,
    "current_price": 100.0,
    "margin_of_safety_conservative": 0.30,
    "uncertainty_width": 0.20,
    "assumptions": {"diagnostics": {"freshness_flag": "ok", "blockers": [], "warnings": []}},
}

_QUAL_GOOD = {
    "id": "qual-001",
    "score_date": _SIGNAL_DATE,
    "final_quality_score": 78.0,
}

_RATIO_GOOD = {
    "factor_date": _SIGNAL_DATE,
    "net_debt_to_ebitda": 0.20,
    "interest_coverage": 12.0,
    "news_sentiment_7d": 0.25,
    "news_volume_7d": 5,
    "momentum_60d": 0.12,
    "momentum_250d": 0.20,
    "volatility_90d": 0.18,
    "data_quality_score": 85.0,
}

_PRICE_GOOD = {"price_date": _SIGNAL_DATE, "close": 100.0}
_FILING_10K = {"filing_type": "10-K", "filing_date": "2024-12-10"}


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _family_scores(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["name"]: item
        for item in result["top_feature_contributors"]
        if item.get("kind") == "family"
    }


def _adjustment(result: dict[str, Any], name: str) -> dict[str, Any]:
    for item in result["top_feature_contributors"]:
        if item.get("name") == name:
            return item
    raise AssertionError(f"missing contributor {name}")


def _reasoning_metadata(result: dict[str, Any]) -> dict[str, Any]:
    return _adjustment(result, "signal_reasoning_metadata")["value"]


def test_compute_signal_run_returns_required_keys():
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
    assert result["model_version"] == MODEL_VERSION


def test_final_signal_is_sql_valid():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] in {
        "strong_buy",
        "buy",
        "hold",
        "sell",
        "strong_sell",
        "insufficient_data",
    }


def test_probabilities_are_bounded():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert 0.0 <= result["p_buy"] <= 1.0
    assert 0.0 <= result["p_buy_adjusted"] <= 1.0
    assert 0.0 <= result["p_sell"] <= 1.0


def test_signal_formula_correctness():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    families = _family_scores(result)
    weighted_rule_score = sum(item["score"] * item["weight"] for item in families.values())
    expected_p_buy = _sigmoid((weighted_rule_score - 50.0) / 12.0)
    assert result["p_buy"] == pytest.approx(expected_p_buy, abs=1e-4)

    quality_multiplier = _adjustment(result, "quality_confidence_multiplier")["value"]
    risk_penalty = _adjustment(result, "risk_penalty")["value"]
    uncertainty_penalty = _adjustment(result, "uncertainty_penalty")["value"]
    expected_adjusted = expected_p_buy * quality_multiplier * (1.0 - risk_penalty) * (1.0 - uncertainty_penalty)
    assert result["p_buy_adjusted"] == pytest.approx(expected_adjusted, abs=1e-4)


def test_signal_strong_buy_threshold_classification():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] == "strong_buy"
    assert result["p_buy_adjusted"] >= 0.70


def test_missing_valuation_is_conservative():
    repo = _FakeSignalRepo(
        valuation=None,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] == "hold"
    assert "missing_valuation" in result["red_flags"]
    assert result["p_buy_adjusted"] < 0.60
    reasoning = _reasoning_metadata(result)
    assert reasoning["valuation_used_in_signal"] is False
    assert "valuation_missing" in reasoning["confidence_limiter_codes"]


def test_unreliable_valuation_blocks_valuation_only_strong_conclusions():
    valuation_unreliable = {
        **_VALUATION_GOOD,
        "current_price": 220.0,
        "iv_p75": 110.0,
        "margin_of_safety_conservative": -0.50,
        "assumptions": {
            "diagnostics": {
                "freshness_flag": "ok",
                "blockers": [],
                "warnings": [],
                "valuation_sanity_status": "unreliable",
                "valuation_signal_influence_blocked": True,
            }
        },
    }
    repo = _FakeSignalRepo(
        valuation=valuation_unreliable,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] != "strong_sell"
    assert "valuation_unreliable" in result["red_flags"]
    assert "overvalued_vs_iv_p75" not in result["red_flags"]
    reasoning = _reasoning_metadata(result)
    assert reasoning["valuation_used_in_signal"] is False
    assert reasoning["hold_reason"] == "valuation_unreliable_hold"
    assert "valuation_unreliable" in reasoning["confidence_limiter_codes"]


def test_reasoning_metadata_embeds_internal_score_note_and_no_language_warning():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    reasoning = _reasoning_metadata(result)
    assert reasoning["probability_interpretation_note"].startswith("Internal rule-based model scores")
    assert reasoning["recommendation_language_warning"] is None
    assert "probability" not in result["explanation"].lower()


def test_reasoning_metadata_marks_risk_driven_strong_sell():
    valuation = {
        **_VALUATION_GOOD,
        "current_price": 108.0,
        "iv_p50": 100.0,
        "iv_p75": 120.0,
        "uncertainty_width": 1.60,
        "margin_of_safety_conservative": -0.02,
    }
    ratios = {
        **_RATIO_GOOD,
        "net_debt_to_ebitda": 6.5,
    }
    repo = _FakeSignalRepo(
        valuation=valuation,
        qualitative=_QUAL_GOOD,
        ratios=[ratios],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] == "strong_sell"
    reasoning = _reasoning_metadata(result)
    assert reasoning["strong_sell_basis"] == "risk"
    assert reasoning["risk_override_applied"] is True


def test_missing_qualitative_score_is_conservative():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=None,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert "missing_qualitative_score" in result["red_flags"]
    assert result["final_signal"] == "hold"


def test_stale_inputs_flagged_conservatively():
    repo = _FakeSignalRepo(
        valuation={**_VALUATION_GOOD, "valuation_date": "2024-11-01"},
        qualitative={**_QUAL_GOOD, "score_date": "2024-11-01"},
        ratios=[{**_RATIO_GOOD, "factor_date": "2024-11-01"}],
        prices=[{**_PRICE_GOOD, "price_date": "2024-12-20"}],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["freshness_flag"] == "stale"
    assert result["final_signal"] == "hold"


def test_high_risk_adjustment_reduces_buy_probability():
    risky_ratio = {
        **_RATIO_GOOD,
        "net_debt_to_ebitda": 6.0,
        "interest_coverage": 0.8,
        "news_sentiment_7d": -0.35,
        "momentum_60d": -0.15,
        "momentum_250d": -0.20,
        "volatility_90d": 0.55,
    }
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[risky_ratio],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["p_buy_adjusted"] < result["p_buy"]
    assert any(flag in result["red_flags"] for flag in ("high_leverage", "critical_interest_coverage"))
    assert result["final_signal"] in {"strong_sell", "sell"}


def test_conflicting_valuation_and_quality_evidence_avoids_buy():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative={**_QUAL_GOOD, "final_quality_score": 28.0},
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] in {"strong_sell", "sell"}
    assert "quality_breakdown" in result["red_flags"]


def test_missing_core_inputs_returns_insufficient_data():
    repo = _FakeSignalRepo(
        valuation=None,
        qualitative=None,
        ratios=[],
        prices=[_PRICE_GOOD],
        filings=[],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] == "insufficient_data"


def test_hard_red_flags_force_strong_sell_when_p_sell_elevated():
    """PR 11A.4 (signal_rule_v1): quality_score=25 generates quality_breakdown,
    which is both a hard red flag and a confirming bearish flag.  With quality
    this low, _sell_probability exceeds 0.60, so the signal is strong_sell
    (p_sell >= 0.60 AND confirming flag) rather than plain sell.
    """
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative={**_QUAL_GOOD, "final_quality_score": 25.0},
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    assert result is not None
    assert result["final_signal"] == "strong_sell"


def test_load_rule_score_weights_negative_raises():
    with pytest.raises(ValueError, match="non-negative"):
        load_rule_score_weights({
            "valuation": -0.1,
            "quality": 0.4,
            "balance_sheet": 0.3,
            "news": 0.2,
            "market_regime": 0.2,
        })


def test_load_rule_score_weights_zero_total_raises():
    with pytest.raises(ValueError, match="positive"):
        load_rule_score_weights({
            "valuation": 0.0,
            "quality": 0.0,
            "balance_sheet": 0.0,
            "news": 0.0,
            "market_regime": 0.0,
        })


def test_load_rule_score_weights_nan_raises():
    with pytest.raises(ValueError, match="finite"):
        load_rule_score_weights({
            "valuation": math.nan,
            "quality": 0.25,
            "balance_sheet": 0.25,
            "news": 0.25,
            "market_regime": 0.25,
        })


def test_load_rule_score_weights_infinite_raises():
    with pytest.raises(ValueError, match="finite"):
        load_rule_score_weights({
            "valuation": float("inf"),
            "quality": 0.25,
            "balance_sheet": 0.25,
            "news": 0.25,
            "market_regime": 0.25,
        })


def test_load_rule_score_weights_non_numeric_raises():
    with pytest.raises(ValueError, match="numeric"):
        load_rule_score_weights({
            "valuation": "abc",
            "quality": 0.25,
            "balance_sheet": 0.25,
            "news": 0.25,
            "market_regime": 0.25,
        })


def test_load_rule_score_weights_normalizes_non_unit_sum():
    weights = load_rule_score_weights({
        "valuation": 4.0,
        "quality": 2.5,
        "balance_sheet": 1.5,
        "news": 1.0,
        "market_regime": 1.0,
    })
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["valuation"] == pytest.approx(0.4)
    assert weights["quality"] == pytest.approx(0.25)


def test_rule_weights_used_match_normalized_contributors():
    override = {
        "valuation": 8.0,
        "quality": 5.0,
        "balance_sheet": 3.0,
        "news": 2.0,
        "market_regime": 2.0,
    }
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    result = compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE, weights=override)
    assert result is not None
    expected = load_rule_score_weights(override)
    families = _family_scores(result)
    assert families["valuation"]["weight"] == pytest.approx(expected["valuation"], abs=1e-4)
    assert families["quality"]["weight"] == pytest.approx(expected["quality"], abs=1e-4)


def test_point_in_time_reads_forward_signal_date():
    repo = _FakeSignalRepo(
        valuation=_VALUATION_GOOD,
        qualitative=_QUAL_GOOD,
        ratios=[_RATIO_GOOD],
        prices=[_PRICE_GOOD],
        filings=[_FILING_10K],
    )
    compute_signal_run(_COMPANY_ID, repo, _SIGNAL_DATE)
    for _, as_of_date in repo.calls:
        assert as_of_date == _SIGNAL_DATE