"""Rule-based helpers for Phase 6 probabilistic signal scoring."""
from __future__ import annotations

import math
from typing import Any

from investment_app.config.loader import load_scoring_weights


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
	"""Clamp *value* to the closed interval [lo, hi]."""
	return max(lo, min(hi, value))


def _clamp01(value: float) -> float:
	"""Clamp *value* to [0, 1]."""
	return _clamp(value, 0.0, 1.0)


def _safe(value: Any, default: float | None = None) -> float | None:
	"""Return *value* as float, or *default* if missing / invalid."""
	if value is None:
		return default
	try:
		numeric = float(value)
	except (TypeError, ValueError):
		return default
	return numeric if math.isfinite(numeric) else default


def sigmoid(value: float) -> float:
	"""Numerically-stable sigmoid."""
	if value >= 0:
		z = math.exp(-value)
		return 1.0 / (1.0 + z)
	z = math.exp(value)
	return z / (1.0 + z)


def load_rule_score_weights(
	weights_override: dict[str, Any] | None = None,
) -> dict[str, float]:
	"""Return validated, normalised rule-score weights."""
	if weights_override is not None:
		section = weights_override
	else:
		config = load_scoring_weights()
		section = config.get("rule_score_weights", {})

	try:
		raw = {
			"valuation": float(section.get("valuation", 0.40)),
			"quality": float(section.get("quality", 0.25)),
			"balance_sheet": float(section.get("balance_sheet", 0.15)),
			"news": float(section.get("news", 0.10)),
			"market_regime": float(section.get("market_regime", 0.10)),
		}
	except (TypeError, ValueError) as exc:
		raise ValueError(f"Rule-score weights must be numeric; got {section}") from exc

	if any(not math.isfinite(value) for value in raw.values()):
		raise ValueError(f"Rule-score weights must be finite; got {raw}")
	if any(value < 0 for value in raw.values()):
		raise ValueError(f"Rule-score weights must be non-negative; got {raw}")
	total = sum(raw.values())
	if total <= 0.0:
		raise ValueError(f"Rule-score weights must sum to a positive value; got {raw}")
	return {key: value / total for key, value in raw.items()}


