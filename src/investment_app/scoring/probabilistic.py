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

_RECOMMENDATION_LIKE_PHRASES: tuple[str, ...] = (
	"you should buy",
	"you should sell",
	"safe to hold",
	"good opportunity",
	"guaranteed",
)

MODEL_VERSION = "signal_rule_v3"

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


_UNCERTAINTY_BANDS: dict[str, float] = {
	"low_or_missing": 0.05,
	"moderate": 0.10,
	"high": 0.15,
	"extreme": 0.25,
}

_SEVERE_MIDPOINT_PREMIUM_THRESHOLDS: dict[str, float | None] = {
	"low_or_missing": 0.30,
	"moderate": 0.40,
	"high": 0.55,
	"extreme": None,
}


def _uncertainty_category_for_signal(uncertainty_width: float | None) -> str:
	"""Return the signal-layer uncertainty bucket from valuation range width."""
	if uncertainty_width is None:
		return "low_or_missing"
	if uncertainty_width <= 0.35:
		return "low_or_missing"
	if uncertainty_width <= 0.75:
		return "moderate"
	if uncertainty_width <= 1.25:
		return "high"
	return "extreme"


def _uncertainty_band_for_signal(valuation_row: dict[str, Any] | None) -> float:
	"""Return the neutral fair-value band used by signal calibration."""
	uncertainty_width = _safe((valuation_row or {}).get("uncertainty_width"))
	return _UNCERTAINTY_BANDS[_uncertainty_category_for_signal(uncertainty_width)]


def _midpoint_premium(valuation_row: dict[str, Any] | None) -> float | None:
	"""Return price premium/discount versus iv_p50, or None when unavailable."""
	current_price = _safe((valuation_row or {}).get("current_price"))
	iv_p50 = _safe((valuation_row or {}).get("iv_p50"))
	if current_price is None or iv_p50 is None or iv_p50 <= 0.0:
		return None
	return (current_price - iv_p50) / iv_p50


def _valuation_position_bucket(valuation_row: dict[str, Any] | None) -> str:
	"""Classify price position against midpoint fair value with uncertainty bands."""
	premium = _midpoint_premium(valuation_row)
	if premium is None:
		return "unknown"

	uncertainty_width = _safe((valuation_row or {}).get("uncertainty_width"))
	category = _uncertainty_category_for_signal(uncertainty_width)
	band = _uncertainty_band_for_signal(valuation_row)
	severe_threshold = _SEVERE_MIDPOINT_PREMIUM_THRESHOLDS[category]

	if premium < -band:
		return "below_fair_value"
	if abs(premium) <= band:
		return "near_fair_value"
	if severe_threshold is not None and premium >= severe_threshold:
		return "severely_overvalued"
	return "modestly_overvalued"


def _has_valuation_only_strong_sell_confirmation(
	valuation_row: dict[str, Any] | None,
) -> bool:
	"""Return True only for severe midpoint overvaluation outside extreme uncertainty."""
	uncertainty_width = _safe((valuation_row or {}).get("uncertainty_width"))
	if _uncertainty_category_for_signal(uncertainty_width) == "extreme":
		return False
	return _valuation_position_bucket(valuation_row) == "severely_overvalued"


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

	valuation_diagnostics = ((valuation_row or {}).get("assumptions") or {}).get("diagnostics") or {}
	valuation_sanity_status = str(
		valuation_diagnostics.get("valuation_sanity_status") or "usable"
	).strip().lower()
	valuation_sanity_blocks_influence = bool(
		valuation_diagnostics.get("valuation_signal_influence_blocked")
	) or valuation_sanity_status in {"unreliable", "model_failure"}

	if valuation_row is None:
		flags.append("missing_valuation")
	else:
		mos = _safe(valuation_row.get("margin_of_safety_conservative"))
		current_price = _safe(valuation_row.get("current_price"))
		iv_p75 = _safe(valuation_row.get("iv_p75"))
		if valuation_sanity_blocks_influence:
			flags.append("valuation_unreliable")
		else:
			if mos is not None and mos < -0.15:
				flags.append("negative_margin_of_safety")
			if current_price is not None and iv_p75 is not None and current_price > iv_p75:
				flags.append("overvalued_vs_iv_p75")
		for blocker in valuation_diagnostics.get("blockers", []):
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
	valuation_diagnostics = ((valuation_row or {}).get("assumptions") or {}).get("diagnostics") or {}
	valuation_sanity_status = str(
		valuation_diagnostics.get("valuation_sanity_status") or "usable"
	).strip().lower()
	valuation_signal_influence_blocked = bool(
		valuation_diagnostics.get("valuation_signal_influence_blocked")
	) or valuation_sanity_status in {"unreliable", "model_failure"}

	position_bucket = (
		"unknown" if valuation_signal_influence_blocked else _valuation_position_bucket(valuation_row)
	)

	if position_bucket == "severely_overvalued":
		pressure += 22.0
	elif position_bucket == "modestly_overvalued":
		pressure += 12.0
	elif (
		position_bucket == "unknown"
		and mos is not None
		and not valuation_signal_influence_blocked
	):
		# Fallback only when midpoint fair value is unavailable. This keeps the
		# conservative MoS useful without stacking it on top of midpoint evidence.
		if mos < -0.20:
			pressure += 12.0
		elif mos < -0.10:
			pressure += 7.0
		elif mos < 0.0:
			pressure += 3.0

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


