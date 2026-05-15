"""Qualitative scoring — Phase 5.

Implements deterministic, rule-based scoring across four dimensions:

  - moat_score        Economic moat strength (0–100)
  - management_score  Capital allocation quality (0–100)
  - risk_score        Financial risk, inverted: higher = safer (0–100)
  - governance_score  Reporting quality and shareholder treatment (0–100)

Each dimension starts at 50 (neutral) and is adjusted up or down based on
observable evidence drawn from ratios_factors, statements_norm, and
filings_index.  When data is missing the score stays conservative (near 50)
rather than adding optimistic points without evidence.

The weighted final score uses the ``qualitative_weights`` section of
``configs/scoring_weights.yml`` and is clamped to [0, 100].

``human_override`` is an optional numeric adjustment clamped to [-10, +10]
applied to the weighted auto-score before final clamping to [0, 100].
"""
from __future__ import annotations

import math
from typing import Any

from investment_app.config.loader import load_scoring_weights

MODEL_VERSION = "qual_v0"

# Diagnostic bounds for ROIC outlier detection.
# Values outside this range are flagged in evidence but do NOT change the score.
_ROIC_DIAGNOSTIC_LO: float = -2.0
_ROIC_DIAGNOSTIC_HI: float = 5.0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* to the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


def _safe(value: Any, default: float | None = None) -> float | None:
    """Return *value* as float, or *default* if it is None, non-finite, or non-numeric."""
    if value is None:
        return default
    try:
        f = float(value)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


# ── Moat score ────────────────────────────────────────────────────────────────


