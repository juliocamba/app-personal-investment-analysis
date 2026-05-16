"""Operational data-quality helpers for Phase 12A diagnostics.

This module is intentionally pure and side-effect free. It provides small
helpers for comparing overlapping provider prices and summarizing statement
completeness without affecting readiness, valuation, signals, or dashboard
display behavior.
"""
from __future__ import annotations

from typing import Any

PRICE_DIVERGENCE_WARNING_THRESHOLD = 0.01
PRICE_DIVERGENCE_CRITICAL_THRESHOLD = 0.05

PRICE_VALIDATION_OK = "ok"
PRICE_VALIDATION_WARNING = "warning"
PRICE_VALIDATION_CRITICAL = "critical"
PRICE_VALIDATION_NOT_COMPARABLE = "not_comparable"

PRICE_VALIDATION_STATUSES: frozenset[str] = frozenset({
    PRICE_VALIDATION_OK,
    PRICE_VALIDATION_WARNING,
    PRICE_VALIDATION_CRITICAL,
    PRICE_VALIDATION_NOT_COMPARABLE,
})

WARNING_CODE_PRICE_DIVERGENCE_WARNING = "price_divergence_warning"
WARNING_CODE_PRICE_DIVERGENCE_CRITICAL = "price_divergence_critical"
WARNING_CODE_PRICE_NOT_COMPARABLE = "price_not_comparable"
WARNING_CODE_NO_STATEMENTS_AVAILABLE = "no_statements_available"
WARNING_CODE_INCOMPLETE_STATEMENT_SET = "incomplete_statement_set"
WARNING_CODE_MISSING_KEY_FIELDS = "missing_key_fields"
WARNING_CODE_INSUFFICIENT_PERIOD_COVERAGE = "insufficient_period_coverage"
WARNING_CODE_FUNDAMENTALS_PROVIDER_OVERLAP_MISSING = "fundamentals_provider_overlap_missing"
WARNING_CODE_FUNDAMENTALS_PROVIDER_DISCREPANCY = "fundamentals_provider_discrepancy"

MIN_STATEMENT_PERIODS = 2
FUNDAMENTALS_DISCREPANCY_WARNING_THRESHOLD = 0.05
FUNDAMENTALS_DISCREPANCY_CRITICAL_THRESHOLD = 0.15

FUNDAMENTALS_COMPARISON_OK = "ok"
FUNDAMENTALS_COMPARISON_WARNING = "warning"
FUNDAMENTALS_COMPARISON_CRITICAL = "critical"
FUNDAMENTALS_COMPARISON_NOT_COMPARABLE = "not_comparable"

_STATEMENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "revenue",
    "net_income",
    "cfo",
    "capex",
    "total_assets",
    "total_equity",
)
_STATEMENT_OPTIONAL_FIELDS: tuple[str, ...] = ("diluted_shares",)
_FUNDAMENTALS_COMPARE_FIELDS: tuple[tuple[str, str], ...] = (
    ("revenue", "revenue"),
    ("net_income", "net_income"),
    ("total_assets", "total_assets"),
    ("total_liabilities", "total_liabilities"),
    ("equity", "total_equity"),
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_price_value(row: dict[str, Any] | None) -> float | None:
    """Return the price value from a price row, or ``None`` when unusable."""
    if not row:
        return None
    price = _safe_float(
        row.get("close")
        if row.get("close") is not None
        else row.get("adjusted_close")
    )
    if price is None or price <= 0.0:
        return None
    return price


def calculate_price_divergence_pct(
    reference_price: float | int | None,
    comparison_price: float | int | None,
) -> float | None:
    """Return absolute divergence as a fraction of the reference price.

    Example: reference=100, comparison=101.5 -> 0.015
    """
    ref = _safe_float(reference_price)
    other = _safe_float(comparison_price)
    if ref is None or other is None or ref <= 0.0 or other <= 0.0:
        return None
    return abs(other - ref) / ref


def classify_price_divergence(
    divergence_pct: float | None,
) -> str:
    """Classify a price divergence percentage into an operational status."""
    if divergence_pct is None:
        return PRICE_VALIDATION_NOT_COMPARABLE
    if divergence_pct > PRICE_DIVERGENCE_CRITICAL_THRESHOLD:
        return PRICE_VALIDATION_CRITICAL
    if divergence_pct > PRICE_DIVERGENCE_WARNING_THRESHOLD:
        return PRICE_VALIDATION_WARNING
    return PRICE_VALIDATION_OK


def find_latest_overlapping_provider_prices(
    price_rows: list[dict[str, Any]],
    *,
    reference_provider: str = "fmp",
    comparison_provider: str = "twelve_data",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the latest same-date provider pair, or ``(None, None)``."""
    by_date_provider: dict[tuple[str, str], dict[str, Any]] = {}
    for row in price_rows:
        price_date = str(row.get("price_date") or "").strip()
        provider = str(row.get("provider") or "").strip()
        if not price_date or not provider:
            continue
        key = (price_date, provider)
        existing = by_date_provider.get(key)
        if existing is None:
            by_date_provider[key] = row
            continue
        existing_created_at = str(existing.get("created_at") or "")
        candidate_created_at = str(row.get("created_at") or "")
        if candidate_created_at >= existing_created_at:
            by_date_provider[key] = row

    overlapping_dates = sorted(
        {
            price_date
            for price_date, provider in by_date_provider
            if provider == reference_provider
            and (price_date, comparison_provider) in by_date_provider
        },
        reverse=True,
    )
    if not overlapping_dates:
        return None, None

    latest_date = overlapping_dates[0]
    return (
        by_date_provider.get((latest_date, reference_provider)),
        by_date_provider.get((latest_date, comparison_provider)),
    )


def compare_provider_prices(
    reference_row: dict[str, Any] | None,
    comparison_row: dict[str, Any] | None,
    *,
    reference_provider: str = "fmp",
    comparison_provider: str = "twelve_data",
) -> dict[str, Any]:
    """Compare two provider rows and return a normalized diagnostic result."""
    reference_price = extract_price_value(reference_row)
    comparison_price = extract_price_value(comparison_row)
    divergence_pct = calculate_price_divergence_pct(reference_price, comparison_price)
    status = classify_price_divergence(divergence_pct)

    comparison_date = None
    if reference_row and reference_row.get("price_date"):
        comparison_date = str(reference_row["price_date"])
    elif comparison_row and comparison_row.get("price_date"):
        comparison_date = str(comparison_row["price_date"])

    return {
        "status": status,
        "comparison_date": comparison_date,
        "reference_provider": reference_provider,
        "comparison_provider": comparison_provider,
        "reference_price": reference_price,
        "comparison_price": comparison_price,
        "divergence_pct": divergence_pct,
    }


def compare_latest_overlapping_provider_prices(
    price_rows: list[dict[str, Any]],
    *,
    reference_provider: str = "fmp",
    comparison_provider: str = "twelve_data",
) -> dict[str, Any]:
    """Compare the latest overlapping provider prices from a list of rows."""
    reference_row, comparison_row = find_latest_overlapping_provider_prices(
        price_rows,
        reference_provider=reference_provider,
        comparison_provider=comparison_provider,
    )
    return compare_provider_prices(
        reference_row,
        comparison_row,
        reference_provider=reference_provider,
        comparison_provider=comparison_provider,
    )


def build_price_validation_payload(
    *,
    ticker: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact, sanitized pipeline-event payload."""
    divergence_pct = result.get("divergence_pct")
    payload: dict[str, Any] = {
        "ticker": ticker,
        "event": "price_cross_provider_validation",
        "status": result.get("status", PRICE_VALIDATION_NOT_COMPARABLE),
        "comparison_date": result.get("comparison_date"),
        "reference_provider": result.get("reference_provider", "fmp"),
        "comparison_provider": result.get("comparison_provider", "twelve_data"),
    }
    if divergence_pct is not None:
        payload["divergence_pct"] = round(float(divergence_pct), 6)
    return payload


def build_price_validation_warning_codes(status: str) -> list[str]:
    """Return compact warning codes for the persisted snapshot."""
    if status == PRICE_VALIDATION_CRITICAL:
        return [WARNING_CODE_PRICE_DIVERGENCE_CRITICAL]
    if status == PRICE_VALIDATION_WARNING:
        return [WARNING_CODE_PRICE_DIVERGENCE_WARNING]
    if status == PRICE_VALIDATION_NOT_COMPARABLE:
        return [WARNING_CODE_PRICE_NOT_COMPARABLE]
    return []


def _annual_statement_rows(statement_rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = statement_rows or []
    annual_rows = [
        row for row in rows
        if str(row.get("fiscal_period") or "annual").lower() == "annual"
    ]
    annual_rows.sort(
        key=lambda row: (
            str(row.get("period_end_date") or ""),
            int(row.get("fiscal_year") or 0),
        ),
        reverse=True,
    )
    return annual_rows


def _annual_statement_rows_for_source(
    statement_rows: list[dict[str, Any]] | None,
    source: str,
) -> list[dict[str, Any]]:
    return [
        row for row in _annual_statement_rows(statement_rows)
        if str(row.get("source") or "").strip() == source
    ]


def _has_positive_or_zero_number(row: dict[str, Any], field: str) -> bool:
    value = _safe_float(row.get(field))
    return value is not None


def evaluate_statement_completeness(
    statement_rows: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Summarize latest annual statement completeness for Phase 12A diagnostics.

    This is intentionally diagnostic-only. It does not mirror or modify the
    readiness classifier, and it never raises on missing or malformed inputs.
    """
    annual_rows = _annual_statement_rows(statement_rows)
    if not annual_rows:
        return {
            "warning_codes": [WARNING_CODE_NO_STATEMENTS_AVAILABLE],
            "details": {
                "status": "warning",
                "latest_period_end_date": None,
                "latest_fiscal_year": None,
                "latest_source": None,
                "annual_periods_found": 0,
                "missing_fields": [],
                "missing_optional_fields": [],
                "missing_statement_domains": ["income", "cashflow", "balance"],
            },
        }

    latest_row = annual_rows[0]
    unique_periods = {
        (int(row.get("fiscal_year") or 0), str(row.get("period_end_date") or ""))
        for row in annual_rows
        if row.get("fiscal_year") is not None or row.get("period_end_date") is not None
    }
    missing_fields = [
        field for field in _STATEMENT_REQUIRED_FIELDS
        if not _has_positive_or_zero_number(latest_row, field)
    ]
    if not (
        _has_positive_or_zero_number(latest_row, "total_liabilities")
        or _has_positive_or_zero_number(latest_row, "total_debt")
    ):
        missing_fields.append("total_liabilities_or_debt")

    missing_optional_fields = [
        field for field in _STATEMENT_OPTIONAL_FIELDS
        if not _has_positive_or_zero_number(latest_row, field)
    ]

    missing_statement_domains: list[str] = []
    if not any(_has_positive_or_zero_number(latest_row, field) for field in ("revenue", "net_income")):
        missing_statement_domains.append("income")
    if not any(
        _has_positive_or_zero_number(latest_row, field)
        for field in ("cfo", "capex", "free_cash_flow")
    ):
        missing_statement_domains.append("cashflow")
    if not any(
        _has_positive_or_zero_number(latest_row, field)
        for field in ("total_assets", "total_liabilities", "total_debt", "total_equity")
    ):
        missing_statement_domains.append("balance")

    warning_codes: list[str] = []
    if missing_statement_domains:
        warning_codes.append(WARNING_CODE_INCOMPLETE_STATEMENT_SET)
    if missing_fields:
        warning_codes.append(WARNING_CODE_MISSING_KEY_FIELDS)
    if len(unique_periods) < MIN_STATEMENT_PERIODS:
        warning_codes.append(WARNING_CODE_INSUFFICIENT_PERIOD_COVERAGE)

    return {
        "warning_codes": warning_codes,
        "details": {
            "status": "warning" if warning_codes else "ok",
            "latest_period_end_date": latest_row.get("period_end_date"),
            "latest_fiscal_year": latest_row.get("fiscal_year"),
            "latest_source": latest_row.get("source"),
            "annual_periods_found": len(unique_periods),
            "missing_fields": missing_fields,
            "missing_optional_fields": missing_optional_fields,
            "missing_statement_domains": missing_statement_domains,
        },
    }


def _merge_warning_codes(*warning_code_lists: list[str]) -> list[str]:
    merged: list[str] = []
    for codes in warning_code_lists:
        for code in codes:
            if code not in merged:
                merged.append(code)
    return merged


def calculate_fundamentals_relative_difference_pct(
    reference_value: float | int | None,
    comparison_value: float | int | None,
) -> float | None:
    """Return a symmetric relative-difference fraction for fundamentals."""
    ref = _safe_float(reference_value)
    other = _safe_float(comparison_value)
    if ref is None or other is None:
        return None
    denominator = max(abs(ref), abs(other))
    if denominator == 0.0:
        return 0.0
    return abs(other - ref) / denominator


def classify_fundamentals_relative_difference(
    relative_difference_pct: float | None,
) -> str:
    if relative_difference_pct is None:
        return FUNDAMENTALS_COMPARISON_NOT_COMPARABLE
    if relative_difference_pct > FUNDAMENTALS_DISCREPANCY_CRITICAL_THRESHOLD:
        return FUNDAMENTALS_COMPARISON_CRITICAL
    if relative_difference_pct > FUNDAMENTALS_DISCREPANCY_WARNING_THRESHOLD:
        return FUNDAMENTALS_COMPARISON_WARNING
    return FUNDAMENTALS_COMPARISON_OK


def evaluate_fundamentals_provider_overlap(
    statement_rows: list[dict[str, Any]] | None,
    *,
    reference_source: str = "fmp",
    comparison_source: str = "sec_edgar",
) -> dict[str, Any]:
    """Compare overlapping annual FMP vs SEC fundamentals diagnostically only."""
    reference_rows = _annual_statement_rows_for_source(statement_rows, reference_source)
    comparison_rows = _annual_statement_rows_for_source(statement_rows, comparison_source)

    reference_by_year = {
        int(row.get("fiscal_year")): row
        for row in reference_rows
        if row.get("fiscal_year") is not None
    }
    comparison_by_year = {
        int(row.get("fiscal_year")): row
        for row in comparison_rows
        if row.get("fiscal_year") is not None
    }
    overlapping_years = sorted(
        set(reference_by_year).intersection(comparison_by_year),
        reverse=True,
    )
    if not overlapping_years:
        return {
            "warning_codes": [WARNING_CODE_FUNDAMENTALS_PROVIDER_OVERLAP_MISSING],
            "details": {
                "overlapping_period_count": 0,
                "compared_fields": [],
                "discrepant_fields": [],
                "max_relative_difference_pct": None,
                "discrepancy_level": FUNDAMENTALS_COMPARISON_NOT_COMPARABLE,
            },
        }

    compared_fields: set[str] = set()
    discrepant_fields: set[str] = set()
    max_relative_difference_pct: float | None = None
    discrepancy_level = FUNDAMENTALS_COMPARISON_OK

    severity_rank = {
        FUNDAMENTALS_COMPARISON_OK: 0,
        FUNDAMENTALS_COMPARISON_WARNING: 1,
        FUNDAMENTALS_COMPARISON_CRITICAL: 2,
        FUNDAMENTALS_COMPARISON_NOT_COMPARABLE: -1,
    }

    for fiscal_year in overlapping_years:
        reference_row = reference_by_year[fiscal_year]
        comparison_row = comparison_by_year[fiscal_year]
        for detail_field_name, row_field_name in _FUNDAMENTALS_COMPARE_FIELDS:
            relative_difference_pct = calculate_fundamentals_relative_difference_pct(
                reference_row.get(row_field_name),
                comparison_row.get(row_field_name),
            )
            if relative_difference_pct is None:
                continue
            compared_fields.add(detail_field_name)
            if (
                max_relative_difference_pct is None
                or relative_difference_pct > max_relative_difference_pct
            ):
                max_relative_difference_pct = relative_difference_pct
            field_level = classify_fundamentals_relative_difference(relative_difference_pct)
            if severity_rank[field_level] > severity_rank[discrepancy_level]:
                discrepancy_level = field_level
            if field_level in {FUNDAMENTALS_COMPARISON_WARNING, FUNDAMENTALS_COMPARISON_CRITICAL}:
                discrepant_fields.add(detail_field_name)

    if not compared_fields:
        return {
            "warning_codes": [WARNING_CODE_FUNDAMENTALS_PROVIDER_OVERLAP_MISSING],
            "details": {
                "overlapping_period_count": len(overlapping_years),
                "compared_fields": [],
                "discrepant_fields": [],
                "max_relative_difference_pct": None,
                "discrepancy_level": FUNDAMENTALS_COMPARISON_NOT_COMPARABLE,
            },
        }

    warning_codes: list[str] = []
    if discrepancy_level in {FUNDAMENTALS_COMPARISON_WARNING, FUNDAMENTALS_COMPARISON_CRITICAL}:
        warning_codes.append(WARNING_CODE_FUNDAMENTALS_PROVIDER_DISCREPANCY)

    return {
        "warning_codes": warning_codes,
        "details": {
            "overlapping_period_count": len(overlapping_years),
            "compared_fields": sorted(compared_fields),
            "discrepant_fields": sorted(discrepant_fields),
            "max_relative_difference_pct": (
                round(float(max_relative_difference_pct), 6)
                if max_relative_difference_pct is not None else None
            ),
            "discrepancy_level": discrepancy_level,
        },
    }


def build_data_quality_snapshot_row(
    *,
    company_id: str,
    snapshot_date: str,
    result: dict[str, Any],
    statement_diagnostics: dict[str, Any] | None = None,
    fundamentals_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a sanitized company_data_quality_snapshots row."""
    status = str(result.get("status") or PRICE_VALIDATION_NOT_COMPARABLE)
    divergence_pct = result.get("divergence_pct")
    statement_diagnostics = statement_diagnostics or {"warning_codes": [], "details": {}}
    fundamentals_diagnostics = fundamentals_diagnostics or {"warning_codes": [], "details": {}}
    details: dict[str, Any] = {
        "price_validation": {
            "reference_provider": result.get("reference_provider", "fmp"),
            "comparison_provider": result.get("comparison_provider", "twelve_data"),
            "comparison_date": result.get("comparison_date"),
        }
    }
    if divergence_pct is not None:
        details["price_validation"]["divergence_pct"] = round(float(divergence_pct), 6)
    statement_details = statement_diagnostics.get("details")
    if isinstance(statement_details, dict):
        details["statement_completeness"] = statement_details
    fundamentals_details = fundamentals_diagnostics.get("details")
    if isinstance(fundamentals_details, dict):
        details["fundamentals_provider_comparison"] = fundamentals_details

    return {
        "company_id": company_id,
        "snapshot_date": snapshot_date,
        "price_validation_status": status,
        "price_reference_provider": result.get("reference_provider", "fmp"),
        "price_comparison_provider": result.get("comparison_provider", "twelve_data"),
        "price_comparison_date": result.get("comparison_date"),
        "price_divergence_pct": round(float(divergence_pct), 6) if divergence_pct is not None else None,
        "warning_codes": _merge_warning_codes(
            build_price_validation_warning_codes(status),
            list(statement_diagnostics.get("warning_codes") or []),
            list(fundamentals_diagnostics.get("warning_codes") or []),
        ),
        "details": details,
    }
