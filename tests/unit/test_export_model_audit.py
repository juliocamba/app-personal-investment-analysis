from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import export_model_audit as audit


class _FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, client: "_FakeClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._select_columns = "*"
        self._company_ids: list[str] | None = None
        self._order_by: list[tuple[str, bool]] = []

    def select(self, columns: str) -> "_FakeQuery":
        self._select_columns = columns
        return self

    def in_(self, field: str, values: list[str]) -> "_FakeQuery":
        assert field == "company_id"
        self._company_ids = list(values)
        return self

    def order(self, column_name: str, desc: bool = False) -> "_FakeQuery":
        self._order_by.append((column_name, desc))
        return self

    def execute(self) -> _FakeResponse:
        self._client.calls.append(
            {
                "table": self._table_name,
                "select_columns": self._select_columns,
                "company_ids": self._company_ids,
                "order_by": list(self._order_by),
            }
        )
        rows = list(self._client.tables.get(self._table_name, []))
        if self._company_ids is not None:
            rows = [row for row in rows if row.get("company_id") in self._company_ids]
        return _FakeResponse(rows)


class _FakeClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.calls: list[dict[str, Any]] = []

    def table(self, table_name: str) -> _FakeQuery:
        return _FakeQuery(self, table_name)


_BASE_FIELD_ORDER = [
    "company_id",
    "ticker",
    "company_name",
    "sector",
    "industry",
    "latest_price",
    "price_date",
    "price_provider",
    "readiness_status",
    "provider_mix",
    "readiness_reason_codes",
    "can_run_valuation",
    "can_run_signal",
    "limiting_domain",
    "readiness_updated_at",
    "data_quality_status",
    "data_quality_warning_codes",
    "price_validation_status",
    "statement_completeness_status",
    "statement_completeness_summary",
    "fundamentals_provider_comparison_status",
    "fundamentals_provider_comparison_summary",
    "data_quality_details_json",
    "statement_source",
    "fiscal_year",
    "fiscal_period",
    "latest_statement_date",
    "revenue",
    "gross_profit",
    "operating_income",
    "ebit",
    "ebitda",
    "net_income",
    "cfo",
    "capex",
    "free_cash_flow",
    "depreciation_amortization",
    "cash_and_equivalents",
    "total_debt",
    "total_equity",
    "diluted_shares",
    "factor_date",
    "roic",
    "roe",
    "fcf_yield",
    "net_debt_to_ebitda",
    "interest_coverage",
    "ev_to_ebitda",
    "price_to_sales",
    "price_to_book",
    "news_sentiment_7d",
    "ratio_data_quality_score",
    "valuation_run_id",
    "valuation_date",
    "valuation_model_version",
    "valuation_currency",
    "valuation_current_price",
    "iv_p10",
    "iv_p25",
    "iv_p50",
    "iv_p75",
    "iv_p90",
    "margin_of_safety_conservative",
    "uncertainty_width",
    "valuation_assumptions_json",
    "mos_basis",
    "scenario_count",
    "uncertainty_category",
    "distribution_collapsed",
    "valuation_status",
    "qualitative_score_id",
    "qualitative_score_date",
    "qualitative_model_version",
    "final_quality_score",
    "signal_run_id",
    "signal_date",
    "signal_model_version",
    "stored_final_signal",
    "p_buy",
    "p_buy_adjusted",
    "p_sell",
    "final_signal",
    "uncertainty_penalty",
    "red_flags",
    "top_feature_contributors",
    "explanation",
    "freshness_flag",
]