def _score_moat(
    ratios: dict[str, Any],
    annual_stmts: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    """Compute moat score (0–100) and an evidence dict.

    Evidence dimensions
    -------------------
    ROIC:
        Strong persistent ROIC signals a durable competitive advantage.
    Gross-margin stability:
        Requires 3+ annual periods. Rewards low variance; penalises shrinkage.
    FCF track record:
        Consistently positive FCF signals genuine cash generation.
    Revenue trend:
        Growing revenue rewards organic moat; sharp decline is penalised.
    """
    score = 50.0
    evidence: dict[str, Any] = {}

    # ── ROIC ─────────────────────────────────────────────────────────────────
    roic = _safe(ratios.get("roic"))
    evidence["roic"] = roic
    if roic is not None:
        if roic > 0.15:
            score += 15
            evidence["roic_signal"] = "strong (>15%)"
        elif roic > 0.10:
            score += 10
            evidence["roic_signal"] = "good (>10%)"
        elif roic > 0.08:
            score += 5
            evidence["roic_signal"] = "adequate (>8%)"
        elif roic < 0.0:
            score -= 15
            evidence["roic_signal"] = "negative"
        else:
            evidence["roic_signal"] = "weak (0–8%)"
        # Outlier diagnostic: flag extreme raw ROIC values for investigation.
        # No score change — diagnostic only.
        if roic < _ROIC_DIAGNOSTIC_LO:
            evidence["roic_outlier"] = True
            evidence["roic_raw"] = roic
            evidence["roic_diagnostic_bound"] = "low"
        elif roic > _ROIC_DIAGNOSTIC_HI:
            evidence["roic_outlier"] = True
            evidence["roic_raw"] = roic
            evidence["roic_diagnostic_bound"] = "high"
    else:
        evidence["roic_signal"] = "missing"

    # ── Gross-margin stability ────────────────────────────────────────────────
    gm_ratios: list[float] = []
    for s in annual_stmts:
        rev = _safe(s.get("revenue"))
        gp = _safe(s.get("gross_profit"))
        if rev and rev > 0 and gp is not None:
            gm_ratios.append(gp / rev)
    evidence["gross_margin_periods"] = len(gm_ratios)
    if len(gm_ratios) >= 3:
        avg_gm = sum(gm_ratios) / len(gm_ratios)
        std_gm = math.sqrt(sum((g - avg_gm) ** 2 for g in gm_ratios) / len(gm_ratios))
        evidence["gross_margin_avg"] = round(avg_gm, 4)
        evidence["gross_margin_std"] = round(std_gm, 4)
        if std_gm < 0.03:
            score += 8
            evidence["margin_stability"] = "very stable (<3% std)"
        elif std_gm < 0.06:
            score += 4
            evidence["margin_stability"] = "stable (<6% std)"
        elif std_gm > 0.10:
            score -= 5
            evidence["margin_stability"] = "volatile (>10% std)"
        else:
            evidence["margin_stability"] = "moderate variance"
        # Outlier diagnostic: extremely high gross-margin std may indicate data
        # quality issues (e.g. segment reclassifications, M&A distortions).
        # Diagnostic only — no score change.
        if std_gm > 0.50:
            evidence["gross_margin_std_outlier"] = True
        # Trend: gm_ratios[0] is the most recent period (newest-first ordering).
        if gm_ratios[0] > gm_ratios[-1] + 0.03:
            score += 4
            evidence["margin_trend"] = "expanding"
        elif gm_ratios[0] < gm_ratios[-1] - 0.05:
            score -= 4
            evidence["margin_trend"] = "shrinking"
        else:
            evidence["margin_trend"] = "flat"
    else:
        evidence["margin_stability"] = "insufficient data"
        evidence["margin_trend"] = "insufficient data"

    # ── FCF track record ──────────────────────────────────────────────────────
    fcf_vals = [_safe(s.get("free_cash_flow")) for s in annual_stmts[:3]]
    fcf_vals = [v for v in fcf_vals if v is not None]
    evidence["fcf_periods"] = len(fcf_vals)
    if fcf_vals:
        positive_count = sum(1 for v in fcf_vals if v > 0)
        evidence["fcf_positive_periods"] = positive_count
        ratio_positive = positive_count / len(fcf_vals)
        if ratio_positive == 1.0:
            score += 10
            evidence["fcf_signal"] = "consistently positive"
        elif ratio_positive >= 0.67:
            score += 5
            evidence["fcf_signal"] = "mostly positive"
        elif ratio_positive == 0.0:
            score -= 10
            evidence["fcf_signal"] = "consistently negative"
        else:
            score -= 3
            evidence["fcf_signal"] = "mixed"
    else:
        evidence["fcf_signal"] = "missing"

    # ── Revenue trend ─────────────────────────────────────────────────────────
    rev_growth = _safe(ratios.get("revenue_growth_yoy"))
    evidence["revenue_growth_yoy"] = rev_growth
    if rev_growth is not None:
        if rev_growth > 0.05:
            score += 4
            evidence["revenue_signal"] = "growing"
        elif rev_growth < -0.10:
            score -= 5
            evidence["revenue_signal"] = "declining"
        else:
            evidence["revenue_signal"] = "stable"
    else:
        evidence["revenue_signal"] = "missing"

    return _clamp(score), evidence


# ── Management score ──────────────────────────────────────────────────────────


def _score_management(
    ratios: dict[str, Any],  # noqa: ARG001 — reserved for future ratio signals
    annual_stmts: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    """Compute management score (0–100) and an evidence dict.

    Evidence dimensions
    -------------------
    Share-count trend:
        Buybacks (falling share count) indicate shareholder-friendly capital allocation.
    FCF conversion:
        FCF consistently above net income signals high-quality earnings.
    Capex intensity:
        Very high capex relative to revenue may indicate capital misallocation.
    """
    score = 50.0
    evidence: dict[str, Any] = {}

    # ── Share-count trend ─────────────────────────────────────────────────────
    share_counts: list[float] = []
    for s in annual_stmts:
        v = _safe(s.get("diluted_shares"))
        if v and v > 0:
            share_counts.append(v)
    evidence["share_count_periods"] = len(share_counts)
    if len(share_counts) >= 3:
        oldest = share_counts[-1]
        newest = share_counts[0]
        dilution_rate = (newest - oldest) / oldest if oldest > 0 else 0.0
        evidence["dilution_rate"] = round(dilution_rate, 4)
        if dilution_rate < -0.03:
            score += 12
            evidence["dilution_signal"] = "buybacks detected"
        elif dilution_rate < 0.02:
            score += 5
            evidence["dilution_signal"] = "share count stable"
        elif dilution_rate > 0.10:
            score -= 10
            evidence["dilution_signal"] = "significant dilution (>10%)"
        elif dilution_rate > 0.05:
            score -= 5
            evidence["dilution_signal"] = "moderate dilution (>5%)"
        else:
            evidence["dilution_signal"] = "minor dilution"
    elif len(share_counts) == 2:
        dilution_rate = (
            (share_counts[0] - share_counts[1]) / share_counts[1]
            if share_counts[1] > 0
            else 0.0
        )
        evidence["dilution_rate"] = round(dilution_rate, 4)
        evidence["dilution_signal"] = "limited data (2 periods)"
    else:
        evidence["dilution_signal"] = "missing"

    # ── FCF conversion ────────────────────────────────────────────────────────
    fcf_conversion_vals: list[float] = []
    for s in annual_stmts[:3]:
        fcf = _safe(s.get("free_cash_flow"))
        ni = _safe(s.get("net_income"))
        if fcf is not None and ni and ni > 0:
            fcf_conversion_vals.append(fcf / ni)
    evidence["fcf_conversion_periods"] = len(fcf_conversion_vals)
    if fcf_conversion_vals:
        avg_conversion = sum(fcf_conversion_vals) / len(fcf_conversion_vals)
        evidence["fcf_conversion_avg"] = round(avg_conversion, 4)
        if avg_conversion > 1.0:
            score += 10
            evidence["fcf_conversion_signal"] = "strong (FCF > net income)"
        elif avg_conversion > 0.7:
            score += 5
            evidence["fcf_conversion_signal"] = "good (>70%)"
        elif avg_conversion < 0.0:
            score -= 10
            evidence["fcf_conversion_signal"] = "negative FCF despite profits"
        else:
            evidence["fcf_conversion_signal"] = "weak (<70%)"
    else:
        evidence["fcf_conversion_signal"] = "missing"

    # ── Capex intensity ───────────────────────────────────────────────────────
    capex_ratios: list[float] = []
    for s in annual_stmts[:3]:
        capex = _safe(s.get("capex"))
        rev = _safe(s.get("revenue"))
        if capex is not None and rev and rev > 0:
            capex_ratios.append(abs(capex) / rev)
    if capex_ratios:
        avg_capex_intensity = sum(capex_ratios) / len(capex_ratios)
        evidence["capex_intensity_avg"] = round(avg_capex_intensity, 4)
        if avg_capex_intensity > 0.25:
            score -= 5
            evidence["capex_signal"] = "high capex intensity (>25%)"
        else:
            evidence["capex_signal"] = "moderate capex"
    else:
        evidence["capex_signal"] = "missing"

    return _clamp(score), evidence


# ── Risk score ────────────────────────────────────────────────────────────────


def _score_risk(
    ratios: dict[str, Any],
    annual_stmts: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    """Compute risk score (0–100, inverted: higher = lower risk) and evidence dict.

    Evidence dimensions
    -------------------
    Leverage:
        Net debt / EBITDA above 3× is a meaningful risk indicator.
    Interest coverage:
        Coverage below 2× is a stress signal; below 1× is critical.
    News sentiment:
        Sustained negative news sentiment can precede fundamental deterioration.
    Revenue + margin trend:
        Both falling simultaneously amplifies financial stress.
    """
    score = 50.0
    evidence: dict[str, Any] = {}

    # ── Leverage ──────────────────────────────────────────────────────────────
    net_debt_ebitda = _safe(ratios.get("net_debt_to_ebitda"))
    evidence["net_debt_to_ebitda"] = net_debt_ebitda
    if net_debt_ebitda is not None:
        if net_debt_ebitda < 0.0:
            score += 12
            evidence["leverage_signal"] = "net cash position"
        elif net_debt_ebitda < 1.0:
            score += 10
            evidence["leverage_signal"] = "low leverage (<1x)"
        elif net_debt_ebitda < 2.0:
            score += 5
            evidence["leverage_signal"] = "modest leverage (<2x)"
        elif net_debt_ebitda < 3.0:
            score -= 5
            evidence["leverage_signal"] = "moderate leverage (2–3x)"
        elif net_debt_ebitda < 5.0:
            score -= 12
            evidence["leverage_signal"] = "elevated leverage (3–5x)"
        else:
            score -= 20
            evidence["leverage_signal"] = "high leverage (>5x)"
    else:
        evidence["leverage_signal"] = "missing"

    # ── Interest coverage ─────────────────────────────────────────────────────
    interest_coverage = _safe(ratios.get("interest_coverage"))
    evidence["interest_coverage"] = interest_coverage
    if interest_coverage is not None:
        if interest_coverage > 10.0:
            score += 10
            evidence["coverage_signal"] = "very strong (>10x)"
        elif interest_coverage > 5.0:
            score += 6
            evidence["coverage_signal"] = "strong (>5x)"
        elif interest_coverage > 2.0:
            score += 2
            evidence["coverage_signal"] = "adequate (>2x)"
        elif interest_coverage > 1.0:
            score -= 5
            evidence["coverage_signal"] = "weak (1–2x)"
        else:
            score -= 15
            evidence["coverage_signal"] = "critical (<1x)"
    else:
        evidence["coverage_signal"] = "missing"

    # ── News sentiment ────────────────────────────────────────────────────────
    news_sentiment = _safe(ratios.get("news_sentiment_7d"))
    evidence["news_sentiment_7d"] = news_sentiment
    if news_sentiment is not None:
        if news_sentiment > 0.2:
            score += 5
            evidence["news_signal"] = "positive"
        elif news_sentiment < -0.3:
            score -= 8
            evidence["news_signal"] = "negative"
        else:
            evidence["news_signal"] = "neutral"
    else:
        evidence["news_signal"] = "missing"

    # ── Revenue + margin both declining ───────────────────────────────────────
    if len(annual_stmts) >= 2:
        curr = annual_stmts[0]
        prev = annual_stmts[1]
        curr_rev = _safe(curr.get("revenue"))
        prev_rev = _safe(prev.get("revenue"))
        curr_op_inc = _safe(curr.get("operating_income"))
        prev_op_inc = _safe(prev.get("operating_income"))
        if (
            curr_rev is not None
            and prev_rev is not None
            and prev_rev > 0
            and curr_rev < prev_rev
            and curr_op_inc is not None
            and prev_op_inc is not None
            and prev_rev > 0
        ):
            curr_op_margin = curr_op_inc / curr_rev if curr_rev > 0 else None
            prev_op_margin = prev_op_inc / prev_rev
            if (
                curr_op_margin is not None
                and prev_op_margin is not None
                and curr_op_margin < prev_op_margin - 0.02
            ):
                score -= 8
                evidence["revenue_margin_signal"] = "revenue and margin both declining"
            else:
                evidence["revenue_margin_signal"] = "revenue declining, margin stable"
        else:
            evidence["revenue_margin_signal"] = "stable or improving"
    else:
        evidence["revenue_margin_signal"] = "insufficient data"

    return _clamp(score), evidence


# ── Governance score ──────────────────────────────────────────────────────────


def _score_governance(
    annual_stmts: list[dict[str, Any]],
    filings: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    """Compute governance score (0–100) and an evidence dict.

    Evidence dimensions
    -------------------
    Restatements:
        Any ``restated_flag = true`` row subtracts points.
    Share-based compensation:
        Excessive SBC relative to revenue dilutes shareholder value.
    Filing regularity:
        Presence of recent 10-K / 20-F signals timely disclosure.
    """
    score = 50.0
    evidence: dict[str, Any] = {}

    # ── Restatements ──────────────────────────────────────────────────────────
    restated_count = sum(1 for s in annual_stmts if s.get("restated_flag"))
    evidence["restated_periods"] = restated_count
    if restated_count > 0:
        score -= min(15, restated_count * 8)
        evidence["restatement_signal"] = f"{restated_count} restatement(s) detected"
    else:
        evidence["restatement_signal"] = "no restatements"

    # ── Share-based compensation ──────────────────────────────────────────────
    sbc_ratios: list[float] = []
    for s in annual_stmts[:3]:
        sbc = _safe(s.get("stock_based_compensation"))
        rev = _safe(s.get("revenue"))
        if sbc is not None and rev and rev > 0:
            sbc_ratios.append(abs(sbc) / rev)
    if sbc_ratios:
        avg_sbc = sum(sbc_ratios) / len(sbc_ratios)
        evidence["sbc_to_revenue_avg"] = round(avg_sbc, 4)
        if avg_sbc > 0.10:
            score -= 12
            evidence["sbc_signal"] = "excessive SBC (>10%)"
        elif avg_sbc > 0.05:
            score -= 6
            evidence["sbc_signal"] = "elevated SBC (>5%)"
        elif avg_sbc > 0.03:
            score -= 2
            evidence["sbc_signal"] = "moderate SBC (>3%)"
        else:
            evidence["sbc_signal"] = "low SBC"
    else:
        evidence["sbc_signal"] = "missing"

    # ── Filing regularity ─────────────────────────────────────────────────────
    recent_filing_types = {f.get("filing_type") for f in filings}
    evidence["recent_filing_types"] = sorted(t for t in recent_filing_types if t)
    if "10-K" in recent_filing_types or "20-F" in recent_filing_types:
        score += 10
        evidence["filing_signal"] = "annual report filed"
    elif filings:
        score += 3
        evidence["filing_signal"] = "some filings present"
    else:
        score -= 10
        evidence["filing_signal"] = "no filings detected"

    return _clamp(score), evidence


# ── Weight loading ────────────────────────────────────────────────────────────


def _load_qualitative_weights(
    weights_override: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Return normalised dimension weights, optionally overriding config values.

    The returned dict always sums to exactly 1.0.

    Parameters
    ----------
    weights_override:
        When provided, uses these values instead of loading from YAML.
        Useful for testing.  Expected keys: moat, management, risks, governance.

    Raises
    ------
    ValueError
        If any weight is negative or the total is not positive.
    """
    if weights_override is not None:
        raw = {
            "moat": float(weights_override.get("moat", 0.35)),
            "management": float(weights_override.get("management", 0.25)),
            "risks": float(weights_override.get("risks", 0.25)),
            "governance": float(weights_override.get("governance", 0.15)),
        }
    else:
        config = load_scoring_weights()
        qw = config.get("qualitative_weights", {})
        raw = {
            "moat": float(qw.get("moat", 0.35)),
            "management": float(qw.get("management", 0.25)),
            "risks": float(qw.get("risks", 0.25)),
            "governance": float(qw.get("governance", 0.15)),
        }
    if any(v < 0 for v in raw.values()):
        raise ValueError(
            f"Qualitative weights must be non-negative; got {raw}"
        )
    total = sum(raw.values())
    if total <= 0:
        raise ValueError(
            f"Qualitative weights must have a positive sum; got {raw}"
        )
    return {k: v / total for k, v in raw.items()}


# ── Statement selection ─────────────────────────────────────────────────────


def _select_annual_statements(all_stmts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter, sort, and deduplicate annual statements.

    Mirrors Phase 3's deterministic selection strategy:

    1. Keep only rows with ``fiscal_period`` in ``{"FY", "annual"}``.
    2. Sort by five descending keys for deterministic restatement preference:
       fiscal_year → period_end_date → restated_flag → created_at → id.
    3. Deduplicate on ``(fiscal_year, fiscal_period)`` — first row wins, which
       is the most authoritative version for each reporting period.
    """
    annual_raw = [s for s in all_stmts if s.get("fiscal_period") in ("FY", "annual")]

    def _sort_key(s: dict[str, Any]) -> tuple:
        return (
            s.get("fiscal_year") or 0,
            s.get("period_end_date") or "",
            bool(s.get("restated_flag")),
            s.get("created_at") or "",
            s.get("id") or "",
        )

    annual_raw.sort(key=_sort_key, reverse=True)
    seen: set[tuple] = set()
    result: list[dict[str, Any]] = []
    for s in annual_raw:
        key = (s.get("fiscal_year") or 0, s.get("fiscal_period") or "")
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result


# ── Public API ────────────────────────────────────────────────────────────────


def compute_qualitative_score(
    company_id: str,
    repo_module: Any,
    score_date: str,
    *,
    weights: dict[str, float] | None = None,
    human_override: float = 0,
    override_reason: str | None = None,
    evidence_notes: str | None = None,
) -> dict[str, Any] | None:
    """Compute qualitative scores for one company on *score_date*.

    Reads from ``ratios_factors``, ``statements_norm``, and ``filings_index``
    via *repo_module*.  All reads are point-in-time safe: only rows with dates
    ≤ *score_date* are considered.

    Parameters
    ----------
    company_id:
        UUID of the company row in Supabase.
    repo_module:
        Object exposing ``get_ratios_for_company``,
        ``get_statements_for_company``, and ``get_filings_for_company``.
        In production this is the ``repositories`` module; in tests it is a
        fake.
    score_date:
        ISO date string (``YYYY-MM-DD``) used both as the ``score_date`` stamp
        and as the upper-bound ceiling for all data reads.
    weights:
        Optional dict overriding ``qualitative_weights`` from
        ``scoring_weights.yml``.  Keys: ``moat``, ``management``, ``risks``,
        ``governance``.
    human_override:
        Numeric adjustment added to the weighted auto-score, clamped to
        [-10, +10] before application.  Defaults to 0.
    override_reason:
        Free-text explanation for the override (persisted as-is).
    evidence_notes:
        Free-text analyst notes stored alongside the row.

    Returns
    -------
    dict or None
        A ``qualitative_scores``-shaped dict, or ``None`` when no data is
        available (ratios, statements, *and* filings are all empty).
    """
    ratio_rows: list[dict[str, Any]] = repo_module.get_ratios_for_company(
        company_id, as_of_date=score_date, limit=3
    )
    all_stmts: list[dict[str, Any]] = repo_module.get_statements_for_company(
        company_id, as_of_date=score_date, limit=10
    )
    filings: list[dict[str, Any]] = repo_module.get_filings_for_company(
        company_id, as_of_date=score_date
    )

    # Deduplicate and sort annual statements (newest, restated-preferred first).
    annual_stmts: list[dict[str, Any]] = _select_annual_statements(all_stmts)

    # Require at least one of: ratios, annual statements, or filings.
    if not ratio_rows and not annual_stmts and not filings:
        return None

    latest_ratios: dict[str, Any] = ratio_rows[0] if ratio_rows else {}

    # ── Per-dimension scoring ─────────────────────────────────────────────────
    dim_weights = _load_qualitative_weights(weights)
    if ratio_rows or annual_stmts:
        moat_s, moat_ev = _score_moat(latest_ratios, annual_stmts)
        mgmt_s, mgmt_ev = _score_management(latest_ratios, annual_stmts)
        risk_s, risk_ev = _score_risk(latest_ratios, annual_stmts)
    else:
        # Filing-only path: return neutral baselines for dimensions that
        # require statements or ratios; governance can be scored from filings.
        moat_s, moat_ev = 50.0, {"note": "no data — filing-only path"}
        mgmt_s, mgmt_ev = 50.0, {"note": "no data — filing-only path"}
        risk_s, risk_ev = 50.0, {"note": "no data — filing-only path"}
    gov_s, gov_ev = _score_governance(annual_stmts, filings)

    # Weighted auto-score using normalised weights (dim_weights already sums to 1).
    weighted_auto = (
        dim_weights["moat"] * moat_s
        + dim_weights["management"] * mgmt_s
        + dim_weights["risks"] * risk_s
        + dim_weights["governance"] * gov_s
    )

    # Apply human override (clamped to [-10, +10]) and clamp final to [0, 100].
    clamped_override = _clamp(float(human_override or 0), -10.0, 10.0)
    final = _clamp(weighted_auto + clamped_override)

    auto_score: dict[str, Any] = {
        "moat": {"score": round(moat_s, 2), "evidence": moat_ev},
        "management": {"score": round(mgmt_s, 2), "evidence": mgmt_ev},
        "risk": {"score": round(risk_s, 2), "evidence": risk_ev},
        "governance": {"score": round(gov_s, 2), "evidence": gov_ev},
        "weights": {k: round(v, 4) for k, v in dim_weights.items()},
        "weights_source": "scoring_weights.yml" if weights is None else "override",
    }

    return {
        "company_id": company_id,
        "score_date": score_date,
        "moat_score": round(moat_s, 2),
        "management_score": round(mgmt_s, 2),
        "risk_score": round(risk_s, 2),
        "governance_score": round(gov_s, 2),
        "final_quality_score": round(final, 2),
        "auto_score": auto_score,
        "human_override": clamped_override,
        "override_reason": override_reason,
        "evidence_notes": evidence_notes,
        "model_version": MODEL_VERSION,
    }
