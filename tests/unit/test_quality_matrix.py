from __future__ import annotations

from investment_app.quality_matrix import (
    SEVERITY_BLOCKS_BOTH,
    SEVERITY_BLOCKS_VALUATION,
    SEVERITY_CONFIDENCE_LIMITED,
    SEVERITY_INFORMATIONAL,
    build_quality_matrix_summary,
    classify_quality_code,
)


def test_quality_matrix_classifies_hard_readiness_blockers() -> None:
    missing_price = classify_quality_code(
        "missing_price",
        source="readiness_reason",
    )
    stale_fundamentals = classify_quality_code(
        "stale_fundamentals",
        source="readiness_reason",
    )

    assert missing_price.severity == SEVERITY_BLOCKS_BOTH
    assert missing_price.blocking_domains == ("valuation", "signal")
    assert stale_fundamentals.severity == SEVERITY_BLOCKS_BOTH


def test_quality_matrix_keeps_partial_history_as_confidence_limiter() -> None:
    classification = classify_quality_code(
        "missing_min_statement_history",
        source="readiness_reason",
    )

    assert classification.severity == SEVERITY_CONFIDENCE_LIMITED
    assert classification.blocking_domains == ()


def test_quality_matrix_resolves_provider_limited_from_gate_context() -> None:
    generic = classify_quality_code(
        "provider_limited",
        source="readiness_reason",
    )
    blocked = classify_quality_code(
        "provider_limited",
        source="readiness_reason",
        context={"can_run_valuation": False, "can_run_signal": False},
    )

    assert generic.severity == SEVERITY_CONFIDENCE_LIMITED
    assert generic.requires_context is True
    assert blocked.severity == SEVERITY_BLOCKS_BOTH
    assert blocked.blocking_domains == ("valuation", "signal")


def test_quality_matrix_classifies_scale_and_share_anomalies_as_valuation_blocks() -> None:
    price_scale = classify_quality_code(
        "price_scale_anomaly",
        source="valuation_sanity_reason",
    )
    share_units = classify_quality_code(
        "share_count_unit_anomaly",
        source="valuation_sanity_reason",
    )

    assert price_scale.severity == SEVERITY_BLOCKS_VALUATION
    assert price_scale.blocking_domains == ("valuation",)
    assert share_units.severity == SEVERITY_BLOCKS_VALUATION


def test_quality_matrix_keeps_risk_red_flags_informational() -> None:
    classification = classify_quality_code(
        "high_leverage",
        source="signal_red_flag",
    )

    assert classification.severity == SEVERITY_INFORMATIONAL
    assert classification.blocking_domains == ()


def test_quality_matrix_summary_aggregates_blocking_domains_and_codes() -> None:
    summary = build_quality_matrix_summary(
        readiness_status="analysis_ready",
        readiness_reason_codes=[],
        data_quality_warning_codes=["price_not_comparable"],
        valuation_sanity_status="unreliable",
        valuation_sanity_reason_codes=["price_scale_anomaly"],
        signal_confidence_limiter_codes=["valuation_unreliable"],
        signal_red_flags=["weak_quality"],
        can_run_valuation=True,
        can_run_signal=True,
    )

    assert summary["max_severity"] == SEVERITY_BLOCKS_VALUATION
    assert summary["blocking_domains"] == ["valuation"]
    assert summary["confidence_limited"] is True
    assert summary["codes_by_severity"][SEVERITY_BLOCKS_VALUATION] == [
        "valuation_sanity_reason:price_scale_anomaly",
        "valuation_sanity_status:unreliable",
    ]
    assert "data_quality_warning:price_not_comparable" in summary[
        "codes_by_severity"
    ][SEVERITY_CONFIDENCE_LIMITED]