def score_valuation_family(valuation_row: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
	"""Score valuation attractiveness on a 0-100 scale."""
	if not valuation_row:
		return 35.0, {
			"margin_of_safety_conservative": None,
			"uncertainty_width": None,
			"signal": "missing valuation",
		}

	mos = _safe(valuation_row.get("margin_of_safety_conservative"))
	current_price = _safe(valuation_row.get("current_price"))
	iv_p25 = _safe(valuation_row.get("iv_p25"))
	iv_p50 = _safe(valuation_row.get("iv_p50"))
	iv_p75 = _safe(valuation_row.get("iv_p75"))
	uncertainty = _safe(valuation_row.get("uncertainty_width"))

	evidence: dict[str, Any] = {
		"margin_of_safety_conservative": mos,
		"current_price": current_price,
		"iv_p25": iv_p25,
		"iv_p50": iv_p50,
		"iv_p75": iv_p75,
		"uncertainty_width": uncertainty,
	}

	if mos is None:
		score = 40.0
		evidence["mos_signal"] = "missing"
	elif mos >= 0.25:
		score = 90.0
		evidence["mos_signal"] = ">=25%"
	elif mos >= 0.15:
		score = 75.0
		evidence["mos_signal"] = ">=15%"
	elif mos >= 0.10:
		score = 65.0
		evidence["mos_signal"] = ">=10%"
	elif mos >= 0.0:
		score = 55.0
		evidence["mos_signal"] = "0-10%"
	elif mos >= -0.10:
		score = 40.0
		evidence["mos_signal"] = "negative but above -10%"
	else:
		score = 25.0
		evidence["mos_signal"] = "below -10%"

	if current_price is not None and iv_p25 is not None and current_price <= iv_p25:
		score += 5.0
		evidence["price_vs_iv"] = "below_or_equal_iv_p25"
	elif current_price is not None and iv_p50 is not None and current_price <= iv_p50:
		score += 2.0
		evidence["price_vs_iv"] = "below_or_equal_iv_p50"
	elif current_price is not None and iv_p75 is not None and current_price > iv_p75:
		score -= 12.0
		evidence["price_vs_iv"] = "above_iv_p75"
	elif current_price is not None and iv_p50 is not None and current_price > iv_p50:
		score -= 5.0
		evidence["price_vs_iv"] = "above_iv_p50"
	else:
		evidence["price_vs_iv"] = "neutral_or_missing"

	if uncertainty is not None:
		if uncertainty > 1.20:
			score -= 15.0
			evidence["uncertainty_signal"] = ">120% width"
		elif uncertainty > 0.80:
			score -= 10.0
			evidence["uncertainty_signal"] = ">80% width"
		elif uncertainty > 0.50:
			score -= 6.0
			evidence["uncertainty_signal"] = ">50% width"
		elif uncertainty > 0.25:
			score -= 3.0
			evidence["uncertainty_signal"] = ">25% width"
		else:
			evidence["uncertainty_signal"] = "contained"
	else:
		evidence["uncertainty_signal"] = "missing"

	return _clamp(score), evidence


def score_balance_sheet_family(ratio_row: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
	"""Score balance-sheet resilience on a 0-100 scale."""
	evidence: dict[str, Any] = {}
	if not ratio_row:
		return 45.0, {"signal": "missing ratio inputs"}

	score = 50.0
	net_debt_ebitda = _safe(ratio_row.get("net_debt_to_ebitda"))
	interest_coverage = _safe(ratio_row.get("interest_coverage"))
	quality_score = _safe(ratio_row.get("data_quality_score"))
	evidence["net_debt_to_ebitda"] = net_debt_ebitda
	evidence["interest_coverage"] = interest_coverage
	evidence["data_quality_score"] = quality_score

	if net_debt_ebitda is not None:
		if net_debt_ebitda < 0.0:
			score += 15.0
			evidence["leverage_signal"] = "net cash"
		elif net_debt_ebitda < 1.0:
			score += 10.0
			evidence["leverage_signal"] = "low leverage"
		elif net_debt_ebitda < 2.0:
			score += 5.0
			evidence["leverage_signal"] = "modest leverage"
		elif net_debt_ebitda < 3.0:
			score -= 5.0
			evidence["leverage_signal"] = "moderate leverage"
		elif net_debt_ebitda < 5.0:
			score -= 12.0
			evidence["leverage_signal"] = "elevated leverage"
		else:
			score -= 20.0
			evidence["leverage_signal"] = "high leverage"
	else:
		evidence["leverage_signal"] = "missing"

	if interest_coverage is not None:
		if interest_coverage > 10.0:
			score += 10.0
			evidence["coverage_signal"] = "very strong"
		elif interest_coverage > 5.0:
			score += 6.0
			evidence["coverage_signal"] = "strong"
		elif interest_coverage > 2.0:
			score += 2.0
			evidence["coverage_signal"] = "adequate"
		elif interest_coverage > 1.0:
			score -= 5.0
			evidence["coverage_signal"] = "weak"
		else:
			score -= 15.0
			evidence["coverage_signal"] = "critical"
	else:
		evidence["coverage_signal"] = "missing"

	if quality_score is not None and quality_score < 60.0:
		score -= 5.0
		evidence["data_quality_signal"] = "limited"
	else:
		evidence["data_quality_signal"] = "ok_or_missing"

	return _clamp(score), evidence


def score_news_family(
	ratio_row: dict[str, Any] | None,
	filings: list[dict[str, Any]] | None = None,
) -> tuple[float, dict[str, Any]]:
	"""Score news / disclosure tone on a 0-100 scale."""
	filings = filings or []
	score = 50.0
	evidence: dict[str, Any] = {}
	if ratio_row is None:
		return score, {"signal": "missing ratio inputs"}

	sentiment = _safe(ratio_row.get("news_sentiment_7d"))
	volume = _safe(ratio_row.get("news_volume_7d"))
	evidence["news_sentiment_7d"] = sentiment
	evidence["news_volume_7d"] = volume

	if sentiment is not None:
		if sentiment > 0.20:
			score += 10.0
			evidence["sentiment_signal"] = "positive"
		elif sentiment > 0.05:
			score += 4.0
			evidence["sentiment_signal"] = "mildly positive"
		elif sentiment < -0.30:
			score -= 15.0
			evidence["sentiment_signal"] = "strongly negative"
		elif sentiment < -0.10:
			score -= 8.0
			evidence["sentiment_signal"] = "negative"
		else:
			evidence["sentiment_signal"] = "neutral"
	else:
		evidence["sentiment_signal"] = "missing"

	if volume is not None and sentiment is not None and sentiment < -0.10:
		if volume >= 20:
			score -= 8.0
			evidence["volume_signal"] = "high volume negative news"
		elif volume >= 10:
			score -= 4.0
			evidence["volume_signal"] = "moderate volume negative news"
		else:
			evidence["volume_signal"] = "contained"
	else:
		evidence["volume_signal"] = "neutral_or_missing"

	recent_filing_types = {row.get("filing_type") for row in filings if row.get("filing_type")}
	evidence["recent_filing_types"] = sorted(recent_filing_types)
	if "10-K" in recent_filing_types or "20-F" in recent_filing_types:
		score += 3.0
		evidence["filing_signal"] = "recent annual filing"
	elif filings:
		evidence["filing_signal"] = "recent filings present"
	else:
		score -= 3.0
		evidence["filing_signal"] = "no recent filings"

	return _clamp(score), evidence


def score_market_regime_family(ratio_row: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
	"""Score price trend / regime on a 0-100 scale."""
	score = 50.0
	evidence: dict[str, Any] = {}
	if ratio_row is None:
		return score, {"signal": "missing ratio inputs"}

	momentum_60d = _safe(ratio_row.get("momentum_60d"))
	momentum_250d = _safe(ratio_row.get("momentum_250d"))
	volatility_90d = _safe(ratio_row.get("volatility_90d"))
	evidence["momentum_60d"] = momentum_60d
	evidence["momentum_250d"] = momentum_250d
	evidence["volatility_90d"] = volatility_90d

	if momentum_60d is not None and momentum_250d is not None:
		if momentum_60d > 0.10 and momentum_250d > 0.10:
			score += 12.0
			evidence["momentum_signal"] = "strong positive trend"
		elif momentum_60d > 0.0 and momentum_250d > 0.0:
			score += 6.0
			evidence["momentum_signal"] = "positive trend"
		elif momentum_60d < -0.10 and momentum_250d < -0.10:
			score -= 12.0
			evidence["momentum_signal"] = "broad downtrend"
		elif momentum_60d < 0.0 and momentum_250d < 0.0:
			score -= 6.0
			evidence["momentum_signal"] = "negative trend"
		else:
			evidence["momentum_signal"] = "mixed"
	else:
		evidence["momentum_signal"] = "missing"

	if volatility_90d is not None:
		if volatility_90d > 0.50:
			score -= 10.0
			evidence["volatility_signal"] = "very high volatility"
		elif volatility_90d > 0.35:
			score -= 5.0
			evidence["volatility_signal"] = "elevated volatility"
		elif volatility_90d < 0.20:
			score += 3.0
			evidence["volatility_signal"] = "contained volatility"
		else:
			evidence["volatility_signal"] = "normal volatility"
	else:
		evidence["volatility_signal"] = "missing"

	return _clamp(score), evidence
