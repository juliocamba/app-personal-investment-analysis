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
) -> str:
	"""Build a short deterministic explanation string."""
	parts: list[str] = [
		f"Signal is {final_signal} with adjusted buy probability {p_buy_adjusted:.2f}"
	]

	mos = None
	if valuation_row is not None:
		mos = valuation_row.get("margin_of_safety_conservative")
	if mos is not None:
		parts.append(f"because conservative margin of safety is {mos:.0%}")
	else:
		parts.append("because valuation evidence is incomplete")

	parts.append(f"quality score is {quality_score:.1f}")
	parts.append(f"balance-sheet score is {balance_score:.1f}")

	if freshness_flag != "ok":
		parts.append(f"data freshness is {freshness_flag}")

	if red_flags:
		parts.append(f"red flags: {', '.join(red_flags[:3])}")
	elif p_sell >= 0.60:
		parts.append("sell pressure remains elevated")

	return "; ".join(parts) + "."
