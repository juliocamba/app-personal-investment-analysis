"""Phase 6 probabilistic signal engine.

Implements a deterministic, explainable, conservative rule-based signal model.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from investment_app.scoring.explanations import (
	build_signal_explanation,
	build_top_feature_contributors,
)
from investment_app.scoring.rule_based import (
	_clamp01,
	_safe,
	load_rule_score_weights,
	score_balance_sheet_family,
	score_market_regime_family,
	score_news_family,
	score_valuation_family,
	sigmoid,
)

MODEL_VERSION = "signal_rule_v2"

_FAIR_VALUE_MOS_EPSILON: float = 0.005
"""Absolute MoS within this band (±0.5%) is treated as near fair value.

Floating-point subtraction in the valuation model can produce values like
-1.5e-16 for stocks trading right at intrinsic value.  Any |mos| smaller
than this constant is clamped to 0.0 before signal pressure is accumulated
so that numerical noise does not add spurious bearish pressure.
"""


def _normalized_mos_for_signal(mos: float | None) -> float | None:
	"""Return *mos* clamped to zero when it falls inside the near-fair-value band.

	Values with ``|mos| <= _FAIR_VALUE_MOS_EPSILON`` are treated as 0.0 for
	signal-pressure purposes.  The raw stored margin_of_safety_conservative
	column is never modified; normalisation is applied only during computation.
	"""
	if mos is None:
		return None
	return 0.0 if abs(mos) <= _FAIR_VALUE_MOS_EPSILON else mos


def _days_between(newer: str | None, older: str | None) -> int | None:
	"""Return whole-day gap between ISO dates, or None when unavailable."""
	if not newer or not older:
		return None
	try:
		newer_date = date.fromisoformat(newer)
		older_date = date.fromisoformat(older)
	except ValueError:
		return None
	return (newer_date - older_date).days


def _extract_freshness_flag(
	*,
	signal_date: str,
	valuation_row: dict[str, Any] | None,
	qualitative_row: dict[str, Any] | None,
	ratio_row: dict[str, Any] | None,
	latest_price_row: dict[str, Any] | None,
) -> str:
	"""Return a compact freshness flag for the signal snapshot."""
	valuation_diag = ((valuation_row or {}).get("assumptions") or {}).get("diagnostics") or {}
	if valuation_diag.get("freshness_flag") == "missing_inputs":
		return "missing_inputs"
	if valuation_row is None or latest_price_row is None:
		return "missing_inputs"

	stale_thresholds = {
		"valuation": _days_between(signal_date, valuation_row.get("valuation_date")),
		"qualitative": _days_between(signal_date, qualitative_row.get("score_date") if qualitative_row else None),
		"ratios": _days_between(signal_date, ratio_row.get("factor_date") if ratio_row else None),
		"price": _days_between(signal_date, latest_price_row.get("price_date")),
	}
	if any(
		age is not None and (
			(name == "price" and age > 7)
			or (name != "price" and age > 30)
		)
		for name, age in stale_thresholds.items()
	):
		return "stale"
	if qualitative_row is None or ratio_row is None:
		return "limited"
	return "ok"


def _build_red_flags(
	*,
	valuation_row: dict[str, Any] | None,
	qualitative_row: dict[str, Any] | None,
	ratio_row: dict[str, Any] | None,
	freshness_flag: str,
) -> list[str]:
	"""Build deterministic red flags from existing evidence."""
	flags: list[str] = []

	if valuation_row is None:
		flags.append("missing_valuation")
	else:
		mos = _safe(valuation_row.get("margin_of_safety_conservative"))
		current_price = _safe(valuation_row.get("current_price"))
		iv_p75 = _safe(valuation_row.get("iv_p75"))
		if mos is not None and mos < -0.15:
			flags.append("negative_margin_of_safety")
		if current_price is not None and iv_p75 is not None and current_price > iv_p75:
			flags.append("overvalued_vs_iv_p75")
		diagnostics = ((valuation_row.get("assumptions") or {}).get("diagnostics") or {})
		for blocker in diagnostics.get("blockers", []):
			if blocker in {"negative_direct_fcf", "zero_direct_fcf"}:
				flags.append(blocker)

	if qualitative_row is None:
		flags.append("missing_qualitative_score")
	else:
		quality_score = _safe(qualitative_row.get("final_quality_score"), 50.0) or 50.0
		if quality_score <= 30.0:
			flags.append("quality_breakdown")
		elif quality_score < 40.0:
			flags.append("weak_quality")

	if ratio_row is not None:
		leverage = _safe(ratio_row.get("net_debt_to_ebitda"))
		coverage = _safe(ratio_row.get("interest_coverage"))
		sentiment = _safe(ratio_row.get("news_sentiment_7d"))
		if leverage is not None and leverage >= 5.0:
			flags.append("high_leverage")
		if coverage is not None and coverage <= 1.0:
			flags.append("critical_interest_coverage")
		if sentiment is not None and sentiment <= -0.30:
			flags.append("negative_news_spike")
	else:
		flags.append("missing_ratio_factors")

	if freshness_flag in {"stale", "missing_inputs"}:
		flags.append(f"freshness_{freshness_flag}")

	return sorted(set(flags))


def _quality_multiplier(quality_score: float, *, freshness_flag: str) -> float:
	"""Convert qualitative strength into a conservative confidence multiplier."""
	multiplier = 1.0 + max(-0.15, min(0.15, (quality_score - 50.0) / 200.0))
	if freshness_flag == "limited":
		multiplier *= 0.95
	elif freshness_flag in {"stale", "missing_inputs"}:
		multiplier *= 0.90
	return multiplier


def _risk_penalty(
	*,
	balance_score: float,
	news_score: float,
	red_flags: list[str],
	freshness_flag: str,
) -> float:
	"""Return a multiplicative risk penalty in [0, 0.35]."""
	penalty = 0.0
	if balance_score < 50.0:
		penalty += min(0.20, (50.0 - balance_score) / 100.0)
	if news_score < 40.0:
		penalty += 0.05
	if freshness_flag == "limited":
		penalty += 0.03
	elif freshness_flag == "stale":
		penalty += 0.05
	elif freshness_flag == "missing_inputs":
		penalty += 0.10
	if any(
		flag in red_flags
		for flag in ("high_leverage", "critical_interest_coverage", "quality_breakdown")
	):
		penalty += 0.10
	return min(0.35, penalty)


def _sell_probability(
	*,
	valuation_row: dict[str, Any] | None,
	quality_score: float,
	balance_score: float,
	news_score: float,
	market_score: float,
	red_flags: list[str],
	freshness_flag: str,
) -> float:
	"""Compute a conservative sell probability."""
	pressure = 35.0
	mos = _normalized_mos_for_signal(_safe((valuation_row or {}).get("margin_of_safety_conservative")))
	current_price = _safe((valuation_row or {}).get("current_price"))
	iv_p50 = _safe((valuation_row or {}).get("iv_p50"))
	iv_p75 = _safe((valuation_row or {}).get("iv_p75"))

	if mos is not None:
		if mos < -0.20:
			pressure += 18.0
		elif mos < -0.10:
			pressure += 10.0
		elif mos < 0.0:
			pressure += 5.0
	if current_price is not None and iv_p75 is not None and current_price > iv_p75:
		pressure += 15.0
	elif current_price is not None and iv_p50 is not None and current_price > iv_p50:
		pressure += 8.0

	if quality_score <= 30.0:
		pressure += 18.0
	elif quality_score < 40.0:
		pressure += 12.0
	elif quality_score < 50.0:
		pressure += 5.0

	if balance_score <= 30.0:
		pressure += 18.0
	elif balance_score < 40.0:
		pressure += 12.0
	elif balance_score < 50.0:
		pressure += 5.0

	if news_score < 35.0:
		pressure += 10.0
	if market_score < 35.0:
		pressure += 6.0
	if freshness_flag in {"stale", "missing_inputs"}:
		pressure += 5.0
	if any(
		flag in red_flags
		for flag in (
			"high_leverage",
			"critical_interest_coverage",
			"quality_breakdown",
			"negative_direct_fcf",
			"zero_direct_fcf",
		)
	):
		pressure += 20.0
	return _clamp01(sigmoid((pressure - 50.0) / 12.0))


# Flags that can confirm a strong_sell verdict (in addition to elevated p_sell).
_STRONG_SELL_CONFIRMING_FLAGS: frozenset[str] = frozenset({
	"high_leverage",
	"critical_interest_coverage",
	"quality_breakdown",
	"negative_margin_of_safety",
	"overvalued_vs_iv_p75",
})


def _classify_signal(
	*,
	p_buy_adjusted: float,
	p_sell: float,
	valuation_row: dict[str, Any] | None,
	quality_score: float,
	red_flags: list[str],
	freshness_flag: str,
	readiness_status: str = "analysis_ready",
) -> str:
	"""Map probabilities and red flags into a conservative final label.

	*readiness_status* — when ``"partial_analysis"``, buy and strong_buy are
	demoted to hold.  All other statuses are treated as ``"analysis_ready"``.

	Strong-sell requires BOTH ``p_sell >= 0.60`` AND at least one confirming
	bearish flag from ``_STRONG_SELL_CONFIRMING_FLAGS``; without confirmation
	the signal degrades to sell.
	"""
	mos = _safe((valuation_row or {}).get("margin_of_safety_conservative"))
	current_price = _safe((valuation_row or {}).get("current_price"))
	iv_p75 = _safe((valuation_row or {}).get("iv_p75"))
	has_insufficient_core_inputs = all(
		flag in red_flags
		for flag in ("missing_valuation", "missing_qualitative_score", "missing_ratio_factors")
	)
	has_hard_red_flag = any(
		flag in red_flags
		for flag in (
			"quality_breakdown",
			"high_leverage",
			"critical_interest_coverage",
			"negative_direct_fcf",
			"zero_direct_fcf",
		)
	)
	has_confirming_bearish = any(f in red_flags for f in _STRONG_SELL_CONFIRMING_FLAGS)

	if has_insufficient_core_inputs:
		return "insufficient_data"

	# Strong sell: elevated p_sell AND at least one confirming bearish flag.
	# Without BOTH conditions, any bearish scenario degrades to sell.
	if p_sell >= 0.60 and has_confirming_bearish:
		return "strong_sell"

	# Sell: hard red flag present, or elevated p_sell without strong_sell confirmation.
	if has_hard_red_flag or p_sell >= 0.60:
		return "sell"

	# Buy / strong buy — only for fully-ready analysis.
	candidate = "hold"
	if freshness_flag == "ok" and valuation_row is not None and mos is not None:
		if p_buy_adjusted >= 0.70 and mos >= 0.15 and not red_flags:
			candidate = "strong_buy"
		elif p_buy_adjusted >= 0.60 and mos >= 0.10 and "missing_qualitative_score" not in red_flags:
			candidate = "buy"

	# Partial analysis: demote high-conviction buy signals to hold.
	if readiness_status == "partial_analysis" and candidate in ("strong_buy", "buy"):
		return "hold"
	return candidate


def compute_signal_run(
	company_id: str,
	repo_module: Any,
	signal_date: str,
	*,
	weights: dict[str, float] | None = None,
	readiness_status: str = "analysis_ready",
) -> dict[str, Any] | None:
	"""Compute one deterministic probabilistic signal row for *signal_date*."""
	valuation_row = repo_module.get_latest_valuation_run(company_id, as_of_date=signal_date)
	qualitative_row = repo_module.get_latest_qualitative_score(company_id, as_of_date=signal_date)
	ratio_rows = repo_module.get_ratios_for_company(company_id, as_of_date=signal_date, limit=1)
	price_rows = repo_module.get_prices_for_company(company_id, as_of_date=signal_date, limit=1)
	filings = repo_module.get_filings_for_company(company_id, as_of_date=signal_date, limit=5)

	ratio_row = ratio_rows[0] if ratio_rows else None
	latest_price_row = price_rows[0] if price_rows else None

	if valuation_row is None and qualitative_row is None and ratio_row is None and latest_price_row is None:
		return None

	family_weights = load_rule_score_weights(weights)
	valuation_score, valuation_ev = score_valuation_family(valuation_row)
	quality_score = _safe((qualitative_row or {}).get("final_quality_score"), 45.0) or 45.0
	quality_ev = {
		"signal": "from qualitative score" if qualitative_row is not None else "missing qualitative score",
		"final_quality_score": quality_score,
	}
	balance_score, balance_ev = score_balance_sheet_family(ratio_row)
	news_score, news_ev = score_news_family(ratio_row, filings)
	market_score, market_ev = score_market_regime_family(ratio_row)

	freshness_flag = _extract_freshness_flag(
		signal_date=signal_date,
		valuation_row=valuation_row,
		qualitative_row=qualitative_row,
		ratio_row=ratio_row,
		latest_price_row=latest_price_row,
	)
	red_flags = _build_red_flags(
		valuation_row=valuation_row,
		qualitative_row=qualitative_row,
		ratio_row=ratio_row,
		freshness_flag=freshness_flag,
	)

	family_scores = {
		"valuation": {
			"score": valuation_score,
			"weight": family_weights["valuation"],
			"evidence": valuation_ev,
		},
		"quality": {
			"score": quality_score,
			"weight": family_weights["quality"],
			"evidence": quality_ev,
		},
		"balance_sheet": {
			"score": balance_score,
			"weight": family_weights["balance_sheet"],
			"evidence": balance_ev,
		},
		"news": {
			"score": news_score,
			"weight": family_weights["news"],
			"evidence": news_ev,
		},
		"market_regime": {
			"score": market_score,
			"weight": family_weights["market_regime"],
			"evidence": market_ev,
		},
	}
	rule_score = sum(payload["score"] * payload["weight"] for payload in family_scores.values())
	p_buy = _clamp01(sigmoid((rule_score - 50.0) / 12.0))

	quality_multiplier = _quality_multiplier(quality_score, freshness_flag=freshness_flag)
	risk_penalty = _risk_penalty(
		balance_score=balance_score,
		news_score=news_score,
		red_flags=red_flags,
		freshness_flag=freshness_flag,
	)
	uncertainty_width = _safe((valuation_row or {}).get("uncertainty_width"), 0.0) or 0.0
	uncertainty_penalty = min(0.35, uncertainty_width / 0.80) if uncertainty_width > 0.0 else 0.0
	p_buy_adjusted = _clamp01(
		p_buy * quality_multiplier * (1.0 - risk_penalty) * (1.0 - uncertainty_penalty)
	)

	p_sell = _sell_probability(
		valuation_row=valuation_row,
		quality_score=quality_score,
		balance_score=balance_score,
		news_score=news_score,
		market_score=market_score,
		red_flags=red_flags,
		freshness_flag=freshness_flag,
	)
	final_signal = _classify_signal(
		p_buy_adjusted=p_buy_adjusted,
		p_sell=p_sell,
		valuation_row=valuation_row,
		quality_score=quality_score,
		red_flags=red_flags,
		freshness_flag=freshness_flag,
		readiness_status=readiness_status,
	)

	top_feature_contributors = build_top_feature_contributors(
		family_scores=family_scores,
		quality_multiplier=quality_multiplier,
		risk_penalty=risk_penalty,
		uncertainty_penalty=uncertainty_penalty,
	)
	explanation = build_signal_explanation(
		final_signal=final_signal,
		valuation_row=valuation_row,
		quality_score=quality_score,
		balance_score=balance_score,
		freshness_flag=freshness_flag,
		red_flags=red_flags,
		p_buy_adjusted=p_buy_adjusted,
		p_sell=p_sell,
		uncertainty_width=uncertainty_width or None,
	)

	return {
		"company_id": company_id,
		"signal_date": signal_date,
		"model_version": MODEL_VERSION,
		"valuation_run_id": (valuation_row or {}).get("id"),
		"qualitative_score_id": (qualitative_row or {}).get("id"),
		"p_buy": round(p_buy, 4),
		"p_buy_adjusted": round(p_buy_adjusted, 4),
		"p_sell": round(p_sell, 4),
		"final_signal": final_signal,
		"uncertainty_penalty": round(uncertainty_penalty, 4),
		"red_flags": red_flags,
		"top_feature_contributors": top_feature_contributors,
		"explanation": explanation,
		"freshness_flag": freshness_flag,
	}