# Independent hard-risk flags that can confirm a strong_sell verdict.
_STRONG_SELL_CONFIRMING_FLAGS: frozenset[str] = frozenset({
	"high_leverage",
	"critical_interest_coverage",
	"quality_breakdown",
	"negative_direct_fcf",
	"zero_direct_fcf",
})


def _valuation_diagnostics(valuation_row: dict[str, Any] | None) -> dict[str, Any]:
	return ((valuation_row or {}).get("assumptions") or {}).get("diagnostics") or {}


def _valuation_sanity_status(valuation_row: dict[str, Any] | None) -> str:
	return str(
		_valuation_diagnostics(valuation_row).get("valuation_sanity_status") or "usable"
	).strip().lower()


def _valuation_used_in_signal(valuation_row: dict[str, Any] | None) -> bool:
	if valuation_row is None:
		return False
	diagnostics = _valuation_diagnostics(valuation_row)
	if bool(diagnostics.get("valuation_signal_influence_blocked")):
		return False
	return _valuation_sanity_status(valuation_row) not in {"unreliable", "model_failure"}


def _hard_risk_flags(red_flags: list[str]) -> list[str]:
	return [flag for flag in red_flags if flag in _STRONG_SELL_CONFIRMING_FLAGS]


def _confidence_limiter_codes(
	*,
	readiness_status: str,
	freshness_flag: str,
	valuation_row: dict[str, Any] | None,
	red_flags: list[str],
) -> list[str]:
	limiters: list[str] = []
	if readiness_status == "partial_analysis":
		limiters.append("partial_analysis")
	if freshness_flag in {"limited", "stale", "missing_inputs"}:
		limiters.append(f"freshness_{freshness_flag}")
	valuation_sanity_status = _valuation_sanity_status(valuation_row)
	if valuation_sanity_status == "high_uncertainty":
		limiters.append("valuation_high_uncertainty")
	elif valuation_sanity_status in {"unreliable", "model_failure"}:
		limiters.append("valuation_unreliable")
	if valuation_row is None:
		limiters.append("valuation_missing")
	elif not _valuation_used_in_signal(valuation_row):
		limiters.append("valuation_not_used_in_signal")
	if "missing_qualitative_score" in red_flags:
		limiters.append("missing_qualitative_score")
	if "missing_ratio_factors" in red_flags:
		limiters.append("missing_ratio_factors")
	return list(dict.fromkeys(limiters))


def _strong_sell_basis(
	*,
	final_signal: str,
	valuation_row: dict[str, Any] | None,
	red_flags: list[str],
) -> str | None:
	if final_signal != "strong_sell":
		return None
	has_risk = bool(_hard_risk_flags(red_flags))
	has_valuation = _valuation_used_in_signal(valuation_row) and _has_valuation_only_strong_sell_confirmation(
		valuation_row
	)
	if has_risk and has_valuation:
		return "combined"
	if has_risk:
		return "risk"
	if has_valuation:
		return "valuation"
	return None


