"""Bear/base/bull scenario orchestration — Phase 4.

``compute_valuation_run`` is the top-level public API.  It:

1. Reads financials from the provided repo module (point-in-time safe).
2. Runs three DCF scenarios (bear/base/bull) and a multiples estimate.
3. Optionally runs DDM when applicable.
4. Applies sector-specific logic (financial-sector P/B fallback).
5. Blends scenario outputs into a probability-weighted distribution.
6. Returns a ``valuation_runs``-shaped dict ready for persistence.

Scenario parameters come from ``configs/valuation_defaults.yml`` (loaded via
:func:`~investment_app.config.loader.load_valuation_defaults`).  Callers may
override any parameter via the ``overrides`` dict.

All numbers are in the company's reporting currency.
"""
from __future__ import annotations

import math
from typing import Any

from investment_app.valuation.dcf import extract_base_fcf, run_dcf_scenario
from investment_app.valuation.dividend_discount import compute_ddm_value, is_ddm_applicable
from investment_app.valuation.financials import (
    compute_financial_sector_value,
    is_financial_sector,
)
from investment_app.valuation.multiples import compute_multiples_value

MODEL_VERSION = "valuation_v1"

# Default scenario adjustments relative to the base assumptions.
_BEAR_GROWTH_HAIRCUT = 0.50   # bear growth = base × 0.50
_BULL_GROWTH_PREMIUM = 1.50   # bull growth = base × 1.50
_BEAR_WACC_SPREAD = 0.015     # bear WACC = base + 150 bps
_BULL_WACC_SPREAD = -0.010    # bull WACC = base − 100 bps
_BEAR_MARGIN_HAIRCUT = 0.90   # bear EBIT margin = base × 0.90 (conservative)
_DEFAULT_METHOD_WEIGHTS = {
    "dcf": 0.50,
    "multiples": 0.30,
    "ddm": 0.20,
}

_SANITY_USABLE = "usable"
_SANITY_HIGH_UNCERTAINTY = "high_uncertainty"
_SANITY_UNRELIABLE = "unreliable"
_SANITY_MODEL_FAILURE = "model_failure"


def _is_finite_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator <= 0.0:
        return None
    return numerator / denominator


def _classify_method_coverage(
    *,
    has_dcf_component: bool,
    has_multiples_component: bool,
    has_ddm_component: bool,
) -> str:
    count = int(has_dcf_component) + int(has_multiples_component) + int(has_ddm_component)
    if count == 0:
        return "no_usable_method"
    if count >= 2:
        return "multi_method"
    if has_dcf_component:
        return "dcf_only"
    if has_multiples_component:
        return "multiples_only"
    return "ddm_only"


def _max_terminal_value_share(dcf_output: dict[str, Any] | None) -> float | None:
    if not isinstance(dcf_output, dict):
        return None
    scenarios = dcf_output.get("scenarios")
    if not isinstance(scenarios, dict):
        return None

    shares: list[float] = []
    for payload in scenarios.values():
        if not isinstance(payload, dict):
            continue
        pv_terminal = _get(payload, "pv_terminal_value")
        enterprise_value = _get(payload, "enterprise_value")
        share = _safe_ratio(pv_terminal, enterprise_value)
        if share is not None:
            shares.append(share)
    return max(shares) if shares else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get(row: dict[str, Any], key: str) -> float | None:
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _load_defaults() -> dict[str, Any]:
    """Return valuation_defaults.yml as a dict; fall back to hard-coded defaults."""
    try:
        from investment_app.config.loader import load_valuation_defaults
        raw = load_valuation_defaults()
        return raw.get("defaults", {})
    except Exception:  # noqa: BLE001
        return {}


