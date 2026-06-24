"""Deterministic severity classification for audit diagnostics.

This module is intentionally pure: it classifies already-produced reason,
warning, and diagnostic codes, but it does not alter readiness, valuation, or
signal decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


SEVERITY_INFORMATIONAL = "informational"
SEVERITY_CONFIDENCE_LIMITED = "confidence_limited"
SEVERITY_BLOCKS_VALUATION = "blocks_valuation"
SEVERITY_BLOCKS_SIGNAL = "blocks_signal"
SEVERITY_BLOCKS_BOTH = "blocks_both"

SEVERITIES = (
    SEVERITY_INFORMATIONAL,
    SEVERITY_CONFIDENCE_LIMITED,
    SEVERITY_BLOCKS_VALUATION,
    SEVERITY_BLOCKS_SIGNAL,
    SEVERITY_BLOCKS_BOTH,
)

_SEVERITY_RANK = {
    SEVERITY_INFORMATIONAL: 0,
    SEVERITY_CONFIDENCE_LIMITED: 1,
    SEVERITY_BLOCKS_VALUATION: 2,
    SEVERITY_BLOCKS_SIGNAL: 2,
    SEVERITY_BLOCKS_BOTH: 3,
}

_BLOCKING_DOMAINS = {
    SEVERITY_BLOCKS_VALUATION: ("valuation",),
    SEVERITY_BLOCKS_SIGNAL: ("signal",),
    SEVERITY_BLOCKS_BOTH: ("valuation", "signal"),
}


@dataclass(frozen=True)
class QualityClassification:
    source: str
    code: str
    severity: str
    blocking_domains: tuple[str, ...] = ()
    requires_context: bool = False
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "source": self.source,
            "code": self.code,
            "severity": self.severity,
            "blocking_domains": list(self.blocking_domains),
        }
        if self.requires_context:
            row["requires_context"] = True
        if self.note:
            row["note"] = self.note
        return row


_DATA_QUALITY_CODES = {
    "price_divergence_warning": SEVERITY_CONFIDENCE_LIMITED,
    "price_divergence_critical": SEVERITY_CONFIDENCE_LIMITED,
    "price_not_comparable": SEVERITY_CONFIDENCE_LIMITED,
    "no_statements_available": SEVERITY_BLOCKS_BOTH,
    "incomplete_statement_set": SEVERITY_CONFIDENCE_LIMITED,
    "missing_key_fields": SEVERITY_CONFIDENCE_LIMITED,
    "insufficient_period_coverage": SEVERITY_CONFIDENCE_LIMITED,
    "fundamentals_provider_overlap_missing": SEVERITY_INFORMATIONAL,
    "fundamentals_provider_discrepancy": SEVERITY_CONFIDENCE_LIMITED,
}

_READINESS_CODES = {
    "missing_price": SEVERITY_BLOCKS_BOTH,
    "missing_supported_fundamentals_path": SEVERITY_BLOCKS_BOTH,
    "non_us_fundamentals_not_supported": SEVERITY_BLOCKS_BOTH,
    "missing_min_statement_history": SEVERITY_CONFIDENCE_LIMITED,
    "missing_diluted_shares": SEVERITY_BLOCKS_VALUATION,
    "missing_fcf_path": SEVERITY_BLOCKS_VALUATION,
    "non_viable_fcf": SEVERITY_BLOCKS_VALUATION,
    "valuation_blocked": SEVERITY_BLOCKS_VALUATION,
    "unsupported_instrument": SEVERITY_BLOCKS_BOTH,
    "valuation_partial": SEVERITY_CONFIDENCE_LIMITED,
    "valuation_ready": SEVERITY_INFORMATIONAL,
    "stale_fundamentals": SEVERITY_BLOCKS_BOTH,
}

_READINESS_STATUS_CODES = {
    "analysis_ready": SEVERITY_INFORMATIONAL,
    "partial_analysis": SEVERITY_CONFIDENCE_LIMITED,
    "provider_limited": SEVERITY_CONFIDENCE_LIMITED,
    "unsupported_for_analysis": SEVERITY_BLOCKS_BOTH,
    "tracking_only": SEVERITY_BLOCKS_BOTH,
}

_VALUATION_STATUS_CODES = {
    "usable": SEVERITY_INFORMATIONAL,
    "high_uncertainty": SEVERITY_CONFIDENCE_LIMITED,
    "unreliable": SEVERITY_BLOCKS_VALUATION,
    "model_failure": SEVERITY_BLOCKS_VALUATION,
}

_VALUATION_BLOCKERS = {
    "missing_statements",
    "missing_shares_outstanding",
    "missing_latest_price",
    "missing_ratio_factor_history",
    "invalid_terminal_growth_gte_discount_rate",
    "negative_direct_fcf",
    "zero_direct_fcf",
    "missing_fcf",
    "missing_finite_percentiles",
    "non_monotonic_percentiles",
    "no_usable_distribution",
    "no_usable_method",
    "missing_dcf_and_multiples",
    "terminal_spread_too_narrow",
    "negative_or_zero_fcf_path",
    "price_scale_anomaly",
    "price_provider_scale_mismatch",
    "share_count_unit_anomaly",
    "share_count_market_cap_mismatch",
    "severe_intrinsic_value_span",
    "severe_distribution_span_ratio",
    "severe_dcf_multiples_divergence",
    "severe_terminal_value_dominance",
    "severe_midpoint_price_implausibility",
}

_VALUATION_LIMITERS = {
    "limited_statement_history",
    "margin_of_safety_unavailable",
    "multiples_unavailable",
    "dcf_unavailable",
    "dcf_uses_synthetic_fcff",
    "stale_ratio_history",
    "distribution_collapsed",
    "missing_dcf_component",
    "missing_multiples_component",
    "sparse_scenario_count",
    "extreme_uncertainty",
    "wide_intrinsic_value_span",
    "wide_distribution_span_ratio",
    "dcf_multiples_divergence",
    "terminal_value_dominance",
    "terminal_spread_narrow",
    "missing_current_price_for_relative_checks",
    "midpoint_price_implausibility",
}

_SIGNAL_LIMITERS = {
    "partial_analysis": SEVERITY_CONFIDENCE_LIMITED,
    "freshness_limited": SEVERITY_CONFIDENCE_LIMITED,
    "freshness_stale": SEVERITY_CONFIDENCE_LIMITED,
    "freshness_missing_inputs": SEVERITY_CONFIDENCE_LIMITED,
    "valuation_high_uncertainty": SEVERITY_CONFIDENCE_LIMITED,
    "valuation_unreliable": SEVERITY_CONFIDENCE_LIMITED,
    "valuation_missing": SEVERITY_CONFIDENCE_LIMITED,
    "valuation_not_used_in_signal": SEVERITY_CONFIDENCE_LIMITED,
    "missing_qualitative_score": SEVERITY_CONFIDENCE_LIMITED,
    "missing_ratio_factors": SEVERITY_CONFIDENCE_LIMITED,
}

_SIGNAL_RED_FLAGS = {
    "missing_valuation": SEVERITY_CONFIDENCE_LIMITED,
    "valuation_unreliable": SEVERITY_CONFIDENCE_LIMITED,
    "negative_margin_of_safety": SEVERITY_INFORMATIONAL,
    "overvalued_vs_iv_p75": SEVERITY_INFORMATIONAL,
    "negative_direct_fcf": SEVERITY_CONFIDENCE_LIMITED,
    "zero_direct_fcf": SEVERITY_CONFIDENCE_LIMITED,
    "missing_qualitative_score": SEVERITY_CONFIDENCE_LIMITED,
    "quality_breakdown": SEVERITY_INFORMATIONAL,
    "weak_quality": SEVERITY_INFORMATIONAL,
    "high_leverage": SEVERITY_INFORMATIONAL,
    "critical_interest_coverage": SEVERITY_INFORMATIONAL,
    "negative_news_spike": SEVERITY_INFORMATIONAL,
    "missing_ratio_factors": SEVERITY_CONFIDENCE_LIMITED,
    "freshness_stale": SEVERITY_CONFIDENCE_LIMITED,
    "freshness_missing_inputs": SEVERITY_CONFIDENCE_LIMITED,
}


def _blocking_domains(severity: str) -> tuple[str, ...]:
    return _BLOCKING_DOMAINS.get(severity, ())


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


def _provider_limited_classification(
    *,
    source: str,
    context: dict[str, Any] | None,
) -> QualityClassification:
    context = context or {}
    can_run_valuation = _as_bool(context.get("can_run_valuation"))
    can_run_signal = _as_bool(context.get("can_run_signal"))

    if can_run_valuation is False and can_run_signal is False:
        severity = SEVERITY_BLOCKS_BOTH
        note = "provider_limited resolved from current readiness gates"
    elif can_run_valuation is False:
        severity = SEVERITY_BLOCKS_VALUATION
        note = "provider_limited resolved from current valuation gate"
    elif can_run_signal is False:
        severity = SEVERITY_BLOCKS_SIGNAL
        note = "provider_limited resolved from current signal gate"
    else:
        severity = SEVERITY_CONFIDENCE_LIMITED
        note = "provider_limited is context-sensitive"

    return QualityClassification(
        source=source,
        code="provider_limited",
        severity=severity,
        blocking_domains=_blocking_domains(severity),
        requires_context=True,
        note=note,
    )


def classify_quality_code(
    code: str,
    *,
    source: str,
    context: dict[str, Any] | None = None,
) -> QualityClassification:
    """Classify a single diagnostic code into an audit severity category."""

    normalized = str(code).strip()
    if not normalized:
        return QualityClassification(
            source=source,
            code=normalized,
            severity=SEVERITY_INFORMATIONAL,
            note="empty code",
        )

    if normalized == "provider_limited" and source in {
        "readiness_reason",
        "readiness_status",
    }:
        return _provider_limited_classification(source=source, context=context)

    severity: str
    if source == "data_quality_warning":
        severity = _DATA_QUALITY_CODES.get(normalized, SEVERITY_CONFIDENCE_LIMITED)
    elif source == "readiness_reason":
        severity = _READINESS_CODES.get(normalized, SEVERITY_CONFIDENCE_LIMITED)
    elif source == "readiness_status":
        severity = _READINESS_STATUS_CODES.get(normalized, SEVERITY_CONFIDENCE_LIMITED)
    elif source == "valuation_sanity_status":
        severity = _VALUATION_STATUS_CODES.get(normalized, SEVERITY_CONFIDENCE_LIMITED)
    elif source in {
        "valuation_sanity_reason",
        "valuation_blocker",
        "valuation_warning",
        "ratio_history_reason",
    }:
        if normalized in _VALUATION_BLOCKERS:
            severity = SEVERITY_BLOCKS_VALUATION
        elif normalized in _VALUATION_LIMITERS:
            severity = SEVERITY_CONFIDENCE_LIMITED
        else:
            severity = SEVERITY_CONFIDENCE_LIMITED
    elif source == "signal_confidence_limiter":
        severity = _SIGNAL_LIMITERS.get(normalized, SEVERITY_CONFIDENCE_LIMITED)
    elif source == "signal_red_flag":
        severity = _SIGNAL_RED_FLAGS.get(normalized, SEVERITY_INFORMATIONAL)
    else:
        severity = SEVERITY_CONFIDENCE_LIMITED

    return QualityClassification(
        source=source,
        code=normalized,
        severity=severity,
        blocking_domains=_blocking_domains(severity),
    )


def _classify_many(
    codes: Iterable[Any] | None,
    *,
    source: str,
    context: dict[str, Any],
) -> list[QualityClassification]:
    return [
        classify_quality_code(str(code), source=source, context=context)
        for code in (codes or [])
        if code is not None and str(code).strip()
    ]


def build_quality_matrix_summary(
    *,
    data_quality_warning_codes: Iterable[Any] | None = None,
    readiness_status: str | None = None,
    readiness_reason_codes: Iterable[Any] | None = None,
    valuation_sanity_status: str | None = None,
    valuation_sanity_reason_codes: Iterable[Any] | None = None,
    valuation_blockers: Iterable[Any] | None = None,
    valuation_warnings: Iterable[Any] | None = None,
    ratio_history_reason_codes: Iterable[Any] | None = None,
    signal_confidence_limiter_codes: Iterable[Any] | None = None,
    signal_red_flags: Iterable[Any] | None = None,
    can_run_valuation: bool | str | None = None,
    can_run_signal: bool | str | None = None,
    limiting_domain: str | None = None,
) -> dict[str, Any]:
    """Aggregate diagnostics into audit-friendly severity metadata."""

    context = {
        "can_run_valuation": can_run_valuation,
        "can_run_signal": can_run_signal,
        "limiting_domain": limiting_domain,
        "readiness_status": readiness_status,
    }
    entries: list[QualityClassification] = []

    if readiness_status:
        entries.append(
            classify_quality_code(
                readiness_status,
                source="readiness_status",
                context=context,
            )
        )

    if valuation_sanity_status:
        entries.append(
            classify_quality_code(
                valuation_sanity_status,
                source="valuation_sanity_status",
                context=context,
            )
        )

    entries.extend(
        _classify_many(
            data_quality_warning_codes,
            source="data_quality_warning",
            context=context,
        )
    )
    entries.extend(
        _classify_many(
            readiness_reason_codes,
            source="readiness_reason",
            context=context,
        )
    )
    entries.extend(
        _classify_many(
            valuation_sanity_reason_codes,
            source="valuation_sanity_reason",
            context=context,
        )
    )
    entries.extend(
        _classify_many(valuation_blockers, source="valuation_blocker", context=context)
    )
    entries.extend(
        _classify_many(valuation_warnings, source="valuation_warning", context=context)
    )
    entries.extend(
        _classify_many(
            ratio_history_reason_codes,
            source="ratio_history_reason",
            context=context,
        )
    )
    entries.extend(
        _classify_many(
            signal_confidence_limiter_codes,
            source="signal_confidence_limiter",
            context=context,
        )
    )
    entries.extend(
        _classify_many(signal_red_flags, source="signal_red_flag", context=context)
    )

    codes_by_severity = {severity: [] for severity in SEVERITIES}
    blocking_domains: set[str] = set()
    max_severity = SEVERITY_INFORMATIONAL

    for entry in entries:
        codes_by_severity[entry.severity].append(f"{entry.source}:{entry.code}")
        blocking_domains.update(entry.blocking_domains)
        if _SEVERITY_RANK[entry.severity] > _SEVERITY_RANK[max_severity]:
            max_severity = entry.severity

    return {
        "max_severity": max_severity,
        "blocking_domains": sorted(blocking_domains),
        "confidence_limited": any(
            entry.severity == SEVERITY_CONFIDENCE_LIMITED for entry in entries
        ),
        "codes_by_severity": {
            severity: sorted(codes)
            for severity, codes in codes_by_severity.items()
            if codes
        },
        "entries": [entry.as_dict() for entry in entries],
    }