def _hold_reason(
	*,
	valuation_row: dict[str, Any] | None,
	red_flags: list[str],
	freshness_flag: str,
	readiness_status: str,
	p_buy_adjusted: float,
	p_sell: float,
) -> str:
	if freshness_flag in {"limited", "stale", "missing_inputs"} or readiness_status == "partial_analysis":
		return "data_constrained_hold"
	if _valuation_sanity_status(valuation_row) in {"unreliable", "model_failure"}:
		return "valuation_unreliable_hold"
	if _hard_risk_flags(red_flags) and _valuation_used_in_signal(valuation_row):
		position_bucket = _valuation_position_bucket(valuation_row)
		if position_bucket == "below_fair_value":
			return "risk_offset_hold"
	if _valuation_used_in_signal(valuation_row):
		position_bucket = _valuation_position_bucket(valuation_row)
		uncertainty_width = _safe((valuation_row or {}).get("uncertainty_width"))
		if position_bucket in {"modestly_overvalued", "below_fair_value"} and uncertainty_width is not None and uncertainty_width > 0.50:
			return "uncertainty_constrained_hold"
		if position_bucket == "near_fair_value":
			return "near_fair_value_hold"
	if p_buy_adjusted >= 0.50 and p_sell >= 0.50:
		return "neutral_mixed_hold"
	return "neutral_mixed_hold"


def _dominant_signal_driver(
	*,
	final_signal: str,
	valuation_row: dict[str, Any] | None,
	red_flags: list[str],
	freshness_flag: str,
	readiness_status: str,
	p_buy_adjusted: float,
	p_sell: float,
	hold_reason: str | None,
) -> str:
	if final_signal == "insufficient_data":
		return "data_unavailable"
	if readiness_status != "analysis_ready":
		if readiness_status == "partial_analysis":
			return "data_constrained"
		return "data_unavailable"
	if hold_reason == "data_constrained_hold":
		return "data_constrained"
	if hold_reason == "valuation_unreliable_hold":
		return "valuation_unreliable"
	if hold_reason == "uncertainty_constrained_hold":
		return "uncertainty_constrained"
	if hold_reason == "risk_offset_hold":
		return "risk_override"
	if final_signal in {"sell", "strong_sell"}:
		if _hard_risk_flags(red_flags):
			return "risk_override"
		if _valuation_used_in_signal(valuation_row):
			return "valuation_downside"
		if _valuation_sanity_status(valuation_row) in {"unreliable", "model_failure"}:
			return "valuation_unreliable"
		return "neutral_mixed"
	if final_signal in {"buy", "strong_buy"}:
		if _valuation_sanity_status(valuation_row) in {"unreliable", "model_failure"}:
			return "valuation_unreliable"
		if _valuation_used_in_signal(valuation_row):
			return "valuation_upside"
		return "quality_support"
	return "neutral_mixed"