def _resolve(defaults: dict[str, Any], overrides: dict[str, Any], key: str, fallback: Any) -> Any:
    return overrides.get(key, defaults.get(key, fallback))


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Normalize positive weights to sum to 1.0."""
    positive = {key: value for key, value in weights.items() if value > 0.0}
    total = sum(positive.values())
    if total <= 0.0:
        return {}
    return {key: value / total for key, value in positive.items()}


def _classify_uncertainty(width: float | None) -> str | None:
    """Classify uncertainty_width into a descriptive category.

    Thresholds (diagnostic only — no effect on valuation math or signal):
    - low:      width <= 0.35
    - moderate: 0.35 < width <= 0.75
    - high:     0.75 < width <= 1.25
    - extreme:  width > 1.25
    """
    if width is None:
        return None
    if width <= 0.35:
        return "low"
    if width <= 0.75:
        return "moderate"
    if width <= 1.25:
        return "high"
    return "extreme"


# ---------------------------------------------------------------------------
# Net debt helper
# ---------------------------------------------------------------------------


def _compute_net_debt(statement: dict[str, Any] | None) -> float | None:
    if statement is None:
        return None
    cash = _get(statement, "cash_and_equivalents")
    total_debt = _get(statement, "total_debt")
    short_term = _get(statement, "short_term_debt")
    long_term = _get(statement, "long_term_debt")
    # Prefer explicit total_debt; fall back to short + long term.
    if total_debt is not None:
        debt = total_debt
    elif short_term is not None or long_term is not None:
        debt = (short_term or 0.0) + (long_term or 0.0)
    else:
        return None
    return debt - (cash or 0.0)


def _ratio_statement_period_end(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("statement_period_end_date")
    return str(value) if value else None


def _filter_ratio_rows_for_statement_vintage(
    ratio_rows: list[dict[str, Any]],
    current_stmt: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep ratio rows aligned to the latest statement vintage when known.

    Older factor snapshots are preserved in ``ratios_factors`` for auditability,
    but valuation should not silently combine a fresh annual statement with
    ratio rows computed from an older statement vintage.
    """
    latest_period_end = str(current_stmt.get("period_end_date") or "") if current_stmt else ""
    diagnostics: dict[str, Any] = {
        "latest_statement_period_end_date": latest_period_end or None,
        "ratio_rows_available": len(ratio_rows),
        "ratio_rows_used": len(ratio_rows),
        "ratio_rows_excluded": 0,
        "status": "ok",
        "reason_codes": [],
    }
    if not ratio_rows or not latest_period_end:
        return ratio_rows, diagnostics

    matching: list[dict[str, Any]] = []
    mismatched = 0
    missing_vintage = 0
    for row in ratio_rows:
        row_period_end = _ratio_statement_period_end(row)
        if row_period_end is None:
            missing_vintage += 1
        elif row_period_end == latest_period_end:
            matching.append(row)
        else:
            mismatched += 1

    reason_codes: list[str] = []
    if mismatched:
        reason_codes.append("ratio_history_statement_vintage_mismatch")
    if missing_vintage:
        reason_codes.append("ratio_history_missing_statement_vintage")

    if matching:
        excluded = len(ratio_rows) - len(matching)
        diagnostics.update(
            {
                "ratio_rows_used": len(matching),
                "ratio_rows_excluded": excluded,
                "status": "filtered" if excluded else "ok",
                "reason_codes": reason_codes,
            }
        )
        if excluded:
            reason_codes.append("stale_ratio_history")
            reason_codes.append("ratio_history_filtered_for_statement_vintage")
        return matching, diagnostics

    if mismatched:
        reason_codes.append("stale_ratio_history")
        diagnostics.update(
            {
                "ratio_rows_used": 0,
                "ratio_rows_excluded": len(ratio_rows),
                "status": "blocked",
                "reason_codes": reason_codes,
            }
        )
        return [], diagnostics

    diagnostics.update(
        {
            "status": "unknown",
            "reason_codes": reason_codes,
        }
    )
    return ratio_rows, diagnostics


def _weighted_percentiles(
    distribution: list[dict[str, Any]],
) -> dict[str, float | None]:
    """Return weighted p10/p25/p50/p75/p90 from a value/weight distribution.

    The implementation is intentionally transparent: for each percentile, pick
    the smallest value whose cumulative normalized weight meets or exceeds the
    target percentile threshold.
    """
    out: dict[str, float | None] = {
        "iv_p10": None,
        "iv_p25": None,
        "iv_p50": None,
        "iv_p75": None,
        "iv_p90": None,
    }
    if not distribution:
        return out

    ordered = sorted(distribution, key=lambda item: item["value"])
    total_weight = sum(item["weight"] for item in ordered)
    if total_weight <= 0.0:
        return out

    def _pick(target: float) -> float:
        running = 0.0
        threshold = target * total_weight
        for item in ordered:
            running += item["weight"]
            if running >= threshold:
                return item["value"]
        return ordered[-1]["value"]

    out["iv_p10"] = _pick(0.10)
    out["iv_p25"] = _pick(0.25)
    out["iv_p50"] = _pick(0.50)
    out["iv_p75"] = _pick(0.75)
    out["iv_p90"] = _pick(0.90)
    return out


def _build_weighted_distribution(
    *,
    dcf_output: dict[str, Any] | None,
    scenario_weights: dict[str, float],
    method_estimates: dict[str, float],
    method_weights: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, float]]:
    """Build the one source-of-truth valuation distribution used for outputs.

    Method weights are first normalized across the methods that actually have a
    usable estimate. The DCF method weight is then split across bear/base/bull
    using the configured scenario weights, normalized over whichever scenarios
    produced a valid IV.
    """
    active_method_weights = {
        method: method_weights[method]
        for method, estimate in method_estimates.items()
        if estimate is not None and method in method_weights
    }
    normalized_method_weights = _normalize_weights(active_method_weights)

    distribution: list[dict[str, Any]] = []
    normalized_scenario_weights: dict[str, float] = {}

    dcf_weight = normalized_method_weights.get("dcf", 0.0)
    if dcf_output is not None and dcf_weight > 0.0:
        dcf_ivs = {
            label: float(value)
            for label, value in dcf_output.get("ivs", {}).items()
            if value is not None
        }
        normalized_scenario_weights = _normalize_weights(
            {
                label: float(scenario_weights.get(label, 0.0))
                for label in dcf_ivs
            }
        )
        for label, value in dcf_ivs.items():
            scenario_weight = normalized_scenario_weights.get(label, 0.0)
            if scenario_weight <= 0.0:
                continue
            distribution.append(
                {
                    "source": f"dcf_{label}",
                    "method": "dcf",
                    "scenario": label,
                    "value": value,
                    "weight": dcf_weight * scenario_weight,
                }
            )

    for method, estimate in method_estimates.items():
        if method == "dcf" or estimate is None:
            continue
        method_weight = normalized_method_weights.get(method, 0.0)
        if method_weight <= 0.0:
            continue
        distribution.append(
            {
                "source": method,
                "method": method,
                "scenario": None,
                "value": float(estimate),
                "weight": method_weight,
            }
        )

    return distribution, normalized_method_weights, normalized_scenario_weights


