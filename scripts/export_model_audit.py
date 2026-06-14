"""Export a current-state model audit snapshot for active watchlist companies.

The export is read-only: it reads persisted current-state tables/views,
computes additional audit-oriented derived fields locally, and writes CSV/JSON
files under ``exports/audit/`` for offline review.

Usage:
    python scripts/export_model_audit.py
    python scripts/export_model_audit.py --output-dir exports/audit
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from investment_app.db.repositories import list_watchlist_active_companies
from investment_app.db.supabase_client import get_supabase_client
from investment_app.scoring.explanations import _has_valuation_concern
from investment_app.scoring.probabilistic import (
    _STRONG_SELL_CONFIRMING_FLAGS,
    _has_valuation_only_strong_sell_confirmation,
    _valuation_position_bucket,
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for candidate in (text, text[:10]):
            try:
                return date.fromisoformat(candidate)
            except ValueError:
                continue
    return None


def _iso_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=_json_default)


def _chunked(values: list[str], size: int = 100) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _fetch_rows_for_company_ids(
    client: Any,
    table_name: str,
    company_ids: list[str],
    select_columns: str = "*",
    *,
    order_by: list[tuple[str, bool]] | None = None,
) -> list[dict[str, Any]]:
    if not company_ids:
        return []

    rows: list[dict[str, Any]] = []
    for chunk in _chunked(company_ids):
        query = client.table(table_name).select(select_columns).in_("company_id", chunk)
        for column_name, desc in order_by or []:
            query = query.order(column_name, desc=desc)
        response = query.execute()
        rows.extend(response.data or [])
    return rows


def _map_by_company_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        row["company_id"]: row
        for row in rows
        if isinstance(row, dict) and row.get("company_id")
    }


def _latest_per_company(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        company_id = row.get("company_id")
        if company_id and company_id not in latest:
            latest[company_id] = row
    return latest


def _build_valuation_row(export_row: dict[str, Any]) -> dict[str, Any] | None:
    if export_row.get("valuation_run_id") is None:
        return None
    return {
        "current_price": export_row.get("valuation_current_price"),
        "iv_p50": export_row.get("iv_p50"),
        "iv_p75": export_row.get("iv_p75"),
        "uncertainty_width": export_row.get("uncertainty_width"),
        "margin_of_safety_conservative": export_row.get("margin_of_safety_conservative"),
    }


def _distribution_values(assumptions: dict[str, Any] | None) -> list[float]:
    if not isinstance(assumptions, dict):
        return []
    aggregation = assumptions.get("aggregation")
    if not isinstance(aggregation, dict):
        return []
    distribution = aggregation.get("distribution")
    if not isinstance(distribution, list):
        return []

    out: list[float] = []
    for entry in distribution:
        if not isinstance(entry, dict):
            continue
        numeric = _safe_float(entry.get("value"))
        if numeric is not None:
            out.append(numeric)
    return out


def _distribution_stats(assumptions: dict[str, Any] | None) -> dict[str, float | None]:
    values = _distribution_values(assumptions)
    if not values:
        return {
            "distribution_min": None,
            "distribution_max": None,
            "distribution_span_ratio": None,
        }

    distribution_min = min(values)
    distribution_max = max(values)
    distribution_span_ratio = None
    if distribution_min > 0.0:
        distribution_span_ratio = distribution_max / distribution_min

    return {
        "distribution_min": distribution_min,
        "distribution_max": distribution_max,
        "distribution_span_ratio": distribution_span_ratio,
    }


def _multiples_vs_dcf_mid_gap(assumptions: dict[str, Any] | None) -> float | None:
    if not isinstance(assumptions, dict):
        return None
    multiples = assumptions.get("multiples")
    dcf = assumptions.get("dcf")
    if not isinstance(multiples, dict) or not isinstance(dcf, dict):
        return None

    multiples_mid = _safe_float(multiples.get("blended_value"))
    dcf_mid = _safe_float(dcf.get("base_iv"))
    if multiples_mid is None or dcf_mid is None:
        return None
    return multiples_mid - dcf_mid


def _statement_age_days(row: dict[str, Any], *, export_date: date) -> int | None:
    latest_statement_date = _as_date(row.get("latest_statement_date"))
    if latest_statement_date is None:
        return None

    anchor_date = (
        _as_date(row.get("signal_date"))
        or _as_date(row.get("valuation_date"))
        or export_date
    )
    return (anchor_date - latest_statement_date).days


def _latest_statement_year(row: dict[str, Any]) -> int | None:
    fiscal_year = row.get("fiscal_year")
    if fiscal_year is not None:
        try:
            return int(fiscal_year)
        except (TypeError, ValueError):
            pass
    latest_statement_date = _as_date(row.get("latest_statement_date"))
    return latest_statement_date.year if latest_statement_date else None


def _strong_sell_confirmation_type(row: dict[str, Any]) -> str:
    if str(row.get("final_signal") or "").lower() != "strong_sell":
        return "not_strong_sell"

    red_flags = row.get("red_flags") or []
    if any(flag in _STRONG_SELL_CONFIRMING_FLAGS for flag in red_flags):
        return "hard_risk_confirmed"

    valuation_row = _build_valuation_row(row)
    if _has_valuation_only_strong_sell_confirmation(valuation_row):
        return "valuation_only"
    return "not_strong_sell"


def _hold_uncertainty_constrained(row: dict[str, Any]) -> bool:
    if str(row.get("final_signal") or "").lower() != "hold":
        return False

    uncertainty_width = _safe_float(row.get("uncertainty_width"))
    if uncertainty_width is None or uncertainty_width <= 0.50:
        return False

    valuation_row = _build_valuation_row(row)
    if valuation_row is None:
        return False

    return _has_valuation_concern(
        mos=_safe_float(row.get("margin_of_safety_conservative")),
        midpoint_premium=(
            None
            if valuation_row.get("current_price") is None or valuation_row.get("iv_p50") in (None, 0)
            else (_safe_float(valuation_row.get("current_price")) - _safe_float(valuation_row.get("iv_p50")))
            / _safe_float(valuation_row.get("iv_p50"))
        ),
        red_flags=list(row.get("red_flags") or []),
    )


def _stale_input_blocked(row: dict[str, Any]) -> bool:
    reason_codes = row.get("readiness_reason_codes")
    if isinstance(reason_codes, str):
        normalized = [part.strip().lower() for part in reason_codes.split(",") if part.strip()]
    elif isinstance(reason_codes, list):
        normalized = [str(code).strip().lower() for code in reason_codes if str(code).strip()]
    else:
        normalized = []

    return (
        "stale_fundamentals" in normalized
        and row.get("can_run_valuation") is False
        and row.get("can_run_signal") is False
    )


def _signal_reasoning_metadata(top_feature_contributors: Any) -> dict[str, Any]:
    if not isinstance(top_feature_contributors, list):
        return {}
    for item in top_feature_contributors:
        if not isinstance(item, dict):
            continue
        if item.get("name") == "signal_reasoning_metadata" and isinstance(item.get("value"), dict):
            return item.get("value") or {}
    return {}


def _signal_display_state(row: dict[str, Any]) -> str:
    if row.get("can_run_signal") is False:
        stored_final_signal = str(row.get("stored_final_signal") or "").strip()
        return "readiness_suppressed" if stored_final_signal else "no_signal"

    current_signal = str(row.get("final_signal") or "").strip()
    if current_signal:
        return "analytical_signal"
    return "no_signal"


def build_derived_fields(
    row: dict[str, Any],
    *,
    export_date: date,
) -> dict[str, Any]:
    latest_price = _safe_float(row.get("latest_price"))
    iv_p50 = _safe_float(row.get("iv_p50"))
    iv_p90 = _safe_float(row.get("iv_p90"))

    price_to_iv_mid = None
    if latest_price is not None and iv_p50 is not None and iv_p50 > 0.0:
        price_to_iv_mid = latest_price / iv_p50

    price_to_iv_high = None
    if latest_price is not None and iv_p90 is not None and iv_p90 > 0.0:
        price_to_iv_high = latest_price / iv_p90

    assumptions = row.get("valuation_assumptions_json")
    if not isinstance(assumptions, dict):
        assumptions = None
    diagnostics = (assumptions or {}).get("diagnostics") if isinstance((assumptions or {}).get("diagnostics"), dict) else {}
    reasoning = _signal_reasoning_metadata(row.get("top_feature_contributors"))

    valuation_row = _build_valuation_row(row)
    valuation_bucket = _valuation_position_bucket(valuation_row)
    statement_age_days = _statement_age_days(row, export_date=export_date)

    derived = {
        "price_to_iv_mid": price_to_iv_mid,
        "price_to_iv_high": price_to_iv_high,
        "valuation_bucket": valuation_bucket,
        "strong_sell_confirmation_type": _strong_sell_confirmation_type(row),
        "hold_uncertainty_constrained": _hold_uncertainty_constrained(row),
        "stale_input_blocked": _stale_input_blocked(row),
        "valuation_sanity_status": diagnostics.get("valuation_sanity_status"),
        "valuation_sanity_reason_codes": diagnostics.get("valuation_sanity_reason_codes"),
        "valuation_evidence_usable": diagnostics.get("valuation_evidence_usable"),
        "valuation_display_suppressed": diagnostics.get("valuation_display_suppressed"),
        "valuation_signal_influence_blocked": diagnostics.get("valuation_signal_influence_blocked"),
        "valuation_method_coverage": diagnostics.get("valuation_method_coverage"),
        "iv_range_ratio_p90_p10": diagnostics.get("iv_range_ratio_p90_p10"),
        "distribution_span_ratio_diagnostics": diagnostics.get("distribution_span_ratio"),
        "dcf_multiples_gap_ratio": diagnostics.get("dcf_multiples_gap_ratio"),
        "max_terminal_value_share": diagnostics.get("max_terminal_value_share"),
        "terminal_spread": diagnostics.get("terminal_spread"),
        "midpoint_price_ratio": diagnostics.get("midpoint_price_ratio"),
        "statement_age_days": statement_age_days,
        "latest_statement_year": _latest_statement_year(row),
        "stale_statement_input": (
            statement_age_days is not None and statement_age_days > 365
        ),
        "has_dcf_component": (row.get("scenario_count") or 0) > 0,
        "valuation_partial_flag": row.get("valuation_status") == "partial",
        "multiples_vs_dcf_mid_gap": _multiples_vs_dcf_mid_gap(assumptions),
        "dominant_signal_driver": reasoning.get("dominant_signal_driver"),
        "hold_reason": reasoning.get("hold_reason"),
        "valuation_used_in_signal": reasoning.get("valuation_used_in_signal"),
        "risk_override_applied": reasoning.get("risk_override_applied"),
        "confidence_limiter_codes": reasoning.get("confidence_limiter_codes"),
        "strong_sell_basis": reasoning.get("strong_sell_basis"),
        "buy_conviction_limited": reasoning.get("buy_conviction_limited"),
        "explanation_quality_warning": reasoning.get("explanation_quality_warning"),
        "recommendation_language_warning": reasoning.get("recommendation_language_warning"),
        "probability_interpretation_note": reasoning.get("probability_interpretation_note"),
        "signal_display_state": _signal_display_state(row),
    }
    derived.update(_distribution_stats(assumptions))
    return derived


def _audit_export_rows(client: Any, *, export_date: date) -> list[dict[str, Any]]:
    active_companies = list_watchlist_active_companies(client=client)
    active_companies = sorted(active_companies, key=lambda row: row.get("ticker") or "")
    company_ids = [row["id"] for row in active_companies if row.get("id")]

    latest_prices = _map_by_company_id(
        _fetch_rows_for_company_ids(
            client,
            "latest_price_eod",
            company_ids,
            "company_id, price_date, close, provider",
        )
    )
    readiness_rows = _map_by_company_id(
        _fetch_rows_for_company_ids(
            client,
            "analysis_readiness_latest",
            company_ids,
            "company_id, readiness_status, provider_mix, readiness_reason_codes, can_run_valuation, can_run_signal, limiting_domain, readiness_updated_at",
        )
    )
    dq_rows = _map_by_company_id(
        _fetch_rows_for_company_ids(
            client,
            "latest_company_data_quality_snapshots",
            company_ids,
            "company_id, snapshot_date, data_quality_status, data_quality_warning_codes, price_validation_status, statement_completeness_status, statement_completeness_summary, fundamentals_provider_comparison_status, fundamentals_provider_comparison_summary",
        )
    )
    dq_raw_rows = _latest_per_company(
        _fetch_rows_for_company_ids(
            client,
            "company_data_quality_snapshots",
            company_ids,
            "company_id, snapshot_date, details",
            order_by=[("company_id", False), ("snapshot_date", True), ("updated_at", True), ("created_at", True)],
        )
    )
    latest_statements = _latest_per_company(
        _fetch_rows_for_company_ids(
            client,
            "statements_norm",
            company_ids,
            "company_id, source, fiscal_year, fiscal_period, period_end_date, currency, revenue, gross_profit, operating_income, ebit, ebitda, net_income, cfo, capex, free_cash_flow, depreciation_amortization, cash_and_equivalents, total_debt, total_equity, diluted_shares, created_at",
            order_by=[("company_id", False), ("period_end_date", True), ("created_at", True)],
        )
    )
    latest_ratios = _map_by_company_id(
        _fetch_rows_for_company_ids(
            client,
            "latest_ratios_factors",
            company_ids,
            "company_id, factor_date, roic, roe, fcf_yield, net_debt_to_ebitda, interest_coverage, ev_to_ebitda, price_to_sales, price_to_book, news_sentiment_7d, data_quality_score",
        )
    )
    latest_valuations = _map_by_company_id(
        _fetch_rows_for_company_ids(
            client,
            "latest_valuation_runs",
            company_ids,
            "company_id, id, valuation_date, model_version, currency, current_price, iv_p10, iv_p25, iv_p50, iv_p75, iv_p90, margin_of_safety_conservative, uncertainty_width, assumptions",
        )
    )
    latest_qualitative = _map_by_company_id(
        _fetch_rows_for_company_ids(
            client,
            "latest_qualitative_scores",
            company_ids,
            "company_id, id, score_date, model_version, final_quality_score",
        )
    )
    latest_signals = _map_by_company_id(
        _fetch_rows_for_company_ids(
            client,
            "latest_signal_runs",
            company_ids,
            "company_id, id, signal_date, model_version, p_buy, p_buy_adjusted, p_sell, final_signal, uncertainty_penalty, red_flags, top_feature_contributors, explanation, freshness_flag",
        )
    )

    enriched_rows: list[dict[str, Any]] = []
    for company in active_companies:
        company_id = company["id"]
        price_row = latest_prices.get(company_id, {})
        readiness_row = readiness_rows.get(company_id, {})
        dq_row = dq_rows.get(company_id, {})
        dq_raw_row = dq_raw_rows.get(company_id, {})
        statement_row = latest_statements.get(company_id, {})
        ratio_row = latest_ratios.get(company_id, {})
        valuation_row = latest_valuations.get(company_id, {})
        qualitative_row = latest_qualitative.get(company_id, {})
        signal_row = latest_signals.get(company_id, {})
        can_run_signal = readiness_row.get("can_run_signal")
        signal_suppressed = can_run_signal is False
        stored_final_signal = signal_row.get("final_signal")

        merged: dict[str, Any] = {
            "company_id": company_id,
            "ticker": company.get("ticker"),
            "company_name": company.get("name"),
            "sector": company.get("sector"),
            "industry": company.get("industry"),
            "latest_price": price_row.get("close"),
            "price_date": price_row.get("price_date"),
            "price_provider": price_row.get("provider"),
            "readiness_status": readiness_row.get("readiness_status"),
            "provider_mix": readiness_row.get("provider_mix"),
            "readiness_reason_codes": readiness_row.get("readiness_reason_codes"),
            "can_run_valuation": readiness_row.get("can_run_valuation"),
            "can_run_signal": readiness_row.get("can_run_signal"),
            "limiting_domain": readiness_row.get("limiting_domain"),
            "readiness_updated_at": readiness_row.get("readiness_updated_at"),
            "data_quality_status": dq_row.get("data_quality_status"),
            "data_quality_warning_codes": dq_row.get("data_quality_warning_codes"),
            "price_validation_status": dq_row.get("price_validation_status"),
            "statement_completeness_status": dq_row.get("statement_completeness_status"),
            "statement_completeness_summary": dq_row.get("statement_completeness_summary"),
            "fundamentals_provider_comparison_status": dq_row.get("fundamentals_provider_comparison_status"),
            "fundamentals_provider_comparison_summary": dq_row.get("fundamentals_provider_comparison_summary"),
            "data_quality_details_json": dq_raw_row.get("details"),
            "statement_source": statement_row.get("source"),
            "fiscal_year": statement_row.get("fiscal_year"),
            "fiscal_period": statement_row.get("fiscal_period"),
            "latest_statement_date": statement_row.get("period_end_date"),
            "revenue": statement_row.get("revenue"),
            "gross_profit": statement_row.get("gross_profit"),
            "operating_income": statement_row.get("operating_income"),
            "ebit": statement_row.get("ebit"),
            "ebitda": statement_row.get("ebitda"),
            "net_income": statement_row.get("net_income"),
            "cfo": statement_row.get("cfo"),
            "capex": statement_row.get("capex"),
            "free_cash_flow": statement_row.get("free_cash_flow"),
            "depreciation_amortization": statement_row.get("depreciation_amortization"),
            "cash_and_equivalents": statement_row.get("cash_and_equivalents"),
            "total_debt": statement_row.get("total_debt"),
            "total_equity": statement_row.get("total_equity"),
            "diluted_shares": statement_row.get("diluted_shares"),
            "factor_date": ratio_row.get("factor_date"),
            "roic": ratio_row.get("roic"),
            "roe": ratio_row.get("roe"),
            "fcf_yield": ratio_row.get("fcf_yield"),
            "net_debt_to_ebitda": ratio_row.get("net_debt_to_ebitda"),
            "interest_coverage": ratio_row.get("interest_coverage"),
            "ev_to_ebitda": ratio_row.get("ev_to_ebitda"),
            "price_to_sales": ratio_row.get("price_to_sales"),
            "price_to_book": ratio_row.get("price_to_book"),
            "news_sentiment_7d": ratio_row.get("news_sentiment_7d"),
            "ratio_data_quality_score": ratio_row.get("data_quality_score"),
            "valuation_run_id": valuation_row.get("id"),
            "valuation_date": valuation_row.get("valuation_date"),
            "valuation_model_version": valuation_row.get("model_version"),
            "valuation_currency": valuation_row.get("currency"),
            "valuation_current_price": valuation_row.get("current_price"),
            "iv_p10": valuation_row.get("iv_p10"),
            "iv_p25": valuation_row.get("iv_p25"),
            "iv_p50": valuation_row.get("iv_p50"),
            "iv_p75": valuation_row.get("iv_p75"),
            "iv_p90": valuation_row.get("iv_p90"),
            "margin_of_safety_conservative": valuation_row.get("margin_of_safety_conservative"),
            "uncertainty_width": valuation_row.get("uncertainty_width"),
            "valuation_assumptions_json": valuation_row.get("assumptions"),
            "mos_basis": ((valuation_row.get("assumptions") or {}).get("diagnostics") or {}).get("mos_basis"),
            "scenario_count": ((valuation_row.get("assumptions") or {}).get("diagnostics") or {}).get("scenario_count"),
            "uncertainty_category": ((valuation_row.get("assumptions") or {}).get("diagnostics") or {}).get("uncertainty_category"),
            "distribution_collapsed": "distribution_collapsed" in (((valuation_row.get("assumptions") or {}).get("diagnostics") or {}).get("warnings") or []),
            "valuation_status": ((valuation_row.get("assumptions") or {}).get("diagnostics") or {}).get("valuation_status"),
            "qualitative_score_id": qualitative_row.get("id"),
            "qualitative_score_date": qualitative_row.get("score_date"),
            "qualitative_model_version": qualitative_row.get("model_version"),
            "final_quality_score": qualitative_row.get("final_quality_score"),
            "signal_run_id": None if signal_suppressed else signal_row.get("id"),
            "signal_date": None if signal_suppressed else signal_row.get("signal_date"),
            "signal_model_version": None if signal_suppressed else signal_row.get("model_version"),
            "stored_final_signal": stored_final_signal,
            "p_buy": None if signal_suppressed else signal_row.get("p_buy"),
            "p_buy_adjusted": None if signal_suppressed else signal_row.get("p_buy_adjusted"),
            "p_sell": None if signal_suppressed else signal_row.get("p_sell"),
            "final_signal": None if signal_suppressed else stored_final_signal,
            "uncertainty_penalty": None if signal_suppressed else signal_row.get("uncertainty_penalty"),
            "red_flags": None if signal_suppressed else signal_row.get("red_flags"),
            "top_feature_contributors": None if signal_suppressed else signal_row.get("top_feature_contributors"),
            "explanation": None if signal_suppressed else signal_row.get("explanation"),
            "freshness_flag": None if signal_suppressed else signal_row.get("freshness_flag"),
        }
        merged.update(build_derived_fields(merged, export_date=export_date))
        enriched_rows.append(merged)

    return enriched_rows


def _csv_ready_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return _json_string(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_ready_value(value) for key, value in row.items()})


def _write_json(path: Path, rows: list[dict[str, Any]], *, exported_at: datetime) -> None:
    payload = {
        "exported_at": exported_at.isoformat(),
        "row_count": len(rows),
        "rows": rows,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, default=_json_default),
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a read-only current-state model audit snapshot."
    )
    parser.add_argument(
        "--output-dir",
        default="exports/audit",
        help="Directory for CSV/JSON export files (default: exports/audit)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    exported_at = _iso_now_utc()
    export_date = exported_at.date()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = get_supabase_client()
    rows = _audit_export_rows(client, export_date=export_date)

    stem = f"model_audit_{exported_at.strftime('%Y%m%dT%H%M%SZ')}"
    csv_path = output_dir / f"{stem}.csv"
    json_path = output_dir / f"{stem}.json"

    _write_csv(csv_path, rows)
    _write_json(json_path, rows, exported_at=exported_at)

    print(f"Wrote {len(rows)} rows to {csv_path}")
    print(f"Wrote {len(rows)} rows to {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