_DERIVED_FIELD_ORDER = [
    "price_to_iv_mid",
    "price_to_iv_high",
    "valuation_bucket",
    "strong_sell_confirmation_type",
    "hold_uncertainty_constrained",
    "stale_input_blocked",
    "valuation_sanity_status",
    "valuation_sanity_reason_codes",
    "valuation_evidence_usable",
    "valuation_display_suppressed",
    "valuation_signal_influence_blocked",
    "valuation_method_coverage",
    "iv_range_ratio_p90_p10",
    "distribution_span_ratio_diagnostics",
    "dcf_multiples_gap_ratio",
    "max_terminal_value_share",
    "terminal_spread",
    "midpoint_price_ratio",
    "ratio_history_status",
    "ratio_history_reason_codes",
    "ratio_rows_available",
    "ratio_rows_used",
    "ratio_rows_excluded",
    "price_provider_diagnostics",
    "implied_market_cap_from_price_shares",
    "price_to_sales_implied",
    "price_to_book_implied",
    "price_to_earnings_implied",
    "market_cap_to_fcf",
    "dcf_price_ratio",
    "market_cap_share_mismatch_ratio",
    "price_row_share_mismatch_ratio",
    "price_scale_anomaly",
    "price_provider_scale_mismatch",
    "share_count_unit_anomaly",
    "share_count_market_cap_mismatch",
    "statement_age_days",
    "latest_statement_year",
    "stale_statement_input",
    "has_dcf_component",
    "valuation_partial_flag",
    "multiples_vs_dcf_mid_gap",
    "dominant_signal_driver",
    "hold_reason",
    "valuation_used_in_signal",
    "risk_override_applied",
    "confidence_limiter_codes",
    "strong_sell_basis",
    "buy_conviction_limited",
    "explanation_quality_warning",
    "recommendation_language_warning",
    "probability_interpretation_note",
    "signal_display_state",
    "distribution_min",
    "distribution_max",
    "distribution_span_ratio",
]


def _live_export_field_order() -> list[str]:
    return [*_BASE_FIELD_ORDER, *_DERIVED_FIELD_ORDER]


def _reasoning_contributors() -> list[dict[str, Any]]:
    return [
        {
            "name": "signal_reasoning_metadata",
            "kind": "metadata",
            "value": {
                "dominant_signal_driver": "valuation_upside",
                "hold_reason": None,
                "valuation_used_in_signal": True,
                "risk_override_applied": False,
                "confidence_limiter_codes": ["freshness_ok"],
                "strong_sell_basis": None,
                "buy_conviction_limited": False,
                "explanation_quality_warning": None,
                "recommendation_language_warning": None,
                "probability_interpretation_note": "Internal rule-based model scores; not calibrated probabilities or investment recommendations.",
            },
        }
    ]