def _build_diagnostics(
    *,
    annual_statements: list[dict[str, Any]],
    ratio_rows: list[dict[str, Any]],
    current_price: float | None,
    diluted_shares: float | None,
    fcf_data: dict[str, Any] | None,
    terminal_growth: float,
    wacc: float,
    distribution: list[dict[str, Any]],
    uncertainty_width: float | None = None,
    iv_p10: float | None = None,
    iv_p25: float | None = None,
    iv_p50: float | None = None,
    iv_p75: float | None = None,
    iv_p90: float | None = None,
    method_estimates: dict[str, float] | None = None,
    dcf_output: dict[str, Any] | None = None,
    ratio_history_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, safe diagnostics payload for assumptions JSON."""
    blockers: list[str] = []
    warnings: list[str] = []

    if not annual_statements:
        blockers.append("missing_statements")
    elif len(annual_statements) < 2:
        warnings.append("limited_statement_history")

    if diluted_shares is None or diluted_shares <= 0.0:
        blockers.append("missing_shares_outstanding")

    if current_price is None or current_price <= 0.0:
        blockers.append("missing_latest_price")
        warnings.append("margin_of_safety_unavailable")

    if not ratio_rows:
        blockers.append("missing_ratio_factor_history")
        warnings.append("multiples_unavailable")

    ratio_history_diagnostics = ratio_history_diagnostics or {}
    ratio_history_status = ratio_history_diagnostics.get("status")
    ratio_history_codes = [
        str(code)
        for code in (ratio_history_diagnostics.get("reason_codes") or [])
        if code
    ]
    if ratio_history_status in {"filtered", "blocked", "unknown"}:
        warnings.extend(ratio_history_codes)
    if ratio_history_status == "blocked":
        blockers.append("stale_ratio_history")
        warnings.append("multiples_unavailable")

    if terminal_growth >= wacc:
        blockers.append("invalid_terminal_growth_gte_discount_rate")

    if fcf_data is not None:
        direct_fcf_status = fcf_data.get("direct_fcf_status")
        base_fcf = fcf_data.get("base_fcf")
        fcf_source = fcf_data.get("fcf_source")
        if direct_fcf_status == "negative":
            blockers.append("negative_direct_fcf")
            warnings.append("dcf_unavailable")
        elif direct_fcf_status == "zero":
            blockers.append("zero_direct_fcf")
            warnings.append("dcf_unavailable")
        elif base_fcf is None:
            blockers.append("missing_fcf")
            warnings.append("dcf_unavailable")
        elif fcf_source == "synthetic_fcff":
            warnings.append("dcf_uses_synthetic_fcff")
    else:
        blockers.append("missing_fcf")
        warnings.append("dcf_unavailable")

    # ── Distribution-level diagnostics ───────────────────────────────────────
    scenario_count = sum(1 for d in distribution if d.get("method") == "dcf")
    # Warn when multiple distribution entries all share the same value — this
    # explains cases where iv_p10..iv_p90 collapse to one number and MoS looks
    # artificially precise.
    if len(distribution) > 1 and len({d["value"] for d in distribution}) <= 1:
        warnings.append("distribution_collapsed")

    # ── Uncertainty classification ────────────────────────────────────────────
    uncertainty_category = _classify_uncertainty(uncertainty_width)

    valuation_status = "ok"
    if not distribution:
        valuation_status = "blocked"
    elif blockers:
        valuation_status = "partial"

    freshness_flag = "ok"
    if not annual_statements or current_price is None:
        freshness_flag = "missing_inputs"

    data_quality_flag = "ok"
    if valuation_status == "blocked":
        data_quality_flag = "insufficient"
    elif blockers or warnings:
        data_quality_flag = "limited"

    method_estimates = method_estimates or {}
    has_dcf_component = _is_finite_number(method_estimates.get("dcf"))
    has_multiples_component = _is_finite_number(method_estimates.get("multiples"))
    has_ddm_component = _is_finite_number(method_estimates.get("ddm"))
    valuation_method_coverage = _classify_method_coverage(
        has_dcf_component=has_dcf_component,
        has_multiples_component=has_multiples_component,
        has_ddm_component=has_ddm_component,
    )

    iv_values = [iv_p10, iv_p25, iv_p50, iv_p75, iv_p90]
    finite_percentiles = all(_is_finite_number(value) for value in iv_values)
    monotonic_percentiles = (
        finite_percentiles
        and float(iv_p10) <= float(iv_p25) <= float(iv_p50) <= float(iv_p75) <= float(iv_p90)
    )

    iv_range_ratio_p90_p10 = _safe_ratio(
        float(iv_p90) if _is_finite_number(iv_p90) else None,
        float(iv_p10) if _is_finite_number(iv_p10) else None,
    )

    distribution_values = [
        float(entry.get("value"))
        for entry in distribution
        if _is_finite_number(entry.get("value"))
    ]
    distribution_span_ratio = None
    if distribution_values:
        distribution_min = min(distribution_values)
        distribution_max = max(distribution_values)
        distribution_span_ratio = _safe_ratio(distribution_max, distribution_min)

    dcf_mid = method_estimates.get("dcf")
    multiples_mid = method_estimates.get("multiples")
    dcf_multiples_gap_ratio = None
    if _is_finite_number(dcf_mid) and _is_finite_number(multiples_mid):
        high = max(float(dcf_mid), float(multiples_mid))
        low = min(float(dcf_mid), float(multiples_mid))
        dcf_multiples_gap_ratio = _safe_ratio(high, low)

    midpoint_price_ratio = _safe_ratio(
        float(iv_p50) if _is_finite_number(iv_p50) else None,
        float(current_price) if _is_finite_number(current_price) else None,
    )

    terminal_spread = wacc - terminal_growth
    max_terminal_value_share = _max_terminal_value_share(dcf_output)

    sanity_reason_codes: set[str] = set()
    sanity_status = _SANITY_USABLE

    def _escalate(next_status: str, reason: str) -> None:
        nonlocal sanity_status
        rank = {
            _SANITY_USABLE: 0,
            _SANITY_HIGH_UNCERTAINTY: 1,
            _SANITY_UNRELIABLE: 2,
            _SANITY_MODEL_FAILURE: 3,
        }
        if rank[next_status] > rank[sanity_status]:
            sanity_status = next_status
        sanity_reason_codes.add(reason)

    # Integrity / model-failure checks.
    if valuation_status != "blocked" and not finite_percentiles:
        _escalate(_SANITY_MODEL_FAILURE, "missing_finite_percentiles")
    if valuation_status != "blocked" and finite_percentiles and not monotonic_percentiles:
        _escalate(_SANITY_MODEL_FAILURE, "non_monotonic_percentiles")
    if valuation_status != "blocked" and not distribution:
        _escalate(_SANITY_MODEL_FAILURE, "no_usable_distribution")
    if terminal_growth >= wacc:
        _escalate(_SANITY_MODEL_FAILURE, "invalid_terminal_growth_gte_discount_rate")

    # Method coverage and moderate uncertainty checks.
    if valuation_method_coverage == "no_usable_method":
        _escalate(_SANITY_MODEL_FAILURE, "no_usable_method")
    if not has_dcf_component and not has_multiples_component:
        _escalate(_SANITY_UNRELIABLE, "missing_dcf_and_multiples")
    if not has_dcf_component and (has_multiples_component or has_ddm_component):
        _escalate(_SANITY_HIGH_UNCERTAINTY, "missing_dcf_component")
    if not has_multiples_component and has_dcf_component:
        _escalate(_SANITY_HIGH_UNCERTAINTY, "missing_multiples_component")
    if scenario_count <= 1:
        _escalate(_SANITY_HIGH_UNCERTAINTY, "sparse_scenario_count")
    if uncertainty_category == "extreme":
        _escalate(_SANITY_HIGH_UNCERTAINTY, "extreme_uncertainty")

    # Economic plausibility checks.
    if iv_range_ratio_p90_p10 is not None:
        if iv_range_ratio_p90_p10 > 6.0:
            _escalate(_SANITY_UNRELIABLE, "severe_intrinsic_value_span")
        elif iv_range_ratio_p90_p10 > 3.0:
            _escalate(_SANITY_HIGH_UNCERTAINTY, "wide_intrinsic_value_span")

    if distribution_span_ratio is not None:
        if distribution_span_ratio > 6.0:
            _escalate(_SANITY_UNRELIABLE, "severe_distribution_span_ratio")
        elif distribution_span_ratio > 3.0:
            _escalate(_SANITY_HIGH_UNCERTAINTY, "wide_distribution_span_ratio")

    if dcf_multiples_gap_ratio is not None:
        if dcf_multiples_gap_ratio > 3.5:
            _escalate(_SANITY_UNRELIABLE, "severe_dcf_multiples_divergence")
        elif dcf_multiples_gap_ratio > 2.0:
            _escalate(_SANITY_HIGH_UNCERTAINTY, "dcf_multiples_divergence")

    if max_terminal_value_share is not None:
        if max_terminal_value_share > 0.95:
            _escalate(_SANITY_UNRELIABLE, "severe_terminal_value_dominance")
        elif max_terminal_value_share > 0.85:
            _escalate(_SANITY_HIGH_UNCERTAINTY, "terminal_value_dominance")

    if terminal_spread < 0.015:
        _escalate(_SANITY_UNRELIABLE, "terminal_spread_too_narrow")
    elif terminal_spread < 0.025:
        _escalate(_SANITY_HIGH_UNCERTAINTY, "terminal_spread_narrow")

    if midpoint_price_ratio is None:
        _escalate(_SANITY_HIGH_UNCERTAINTY, "missing_current_price_for_relative_checks")
    else:
        if midpoint_price_ratio > 8.0 or midpoint_price_ratio < 0.125:
            _escalate(_SANITY_UNRELIABLE, "severe_midpoint_price_implausibility")
        elif midpoint_price_ratio > 4.0 or midpoint_price_ratio < 0.25:
            _escalate(_SANITY_HIGH_UNCERTAINTY, "midpoint_price_implausibility")

    if fcf_data is not None and fcf_data.get("direct_fcf_status") in {"negative", "zero"} and distribution:
        _escalate(_SANITY_UNRELIABLE, "negative_or_zero_fcf_path")

    if ratio_history_status == "blocked":
        _escalate(_SANITY_UNRELIABLE, "stale_ratio_history")
    elif "stale_ratio_history" in ratio_history_codes:
        _escalate(_SANITY_HIGH_UNCERTAINTY, "stale_ratio_history")

    valuation_evidence_usable = sanity_status in {_SANITY_USABLE, _SANITY_HIGH_UNCERTAINTY}
    valuation_display_suppressed = sanity_status in {_SANITY_UNRELIABLE, _SANITY_MODEL_FAILURE}
    valuation_signal_influence_blocked = sanity_status in {_SANITY_UNRELIABLE, _SANITY_MODEL_FAILURE}

    return {
        "valuation_status": valuation_status,
        "freshness_flag": freshness_flag,
        "data_quality_flag": data_quality_flag,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "mos_basis": "iv_p10",
        "scenario_count": scenario_count,
        "uncertainty_category": uncertainty_category,
        "valuation_sanity_status": sanity_status,
        "valuation_sanity_reason_codes": sorted(sanity_reason_codes),
        "valuation_evidence_usable": valuation_evidence_usable,
        "valuation_display_suppressed": valuation_display_suppressed,
        "valuation_signal_influence_blocked": valuation_signal_influence_blocked,
        "valuation_method_coverage": valuation_method_coverage,
        "iv_range_ratio_p90_p10": iv_range_ratio_p90_p10,
        "distribution_span_ratio": distribution_span_ratio,
        "dcf_multiples_gap_ratio": dcf_multiples_gap_ratio,
        "max_terminal_value_share": max_terminal_value_share,
        "terminal_spread": terminal_spread,
        "midpoint_price_ratio": midpoint_price_ratio,
        "ratio_history_status": ratio_history_status,
        "ratio_history_reason_codes": ratio_history_codes,
        "ratio_rows_available": ratio_history_diagnostics.get("ratio_rows_available"),
        "ratio_rows_used": ratio_history_diagnostics.get("ratio_rows_used"),
        "ratio_rows_excluded": ratio_history_diagnostics.get("ratio_rows_excluded"),
        "latest_statement_period_end_date": ratio_history_diagnostics.get(
            "latest_statement_period_end_date"
        ),
    }


# ---------------------------------------------------------------------------
# Revenue-based FCF proxy
# ---------------------------------------------------------------------------


def _revenue_based_fcf(
    annual_statements: list[dict[str, Any]],
    growth_rate: float,
    ebit_margin_cap: float,
    tax_rate: float,
) -> float | None:
    """Derive a smoothed normalised FCF from the last 3 years of revenue + margins."""
    if not annual_statements:
        return None
    revenues = [_get(s, "revenue") for s in annual_statements[:3]]
    revenues = [r for r in revenues if r is not None and r > 0.0]
    if not revenues:
        return None
    avg_revenue = sum(revenues) / len(revenues)

    # Collect operating margins; fall back to ebit / revenue.
    margins = []
    for stmt in annual_statements[:3]:
        ebit = _get(stmt, "ebit")
        rev = _get(stmt, "revenue")
        if ebit is not None and rev and rev > 0.0:
            margins.append(min(ebit / rev, ebit_margin_cap))
    ebit_margin = (sum(margins) / len(margins)) if margins else None
    if ebit_margin is None or ebit_margin <= 0.0:
        return None

    # Project next-year revenue using the scenario growth rate.
    next_revenue = avg_revenue * (1.0 + growth_rate)
    nopat = next_revenue * ebit_margin * (1.0 - tax_rate)
    # Capex and D&A as % of revenue (fallback: 5% capex, 3% D&A).
    capex_pct = 0.05
    da_pct = 0.03
    if annual_statements:
        capex_vals = [
            abs(_get(s, "capex") or 0.0) / (_get(s, "revenue") or 1.0)
            for s in annual_statements[:3]
            if _get(s, "revenue")
        ]
        da_vals = [
            (_get(s, "depreciation_amortization") or 0.0) / (_get(s, "revenue") or 1.0)
            for s in annual_statements[:3]
            if _get(s, "revenue")
        ]
        if capex_vals:
            capex_pct = sum(capex_vals) / len(capex_vals)
        if da_vals:
            da_pct = sum(da_vals) / len(da_vals)

    estimated_fcf = nopat + next_revenue * da_pct - next_revenue * capex_pct
    return estimated_fcf if estimated_fcf > 0.0 else None


# ---------------------------------------------------------------------------
# Core scenario runner
# ---------------------------------------------------------------------------


def _run_three_scenarios(
    *,
    base_fcf: float | None,
    base_growth: float,
    base_wacc: float,
    terminal_growth: float,
    forecast_years: int,
    net_debt: float | None,
    minority_interest: float | None,
    preferred_equity: float | None,
    diluted_shares: float | None,
    scenario_weights: dict[str, float],
    bear_growth_haircut: float = _BEAR_GROWTH_HAIRCUT,
    bull_growth_premium: float = _BULL_GROWTH_PREMIUM,
    bear_wacc_spread: float = _BEAR_WACC_SPREAD,
    bull_wacc_spread: float = _BULL_WACC_SPREAD,
) -> dict[str, Any]:
    """Run bear/base/bull scenarios and return per-scenario IV and blended stats."""
    scenarios: dict[str, dict[str, float | None]] = {}

    bear_growth = base_growth * bear_growth_haircut
    bull_growth = base_growth * bull_growth_premium
    bear_wacc = base_wacc + bear_wacc_spread
    bull_wacc = max(0.01, base_wacc + bull_wacc_spread)

    for label, growth, wacc in (
        ("bear", bear_growth, bear_wacc),
        ("base", base_growth, base_wacc),
        ("bull", bull_growth, bull_wacc),
    ):
        scenarios[label] = run_dcf_scenario(
            base_fcf=base_fcf,
            growth_rate=growth,
            wacc=wacc,
            terminal_growth=terminal_growth,
            forecast_years=forecast_years,
            net_debt=net_debt,
            minority_interest=minority_interest,
            preferred_equity=preferred_equity,
            diluted_shares=diluted_shares,
        )

    # Collect per-share IVs that are not None.
    ivs: dict[str, float] = {}
    for label, result in scenarios.items():
        iv = result.get("intrinsic_value_per_share")
        if iv is not None:
            ivs[label] = iv

    # Weighted average using scenario_weights.
    weighted_iv: float | None = None
    if ivs:
        total_weight = 0.0
        wsum = 0.0
        for label, iv in ivs.items():
            w = scenario_weights.get(label, 0.0)
            wsum += w * iv
            total_weight += w
        if total_weight > 0.0:
            weighted_iv = wsum / total_weight

    return {
        "scenarios": scenarios,
        "ivs": ivs,
        "weighted_iv": weighted_iv,
    }


# ---------------------------------------------------------------------------
# Percentile builder from scenario IVs + multiples
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_valuation_run(
    company_id: str,
    repo_module: Any,
    valuation_date: str,
    *,
    sector: str | None = None,
    company_currency: str = "USD",
    overrides: dict[str, Any] | None = None,
    diagnostics_out: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compute a full valuation run for one company on one date.

    Parameters
    ----------
    company_id:
        UUID of the company in Supabase.
    repo_module:
        Object exposing ``get_statements_for_company``, ``get_prices_for_company``,
        ``get_ratios_for_company`` (Phase 4 repo function).  May also expose
        ``get_filings_for_company``.  In tests, pass a fake.
    valuation_date:
        ISO date string (YYYY-MM-DD).  All repo reads use this as the
        point-in-time ceiling.
    sector:
        GICS or FMP sector string.  Used to select the financial-sector model.
    company_currency:
        Reporting / pricing currency.
    overrides:
        Dict of parameter overrides (e.g. ``{"discount_rate_fallback": 0.10}``).

    Returns
    -------
    dict or None
        A ``valuation_runs``-shaped dict ready for ``upsert_valuation_run``, or
        None when there is insufficient data to produce any estimate.
    """
    overrides = overrides or {}
    defaults = _load_defaults()

    # ── Config resolution ────────────────────────────────────────────────────
    forecast_years = int(_resolve(defaults, overrides, "explicit_forecast_years", 5))
    terminal_growth_floor = float(_resolve(defaults, overrides, "terminal_growth_floor", 0.01))
    terminal_growth_cap = float(_resolve(defaults, overrides, "terminal_growth_cap", 0.03))
    tax_rate_fallback = float(_resolve(defaults, overrides, "tax_rate_fallback", 0.25))
    wacc = float(_resolve(defaults, overrides, "discount_rate_fallback", 0.09))
    revenue_growth_cap = float(_resolve(defaults, overrides, "revenue_growth_cap", 0.30))
    ebit_margin_cap = float(_resolve(defaults, overrides, "ebit_margin_cap", 0.50))
    sw_raw = _resolve(defaults, overrides, "scenario_weights", {})
    scenario_weights = {
        "bear": float(sw_raw.get("bear", 0.25)),
        "base": float(sw_raw.get("base", 0.50)),
        "bull": float(sw_raw.get("bull", 0.25)),
    }
    terminal_growth = max(terminal_growth_floor, min(terminal_growth_cap, 0.02))

    # ── Data reads ───────────────────────────────────────────────────────────
    annual_statements: list[dict[str, Any]] = repo_module.get_statements_for_company(
        company_id, as_of_date=valuation_date, limit=5
    )
    price_rows: list[dict[str, Any]] = repo_module.get_prices_for_company(
        company_id, as_of_date=valuation_date, limit=2
    )
    ratio_rows: list[dict[str, Any]] = repo_module.get_ratios_for_company(
        company_id, as_of_date=valuation_date
    )

    # Current price (most recent close).
    # Primary schema field is ``close`` (price_eod); ``close_price`` kept as fallback.
    current_price: float | None = None
    if price_rows:
        current_price = _get(price_rows[0], "close") or _get(price_rows[0], "close_price")

    # Most recent annual statement.
    current_stmt: dict[str, Any] | None = annual_statements[0] if annual_statements else None
    ratio_rows_for_valuation, ratio_history_diagnostics = (
        _filter_ratio_rows_for_statement_vintage(ratio_rows, current_stmt)
    )

    diluted_shares: float | None = None
    if current_stmt:
        # Primary schema field is ``diluted_shares`` (statements_norm).
        # Legacy aliases kept as fallbacks for backwards compatibility.
        diluted_shares = (
            _get(current_stmt, "diluted_shares")
            or _get(current_stmt, "shares_diluted")
            or _get(current_stmt, "diluted_shares_outstanding")
        )

    # Net debt.
    net_debt = _compute_net_debt(current_stmt)

    # Minority interest / preferred equity (minor components, default 0).
    minority_interest: float | None = _get(current_stmt, "minority_interest") if current_stmt else None
    preferred_equity: float | None = _get(current_stmt, "preferred_equity") if current_stmt else None

    # ── Revenue growth rate ──────────────────────────────────────────────────
    base_growth = 0.0
    if len(annual_statements) >= 2:
        rev_current = _get(annual_statements[0], "revenue")
        rev_prior = _get(annual_statements[1], "revenue")
        if rev_current and rev_prior and rev_prior > 0.0:
            raw_growth = (rev_current - rev_prior) / rev_prior
            base_growth = max(-0.50, min(revenue_growth_cap, raw_growth))

    # ── Financial sector fallback ────────────────────────────────────────────
    use_financial_sector = is_financial_sector(sector)

    configured_method_weights = {
        key: float(value)
        for key, value in _resolve(defaults, overrides, "method_weights", _DEFAULT_METHOD_WEIGHTS).items()
    }
    assumptions: dict[str, Any] = {
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "base_growth": base_growth,
        "forecast_years": forecast_years,
        "tax_rate": tax_rate_fallback,
        "sector": sector,
        "model_version": MODEL_VERSION,
        "scenario_weights_configured": scenario_weights,
    }
    method_estimates: dict[str, float] = {}
    dcf_output: dict[str, Any] | None = None
    fcf_data: dict[str, Any] | None = None

    if use_financial_sector:
        # Financial sector: P/B + ROE / Ke spread.
        roe_val: float | None = None
        bvps: float | None = None
        if ratio_rows_for_valuation:
            roe_val = _get(ratio_rows_for_valuation[0], "roe")
        if current_stmt and diluted_shares and diluted_shares > 0.0:
            eq = _get(current_stmt, "total_equity")
            if eq is not None:
                bvps = eq / diluted_shares

        fin_result = compute_financial_sector_value(
            roe=roe_val,
            cost_of_equity=wacc,
            book_value_per_share=bvps,
        )
        iv_fs = fin_result.get("intrinsic_value_per_share")
        if iv_fs is not None:
            method_estimates["financial_sector_pb"] = float(iv_fs)
        assumptions["financial_sector"] = fin_result

    else:
        # ── DCF ──────────────────────────────────────────────────────────────
        fcf_data = extract_base_fcf(
            annual_statements,
            ebit_margin_cap=ebit_margin_cap,
            tax_rate_fallback=tax_rate_fallback,
        )
        base_fcf = fcf_data.get("base_fcf")

        # Revenue-based proxy applies only when direct FCF is missing. If the
        # latest direct FCF is explicitly zero or negative, prefer no DCF
        # valuation over a synthetic fallback.
        if base_fcf is None and fcf_data.get("direct_fcf_status") == "missing":
            base_fcf = _revenue_based_fcf(
                annual_statements, base_growth, ebit_margin_cap, tax_rate_fallback
            )

        dcf_output = _run_three_scenarios(
            base_fcf=base_fcf,
            base_growth=base_growth,
            base_wacc=wacc,
            terminal_growth=terminal_growth,
            forecast_years=forecast_years,
            net_debt=net_debt,
            minority_interest=minority_interest,
            preferred_equity=preferred_equity,
            diluted_shares=diluted_shares,
            scenario_weights=scenario_weights,
        )
        dcf_iv = dcf_output.get("weighted_iv")
        if dcf_iv is not None:
            method_estimates["dcf"] = float(dcf_iv)

        assumptions["dcf"] = {
            "base_fcf": base_fcf,
            "direct_fcf": fcf_data.get("direct_fcf") if fcf_data else None,
            "direct_fcf_status": fcf_data.get("direct_fcf_status") if fcf_data else None,
            "fcf_source": fcf_data.get("fcf_source") if fcf_data else None,
            "bear_iv": dcf_output.get("ivs", {}).get("bear"),
            "base_iv": dcf_output.get("ivs", {}).get("base"),
            "bull_iv": dcf_output.get("ivs", {}).get("bull"),
        }

        # ── Multiples ─────────────────────────────────────────────────────────
        mult_result = compute_multiples_value(
            statement=current_stmt,
            net_debt=net_debt,
            diluted_shares=diluted_shares,
            ratio_rows=ratio_rows_for_valuation,
        )
        mult_blended = mult_result.get("blended_value")
        if mult_blended is not None:
            method_estimates["multiples"] = float(mult_blended)
        assumptions["multiples"] = mult_result

        # ── DDM ───────────────────────────────────────────────────────────────
        if is_ddm_applicable(annual_statements):
            dps: float | None = None
            if current_stmt and diluted_shares and diluted_shares > 0.0:
                div_paid = _get(current_stmt, "dividends_paid")
                if div_paid is not None:
                    dps = abs(div_paid) / diluted_shares
            ddm_iv = compute_ddm_value(
                dps=dps,
                growth_rate=terminal_growth,
                cost_of_equity=wacc,
            )
            if ddm_iv is not None:
                method_estimates["ddm"] = float(ddm_iv)
            assumptions["ddm"] = {"dps": dps, "iv": ddm_iv}

    distribution, method_weights_used, scenario_weights_used = _build_weighted_distribution(
        dcf_output=dcf_output,
        scenario_weights=scenario_weights,
        method_estimates=method_estimates,
        method_weights=(
            {"financial_sector_pb": 1.0}
            if use_financial_sector
            else configured_method_weights
        ),
    )

    # ── Percentiles and uncertainty — computed here so _build_diagnostics ────
    # ── can include uncertainty_category in the assumptions payload.       ────
    percentiles = _weighted_percentiles(distribution)
    iv_p10 = percentiles.get("iv_p10")
    iv_p25 = percentiles.get("iv_p25")
    iv_p50 = percentiles.get("iv_p50")
    iv_p75 = percentiles.get("iv_p75")
    iv_p90 = percentiles.get("iv_p90")

    margin_of_safety_conservative: float | None = None
    if current_price and current_price > 0.0 and iv_p10 is not None:
        margin_of_safety_conservative = (iv_p10 - current_price) / current_price

    uncertainty_width: float | None = None
    if iv_p90 is not None and iv_p10 is not None and iv_p10 > 0.0:
        uncertainty_width = (iv_p90 - iv_p10) / iv_p10

    diagnostics = _build_diagnostics(
        annual_statements=annual_statements,
        ratio_rows=ratio_rows_for_valuation,
        current_price=current_price,
        diluted_shares=diluted_shares,
        fcf_data=fcf_data,
        terminal_growth=terminal_growth,
        wacc=wacc,
        distribution=distribution,
        uncertainty_width=uncertainty_width,
        iv_p10=iv_p10,
        iv_p25=iv_p25,
        iv_p50=iv_p50,
        iv_p75=iv_p75,
        iv_p90=iv_p90,
        method_estimates=method_estimates,
        dcf_output=dcf_output,
        ratio_history_diagnostics=ratio_history_diagnostics,
    )
    assumptions["ratio_history"] = ratio_history_diagnostics
    assumptions["aggregation"] = {
        "distribution_method": "weighted_step_percentiles",
        "method_weights_used": method_weights_used,
        "scenario_weights_used": scenario_weights_used,
        "distribution": distribution,
    }
    assumptions["diagnostics"] = diagnostics

    # ── No estimates ─────────────────────────────────────────────────────────
    if not distribution:
        # Populate diagnostics_out so the caller can log why valuation was skipped
        # without returning a non-None result that would be persisted.
        if diagnostics_out is not None:
            # Compact available_inputs summary — field names only, no values.
            available: list[str] = []
            if current_stmt:
                available += [k for k, v in current_stmt.items() if v is not None]
            if current_price is not None:
                available.append("current_price")
            if diluted_shares is not None:
                available.append("diluted_shares")
            diagnostics_out.update({
                "blockers": diagnostics.get("blockers", []),
                "valuation_status": diagnostics.get("valuation_status", "blocked"),
                "data_quality_flag": diagnostics.get("data_quality_flag", "insufficient"),
                "available_inputs": available[:20],  # cap to keep event payload compact
                "fcf_source": (fcf_data or {}).get("fcf_source"),
                "direct_fcf_status": (fcf_data or {}).get("direct_fcf_status"),
            })
        return None

    return {
        "company_id": company_id,
        "valuation_date": valuation_date,
        "model_version": MODEL_VERSION,
        "method_weights": method_weights_used,
        "assumptions": assumptions,
        "iv_p10": iv_p10,
        "iv_p25": iv_p25,
        "iv_p50": iv_p50,
        "iv_p75": iv_p75,
        "iv_p90": iv_p90,
        "current_price": current_price,
        "margin_of_safety_conservative": margin_of_safety_conservative,
        "uncertainty_width": uncertainty_width,
        "currency": company_currency,
    }

