"""Deterministic explanation helpers for Phase 6 signals."""
from __future__ import annotations

from typing import Any


def build_top_feature_contributors(
	*,
	family_scores: dict[str, dict[str, Any]],
	quality_multiplier: float,
	risk_penalty: float,
	uncertainty_penalty: float,
) -> list[dict[str, Any]]:
	"""Return an auditable JSON-serialisable contributor payload."""
	contributors: list[dict[str, Any]] = []
	for name, payload in family_scores.items():
		score = float(payload["score"])
		weight = float(payload["weight"])
		weighted_impact = round(weight * (score - 50.0), 2)
		contributors.append(
			{
				"name": name,
				"kind": "family",
				"score": round(score, 2),
				"weight": round(weight, 4),
				"weighted_impact": weighted_impact,
				"direction": (
					"positive"
					if weighted_impact > 0
					else "negative" if weighted_impact < 0 else "neutral"
				),
				"evidence": payload["evidence"],
			}
		)

	contributors.append(
		{
			"name": "quality_confidence_multiplier",
			"kind": "adjustment",
			"value": round(quality_multiplier, 4),
			"impact": round((quality_multiplier - 1.0) * 100.0, 2),
			"direction": "positive" if quality_multiplier >= 1.0 else "negative",
		}
	)
	contributors.append(
		{
			"name": "risk_penalty",
			"kind": "adjustment",
			"value": round(risk_penalty, 4),
			"impact": round(-risk_penalty * 100.0, 2),
			"direction": "negative" if risk_penalty > 0 else "neutral",
		}
	)
	contributors.append(
		{
			"name": "uncertainty_penalty",
			"kind": "adjustment",
			"value": round(uncertainty_penalty, 4),
			"impact": round(-uncertainty_penalty * 100.0, 2),
			"direction": "negative" if uncertainty_penalty > 0 else "neutral",
		}
	)

	contributors.sort(
		key=lambda item: abs(float(item.get("weighted_impact", item.get("impact", 0.0)))),
		reverse=True,
	)
	return contributors


# ---------------------------------------------------------------------------
# Red flag plain-English labels
# ---------------------------------------------------------------------------

_RED_FLAG_LABELS: dict[str, str] = {
	"negative_margin_of_safety":  "price above intrinsic value",
	"overvalued_vs_iv_p75":       "price exceeds optimistic IV estimate",
	"quality_breakdown":          "quality score very low",
	"weak_quality":               "weak quality indicators",
	"high_leverage":              "high financial leverage",
	"critical_interest_coverage": "insufficient interest coverage",
	"negative_direct_fcf":        "negative free cash flow",
	"zero_direct_fcf":            "zero free cash flow",
	"negative_news_spike":        "recent negative news spike",
	"missing_valuation":          "valuation unavailable",
	"missing_qualitative_score":  "qualitative data unavailable",
	"missing_ratio_factors":      "ratio factors unavailable",
	"freshness_stale":            "stale input data",
	"freshness_missing_inputs":   "missing core inputs",
}

# Priority order for selecting the top bearish driver(s) in sell explanations.
_BEARISH_PRIORITY: list[str] = [
	"negative_margin_of_safety",
	"overvalued_vs_iv_p75",
	"quality_breakdown",
	"high_leverage",
	"critical_interest_coverage",
	"negative_direct_fcf",
	"zero_direct_fcf",
	"weak_quality",
	"negative_news_spike",
]


def _label(flag: str) -> str:
	"""Return a plain-English label for a red flag code."""
	return _RED_FLAG_LABELS.get(flag, flag.replace("_", " "))


def _top_bearish(red_flags: list[str], limit: int = 2) -> list[str]:
	"""Return up to *limit* highest-priority bearish flags."""
	prioritised = [f for f in _BEARISH_PRIORITY if f in red_flags]
	return prioritised[:limit] if prioritised else list(red_flags[:limit])


def build_signal_explanation(
	*,
	final_signal: str,
	valuation_row: dict[str, Any] | None,
	quality_score: float,
	balance_score: float,
	freshness_flag: str,
	red_flags: list[str],
	p_buy_adjusted: float,
	p_sell: float,
	uncertainty_width: float | None = None,
) -> str:
	"""Build a short, structured, plain-English explanation string.

	The function is backward-compatible: *uncertainty_width* defaults to None
	and existing callers that omit it continue to work without modification.
	"""
	sig = final_signal.upper()
	mos: float | None = None
	if valuation_row is not None:
		mos = valuation_row.get("margin_of_safety_conservative")

	# Optional uncertainty suffix appended to every label when width is wide.
	uncertainty_note = (
		" Wide valuation range — estimates carry high uncertainty."
		if uncertainty_width is not None and uncertainty_width > 0.50
		else ""
	)

	# ── Insufficient data ────────────────────────────────────────────────────
	if sig == "INSUFFICIENT_DATA":
		if "missing_valuation" in red_flags:
			return (
				"Insufficient data — valuation unavailable; cannot assess margin of safety."
				+ uncertainty_note
			)
		return (
			"Insufficient data — core inputs missing; signal cannot be determined."
			+ uncertainty_note
		)

	# ── Sell / Strong sell ───────────────────────────────────────────────────
	if sig in ("STRONG_SELL", "SELL"):
		label = "Strong sell" if sig == "STRONG_SELL" else "Sell"
		top = _top_bearish(red_flags)
		if top:
			reasons = " and ".join(_label(f) for f in top)
			return f"{label} — {reasons}." + uncertainty_note
		if mos is not None and mos < 0.0:
			return f"{label} — price above intrinsic value ({mos:.0%} MoS)." + uncertainty_note
		return f"{label} — elevated sell pressure (p_sell={p_sell:.2f})." + uncertainty_note

	# ── Buy / Strong buy ─────────────────────────────────────────────────────
	if sig in ("STRONG_BUY", "BUY"):
		label = "Strong buy" if sig == "STRONG_BUY" else "Buy"
		if mos is not None:
			parts: list[str] = [f"{label} — conservative margin of safety {mos:.0%}"]
			if quality_score >= 60.0:
				parts.append("supported by strong quality score")
			if not red_flags:
				parts.append("no major red flags")
			return "; ".join(parts) + "." + uncertainty_note
		return (
			f"{label} — buy probability {p_buy_adjusted:.2f} with no disqualifying red flags."
			+ uncertainty_note
		)

	# ── Hold ─────────────────────────────────────────────────────────────────
	if p_buy_adjusted >= 0.50 and p_sell >= 0.50:
		return "Hold — mixed signals; buy and sell pressure both elevated." + uncertainty_note
	if p_buy_adjusted >= 0.55:
		return (
			f"Hold — buy probability ({p_buy_adjusted:.2f}) just below threshold."
			+ uncertainty_note
		)
	if freshness_flag == "missing_inputs":
		return "Hold — low confidence due to missing core inputs." + uncertainty_note
	if freshness_flag == "stale":
		return "Hold — low confidence due to stale input data." + uncertainty_note
	if freshness_flag == "limited":
		return "Hold — limited evidence; no high-conviction signal." + uncertainty_note
	if p_buy_adjusted >= 0.40:
		return (
			f"Hold — insufficient directional conviction (p_buy_adj={p_buy_adjusted:.2f})."
			+ uncertainty_note
		)
	return "Hold — no strong buy or sell case established." + uncertainty_note