def _base_tables() -> dict[str, list[dict[str, Any]]]:
    return {
        "latest_price_eod": [
            {"company_id": "c1", "price_date": "2026-06-12", "close": 100.0, "provider": "fmp"}
        ],
        "analysis_readiness_latest": [
            {
                "company_id": "c1",
                "readiness_status": "analysis_ready",
                "provider_mix": "primary_only",
                "readiness_reason_codes": ["valuation_ready"],
                "can_run_valuation": True,
                "can_run_signal": True,
                "limiting_domain": None,
                "readiness_updated_at": "2026-06-12T00:00:00+00:00",
            }
        ],
        "latest_company_data_quality_snapshots": [
            {
                "company_id": "c1",
                "snapshot_date": "2026-06-12",
                "data_quality_status": "healthy",
                "data_quality_warning_codes": [],
                "price_validation_status": "ok",
                "statement_completeness_status": "ok",
                "statement_completeness_summary": "Complete",
                "fundamentals_provider_comparison_status": "ok",
                "fundamentals_provider_comparison_summary": "Aligned",
            }
        ],
        "company_data_quality_snapshots": [
            {
                "company_id": "c1",
                "snapshot_date": "2026-06-12",
                "details": {"statement_completeness": {"status": "ok", "source": "latest"}},
            },
            {
                "company_id": "c1",
                "snapshot_date": "2026-06-11",
                "details": {"statement_completeness": {"status": "warning", "source": "older"}},
            },
        ],
        "statements_norm": [
            {
                "company_id": "c1",
                "source": "fmp",
                "fiscal_year": 2025,
                "fiscal_period": "annual",
                "period_end_date": "2025-12-31",
                "revenue": 1000.0,
                "gross_profit": 500.0,
                "operating_income": 200.0,
                "ebit": 190.0,
                "ebitda": 220.0,
                "net_income": 150.0,
                "cfo": 210.0,
                "capex": -50.0,
                "free_cash_flow": 160.0,
                "depreciation_amortization": 30.0,
                "cash_and_equivalents": 100.0,
                "total_debt": 80.0,
                "total_equity": 300.0,
                "diluted_shares": 10.0,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "company_id": "c1",
                "source": "fmp",
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
        ],
        "latest_ratios_factors": [
            {
                "company_id": "c1",
                "factor_date": "2026-06-12",
                "roic": 0.3,
                "roe": 0.25,
                "fcf_yield": 0.05,
                "net_debt_to_ebitda": 1.2,
                "interest_coverage": 8.0,
                "ev_to_ebitda": 10.0,
                "price_to_sales": 3.0,
                "price_to_book": 2.0,
                "news_sentiment_7d": 0.1,
                "data_quality_score": 100.0,
            }
        ],
        "latest_valuation_runs": [
            {
                "company_id": "c1",
                "id": "val-1",
                "valuation_date": "2026-06-12",
                "model_version": "valuation_v1",
                "currency": "USD",
                "current_price": 100.0,
                "iv_p10": 80.0,
                "iv_p25": 90.0,
                "iv_p50": 110.0,
                "iv_p75": 130.0,
                "iv_p90": 150.0,
                "margin_of_safety_conservative": 0.2,
                "uncertainty_width": 0.4,
                "assumptions": {
                    "dcf": {"base_iv": 100.0},
                    "multiples": {"blended_value": 120.0},
                    "aggregation": {"distribution": [{"value": 80.0}, {"value": 110.0}, {"value": 150.0}]},
                    "diagnostics": {
                        "mos_basis": "iv_p10",
                        "scenario_count": 2,
                        "uncertainty_category": "moderate",
                        "warnings": [],
                        "valuation_status": "partial",
                        "valuation_sanity_status": "high_uncertainty",
                        "valuation_sanity_reason_codes": ["sparse_scenario_count"],
                        "valuation_evidence_usable": True,
                        "valuation_display_suppressed": False,
                        "valuation_signal_influence_blocked": False,
                        "valuation_method_coverage": "dcf_only",
                        "iv_range_ratio_p90_p10": 1.875,
                        "distribution_span_ratio": 1.875,
                        "dcf_multiples_gap_ratio": 1.2,
                        "max_terminal_value_share": 0.85,
                        "terminal_spread": 0.03,
                        "midpoint_price_ratio": 1.1,
                    },
                },
            }
        ],
        "latest_qualitative_scores": [
            {"company_id": "c1", "id": "qual-1", "score_date": "2026-06-12", "model_version": "quality_v1", "final_quality_score": 78.0}
        ],
        "latest_signal_runs": [
            {
                "company_id": "c1",
                "id": "sig-1",
                "signal_date": "2026-06-12",
                "model_version": "signal_rule_v3",
                "p_buy": 0.65,
                "p_buy_adjusted": 0.62,
                "p_sell": 0.18,
                "final_signal": "buy",
                "uncertainty_penalty": 0.1,
                "red_flags": ["weak_quality"],
                "top_feature_contributors": _reasoning_contributors(),
                "explanation": "Buy - supportive internal model score 0.62 with no disqualifying red flags.",
                "freshness_flag": "ok",
            }
        ],
    }


def _tracking_tables(*, signal_row: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {
        "latest_price_eod": [
            {"company_id": "c2", "price_date": "2026-06-12", "close": 100.0, "provider": "fmp"}
        ],
        "analysis_readiness_latest": [
            {
                "company_id": "c2",
                "readiness_status": "tracking_only",
                "provider_mix": "price_only",
                "readiness_reason_codes": ["provider_limited"],
                "can_run_valuation": False,
                "can_run_signal": False,
                "limiting_domain": "fundamentals",
                "readiness_updated_at": "2026-06-12T00:00:00+00:00",
            }
        ],
        "latest_company_data_quality_snapshots": [
            {
                "company_id": "c2",
                "snapshot_date": "2026-06-12",
                "data_quality_status": "healthy",
                "data_quality_warning_codes": [],
                "price_validation_status": "ok",
                "statement_completeness_status": "ok",
                "statement_completeness_summary": "Complete",
                "fundamentals_provider_comparison_status": "not_comparable",
                "fundamentals_provider_comparison_summary": "No overlap",
            }
        ],
        "company_data_quality_snapshots": [
            {"company_id": "c2", "snapshot_date": "2026-06-12", "details": {}},
        ],
        "statements_norm": [],
        "latest_ratios_factors": [],
        "latest_valuation_runs": [],
        "latest_qualitative_scores": [],
        "latest_signal_runs": ([signal_row] if signal_row is not None else []),
    }
    return tables


def _canonical_rows(monkeypatch: Any) -> list[dict[str, Any]]:
    monkeypatch.setattr(
        audit,
        "list_watchlist_active_companies",
        lambda client=None: [
            {
                "id": "c1",
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
            }
        ],
    )
    return audit._audit_export_rows(_FakeClient(_base_tables()), export_date=date(2026, 6, 12))


def test_live_statement_age_and_year_derivations() -> None:
    row = {
        "latest_statement_date": "2024-01-01",
        "signal_date": "2025-01-01",
        "valuation_date": None,
        "fiscal_year": 2023,
    }
    assert audit._statement_age_days(row, export_date=date(2025, 1, 15)) == 366
    assert audit._latest_statement_year(row) == 2023


def test_live_valuation_bucket_uses_signal_rule_v3_semantics() -> None:
    row = {
        "valuation_run_id": "val-1",
        "valuation_current_price": 130.0,
        "iv_p50": 100.0,
        "iv_p75": 120.0,
        "uncertainty_width": 0.30,
        "margin_of_safety_conservative": -0.10,
    }
    assert audit._valuation_position_bucket(audit._build_valuation_row(row)) == "severely_overvalued"


def test_live_build_derived_fields_preserves_false_for_missing_statement_age() -> None:
    row = {
        "latest_price": None,
        "iv_p50": None,
        "iv_p90": None,
        "valuation_run_id": None,
        "valuation_current_price": None,
        "uncertainty_width": None,
        "margin_of_safety_conservative": None,
        "final_signal": None,
        "red_flags": None,
        "scenario_count": 0,
        "valuation_assumptions_json": {},
        "latest_statement_date": None,
        "valuation_date": None,
        "signal_date": None,
        "fiscal_year": None,
    }
    derived = audit.build_derived_fields(row, export_date=date(2026, 6, 12))
    assert derived["statement_age_days"] is None
    assert derived["stale_statement_input"] is False
    assert derived["stale_input_blocked"] is False
    assert derived["dominant_signal_driver"] is None
    assert derived["probability_interpretation_note"] is None


def test_live_build_derived_fields_sets_stale_input_blocked_when_gate_active() -> None:
    row = {
        "latest_price": 120.0,
        "iv_p50": None,
        "iv_p90": None,
        "valuation_run_id": None,
        "valuation_current_price": None,
        "uncertainty_width": None,
        "margin_of_safety_conservative": None,
        "final_signal": None,
        "red_flags": [],
        "scenario_count": 0,
        "valuation_assumptions_json": {},
        "latest_statement_date": "2024-09-30",
        "valuation_date": "2026-03-25",
        "signal_date": "2026-03-25",
        "fiscal_year": 2024,
        "readiness_reason_codes": ["stale_fundamentals"],
        "can_run_valuation": False,
        "can_run_signal": False,
    }
    derived = audit.build_derived_fields(row, export_date=date(2026, 6, 12))
    assert derived["stale_input_blocked"] is True


def test_live_build_derived_fields_surfaces_valuation_sanity_fields() -> None:
    row = {
        "latest_price": 100.0,
        "iv_p50": 100.0,
        "iv_p90": 140.0,
        "valuation_run_id": "val-1",
        "valuation_current_price": 100.0,
        "iv_p75": 120.0,
        "uncertainty_width": 0.6,
        "margin_of_safety_conservative": 0.0,
        "final_signal": "hold",
        "red_flags": [],
        "scenario_count": 1,
        "valuation_assumptions_json": {
            "diagnostics": {
                "valuation_sanity_status": "high_uncertainty",
                "valuation_sanity_reason_codes": ["sparse_scenario_count"],
                "valuation_evidence_usable": True,
                "valuation_display_suppressed": False,
                "valuation_signal_influence_blocked": False,
                "valuation_method_coverage": "dcf_only",
                "iv_range_ratio_p90_p10": 3.2,
                "distribution_span_ratio": 3.2,
                "dcf_multiples_gap_ratio": None,
                "max_terminal_value_share": 0.9,
                "terminal_spread": 0.02,
                "midpoint_price_ratio": 1.0,
                "ratio_history_status": "filtered",
                "ratio_history_reason_codes": ["stale_ratio_history"],
                "ratio_rows_available": 12,
                "ratio_rows_used": 1,
                "ratio_rows_excluded": 11,
                "price_provider": "twelve_data",
                "implied_market_cap_from_price_shares": 1_183_241_272_500.0,
                "price_to_sales_implied": 31.7,
                "price_to_book_implied": 21.8,
                "price_to_earnings_implied": 138.6,
                "market_cap_to_fcf": 709.4,
                "dcf_price_ratio": 0.0619,
                "market_cap_share_mismatch_ratio": None,
                "price_row_share_mismatch_ratio": None,
                "price_scale_anomaly": True,
                "price_provider_scale_mismatch": True,
                "share_count_unit_anomaly": False,
                "share_count_market_cap_mismatch": False,
            }
        },
        "latest_statement_date": "2025-01-01",
        "valuation_date": "2026-01-02",
        "signal_date": "2026-01-02",
        "fiscal_year": 2025,
        "readiness_reason_codes": [],
        "can_run_valuation": True,
        "can_run_signal": True,
    }
    derived = audit.build_derived_fields(row, export_date=date(2026, 6, 12))
    assert derived["valuation_sanity_status"] == "high_uncertainty"
    assert derived["valuation_sanity_reason_codes"] == ["sparse_scenario_count"]
    assert derived["valuation_method_coverage"] == "dcf_only"
    assert derived["iv_range_ratio_p90_p10"] == 3.2
    assert derived["ratio_history_status"] == "filtered"
    assert derived["ratio_history_reason_codes"] == ["stale_ratio_history"]
    assert derived["ratio_rows_available"] == 12
    assert derived["ratio_rows_used"] == 1
    assert derived["ratio_rows_excluded"] == 11
    assert derived["price_provider_diagnostics"] == "twelve_data"
    assert derived["price_to_sales_implied"] == 31.7
    assert derived["price_to_book_implied"] == 21.8
    assert derived["price_scale_anomaly"] is True
    assert derived["price_provider_scale_mismatch"] is True
    assert derived["share_count_unit_anomaly"] is False


def test_live_build_derived_fields_extracts_signal_reasoning_metadata() -> None:
    row = {
        "latest_price": 100.0,
        "iv_p50": 110.0,
        "iv_p90": 140.0,
        "valuation_run_id": "val-1",
        "valuation_current_price": 100.0,
        "iv_p75": 120.0,
        "uncertainty_width": 0.4,
        "margin_of_safety_conservative": 0.1,
        "final_signal": "buy",
        "red_flags": [],
        "scenario_count": 1,
        "valuation_assumptions_json": {"diagnostics": {}},
        "latest_statement_date": "2025-01-01",
        "valuation_date": "2026-01-02",
        "signal_date": "2026-01-02",
        "fiscal_year": 2025,
        "readiness_reason_codes": [],
        "can_run_valuation": True,
        "can_run_signal": True,
        "top_feature_contributors": _reasoning_contributors(),
    }
    derived = audit.build_derived_fields(row, export_date=date(2026, 6, 12))
    assert derived["dominant_signal_driver"] == "valuation_upside"
    assert derived["valuation_used_in_signal"] is True
    assert derived["confidence_limiter_codes"] == ["freshness_ok"]
    assert derived["probability_interpretation_note"].startswith("Internal rule-based model scores")
    assert derived["signal_display_state"] == "analytical_signal"


def test_live_build_derived_fields_marks_tracking_only_suppressed_hold() -> None:
    row = {
        "latest_price": 100.0,
        "iv_p50": None,
        "iv_p90": None,
        "valuation_run_id": None,
        "valuation_current_price": None,
        "iv_p75": None,
        "uncertainty_width": None,
        "margin_of_safety_conservative": None,
        "final_signal": None,
        "stored_final_signal": "hold",
        "red_flags": None,
        "scenario_count": 0,
        "valuation_assumptions_json": {},
        "latest_statement_date": None,
        "valuation_date": None,
        "signal_date": None,
        "fiscal_year": None,
        "readiness_reason_codes": ["provider_limited"],
        "can_run_valuation": False,
        "can_run_signal": False,
        "top_feature_contributors": None,
    }
    derived = audit.build_derived_fields(row, export_date=date(2026, 6, 12))
    assert derived["signal_display_state"] == "readiness_suppressed"


def test_live_build_derived_fields_marks_tracking_only_no_signal() -> None:
    row = {
        "latest_price": 100.0,
        "iv_p50": None,
        "iv_p90": None,
        "valuation_run_id": None,
        "valuation_current_price": None,
        "iv_p75": None,
        "uncertainty_width": None,
        "margin_of_safety_conservative": None,
        "final_signal": None,
        "stored_final_signal": None,
        "red_flags": None,
        "scenario_count": 0,
        "valuation_assumptions_json": {},
        "latest_statement_date": None,
        "valuation_date": None,
        "signal_date": None,
        "fiscal_year": None,
        "readiness_reason_codes": ["provider_limited"],
        "can_run_valuation": False,
        "can_run_signal": False,
        "top_feature_contributors": None,
    }
    derived = audit.build_derived_fields(row, export_date=date(2026, 6, 12))
    assert derived["signal_display_state"] == "no_signal"


def test_live_audit_export_rows_preserves_field_order_and_nested_shape(monkeypatch: Any) -> None:
    rows = _canonical_rows(monkeypatch)
    assert len(rows) == 1
    row = rows[0]
    assert list(row.keys()) == _live_export_field_order()
    assert row["stored_final_signal"] == "buy"
    assert row["signal_display_state"] == "analytical_signal"
    assert row["data_quality_details_json"]["statement_completeness"]["status"] == "ok"
    assert row["valuation_assumptions_json"]["diagnostics"]["valuation_sanity_status"] == "high_uncertainty"
    assert row["top_feature_contributors"][0]["name"] == "signal_reasoning_metadata"


def test_live_audit_export_rows_uses_latest_statement_and_diagnostics(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        audit,
        "list_watchlist_active_companies",
        lambda client=None: [{"id": "c1", "ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics"}],
    )
    client = _FakeClient(_base_tables())
    rows = audit._audit_export_rows(client, export_date=date(2026, 6, 12))
    row = rows[0]
    assert row["latest_statement_date"] == "2025-12-31"
    assert row["data_quality_details_json"]["statement_completeness"]["source"] == "latest"
    statement_query = next(call for call in client.calls if call["table"] == "statements_norm")
    dq_raw_query = next(call for call in client.calls if call["table"] == "company_data_quality_snapshots")
    assert statement_query["order_by"] == [("company_id", False), ("period_end_date", True), ("created_at", True)]
    assert dq_raw_query["order_by"] == [("company_id", False), ("snapshot_date", True), ("updated_at", True), ("created_at", True)]


def test_live_audit_export_rows_suppresses_tracking_only_old_hold(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        audit,
        "list_watchlist_active_companies",
        lambda client=None: [{"id": "c2", "ticker": "ASML", "name": "ASML Holding", "sector": "Technology", "industry": "Semiconductors"}],
    )
    client = _FakeClient(
        _tracking_tables(
            signal_row={
                "company_id": "c2",
                "id": "sig-2",
                "signal_date": "2026-06-12",
                "model_version": "signal_rule_v3",
                "p_buy": 0.42,
                "p_buy_adjusted": 0.31,
                "p_sell": 0.28,
                "final_signal": "hold",
                "uncertainty_penalty": 0.2,
                "red_flags": ["stale_input"],
                "top_feature_contributors": _reasoning_contributors(),
                "explanation": "Hold - illustrative stale analytical output.",
                "freshness_flag": "stale",
            }
        )
    )
    rows = audit._audit_export_rows(client, export_date=date(2026, 6, 12))
    row = rows[0]
    assert row["readiness_status"] == "tracking_only"
    assert row["stored_final_signal"] == "hold"
    assert row["signal_display_state"] == "readiness_suppressed"
    assert row["final_signal"] is None
    assert row["signal_run_id"] is None
    assert row["p_buy"] is None
    assert row["explanation"] is None


def test_live_audit_export_rows_marks_tracking_only_without_signal_row(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        audit,
        "list_watchlist_active_companies",
        lambda client=None: [{"id": "c2", "ticker": "MFC", "name": "Manulife Financial Corporation", "sector": "Financials", "industry": "Insurance"}],
    )
    client = _FakeClient(_tracking_tables(signal_row=None))
    rows = audit._audit_export_rows(client, export_date=date(2026, 6, 12))
    row = rows[0]
    assert row["readiness_status"] == "tracking_only"
    assert row["stored_final_signal"] is None
    assert row["signal_display_state"] == "no_signal"
    assert row["final_signal"] is None
    assert row["signal_run_id"] is None


def test_live_write_csv_preserves_header_order(monkeypatch: Any, tmp_path: Path) -> None:
    rows = _canonical_rows(monkeypatch)
    path = tmp_path / "audit.csv"
    audit._write_csv(path, rows)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
    assert header == _live_export_field_order()


def test_live_write_json_preserves_nested_row_structure(monkeypatch: Any, tmp_path: Path) -> None:
    rows = _canonical_rows(monkeypatch)
    path = tmp_path / "audit.json"
    exported_at = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    audit._write_json(path, rows, exported_at=exported_at)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["exported_at"] == exported_at.isoformat()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["data_quality_details_json"]["statement_completeness"]["source"] == "latest"
    assert payload["rows"][0]["valuation_assumptions_json"]["diagnostics"]["valuation_sanity_status"] == "high_uncertainty"
    assert payload["rows"][0]["signal_display_state"] == "analytical_signal"


def test_live_zero_row_export_behavior(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    json_path = tmp_path / "empty.json"
    audit._write_csv(csv_path, [])
    audit._write_json(json_path, [], exported_at=datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc))
    assert csv_path.read_text(encoding="utf-8") == ""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["row_count"] == 0
    assert payload["rows"] == []


def test_imported_main_runs_canonical_export_path(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(
        audit,
        "list_watchlist_active_companies",
        lambda client=None: [{"id": "c1", "ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics"}],
    )
    monkeypatch.setattr(audit, "get_supabase_client", lambda: _FakeClient(_base_tables()))
    result = audit.main(["--output-dir", str(tmp_path)])
    assert result == 0
    assert len(list(tmp_path.glob("model_audit_*.csv"))) == 1
    assert len(list(tmp_path.glob("model_audit_*.json"))) == 1