def _reasoning_metadata(
	*,
	final_signal: str,
	valuation_row: dict[str, Any] | None,
	red_flags: list[str],
	freshness_flag: str,
	readiness_status: str,
	p_buy_adjusted: float,
	p_sell: float,
	explanation: str | None = None,
) -> dict[str, Any]:
	hold_reason = (
		_hold_reason(
			valuation_row=valuation_row,
			red_flags=red_flags,
			freshness_flag=freshness_flag,
			readiness_status=readiness_status,
			p_buy_adjusted=p_buy_adjusted,
			p_sell=p_sell,
		)
		if final_signal == "hold"
		else None
	)
	valuation_used_in_signal = _valuation_used_in_signal(valuation_row)
	risk_override_applied = bool(_hard_risk_flags(red_flags)) and final_signal in {"hold", "sell", "strong_sell"}
	confidence_limiter_codes = _confidence_limiter_codes(
		readiness_status=readiness_status,
		freshness_flag=freshness_flag,
		valuation_row=valuation_row,
		red_flags=red_flags,
	)
	strong_sell_basis = _strong_sell_basis(
		final_signal=final_signal,
		valuation_row=valuation_row,
		red_flags=red_flags,
	)
	buy_conviction_limited = final_signal in {"buy", "strong_buy"} and bool(confidence_limiter_codes)
	dominant_signal_driver = _dominant_signal_driver(
		final_signal=final_signal,
		valuation_row=valuation_row,
		red_flags=red_flags,
		freshness_flag=freshness_flag,
		readiness_status=readiness_status,
		p_buy_adjusted=p_buy_adjusted,
		p_sell=p_sell,
		hold_reason=hold_reason,
	)
	recommendation_language_warning = None
	if explanation:
		lowered = explanation.lower()
		if any(phrase in lowered for phrase in _RECOMMENDATION_LIKE_PHRASES):
			recommendation_language_warning = "recommendation_like_language"
	explanation_quality_warning = None
	if final_signal in {"buy", "strong_buy"} and dominant_signal_driver == "valuation_unreliable":
		explanation_quality_warning = "buy_with_unreliable_valuation"
	elif final_signal == "strong_sell" and strong_sell_basis is None:
		explanation_quality_warning = "missing_strong_sell_basis"
	return {
		"dominant_signal_driver": dominant_signal_driver,
		"hold_reason": hold_reason,
		"valuation_used_in_signal": valuation_used_in_signal,
		"risk_override_applied": risk_override_applied,
		"confidence_limiter_codes": confidence_limiter_codes,
		"strong_sell_basis": strong_sell_basis,
		"buy_conviction_limited": buy_conviction_limited,
		"explanation_quality_warning": explanation_quality_warning,
		"recommendation_language_warning": recommendation_language_warning,
		"probability_interpretation_note": "Internal rule-based model scores; not calibrated probabilities or investment recommendations.",
	}


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

	Strong-sell requires elevated sell pressure plus either severe midpoint
	overvaluation or an independent hard-risk flag. Valuation-only warnings such
	as negative MoS or price above iv_p75 do not confirm strong_sell by
	themselves.
	"""
	mos = _safe((valuation_row or {}).get("margin_of_safety_conservative"))
	has_insufficient_core_inputs = all(
		flag in red_flags
		for flag in ("missing_valuation", "missing_qualitative_score", "missing_ratio_factors")
	)
	has_hard_red_flag = any(flag in red_flags for flag in _STRONG_SELL_CONFIRMING_FLAGS)
	has_confirming_bearish = any(f in red_flags for f in _STRONG_SELL_CONFIRMING_FLAGS)
	valuation_diagnostics = ((valuation_row or {}).get("assumptions") or {}).get("diagnostics") or {}
	valuation_sanity_status = str(
		valuation_diagnostics.get("valuation_sanity_status") or "usable"
	).strip().lower()
	valuation_signal_influence_blocked = bool(
		valuation_diagnostics.get("valuation_signal_influence_blocked")
	) or valuation_sanity_status in {"unreliable", "model_failure"}
	has_severe_valuation_confirmation = _has_valuation_only_strong_sell_confirmation(
		valuation_row
	) if not valuation_signal_influence_blocked else False

	if has_insufficient_core_inputs:
		return "insufficient_data"

	# Strong sell: elevated p_sell plus independent hard risk, or severe
	# midpoint overvaluation outside extreme uncertainty.
	if p_sell >= 0.60 and (has_confirming_bearish or has_severe_valuation_confirmation):
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
	reasoning_metadata = _reasoning_metadata(
		final_signal=final_signal,
		valuation_row=valuation_row,
		red_flags=red_flags,
		freshness_flag=freshness_flag,
		readiness_status=readiness_status,
		p_buy_adjusted=p_buy_adjusted,
		p_sell=p_sell,
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
		valuation_sanity_status=str(
			((((valuation_row or {}).get("assumptions") or {}).get("diagnostics") or {}).get(
				"valuation_sanity_status"
			) or "usable")
		),
		reasoning_metadata=reasoning_metadata,
	)
	reasoning_metadata = {
		**reasoning_metadata,
		"recommendation_language_warning": (
			"recommendation_like_language"
			if any(phrase in explanation.lower() for phrase in _RECOMMENDATION_LIKE_PHRASES)
			else reasoning_metadata.get("recommendation_language_warning")
		),
	}
	top_feature_contributors = build_top_feature_contributors(
		family_scores=family_scores,
		quality_multiplier=quality_multiplier,
		risk_penalty=risk_penalty,
		uncertainty_penalty=uncertainty_penalty,
		reasoning_metadata=reasoning_metadata,
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
