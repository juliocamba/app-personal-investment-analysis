"""Pure provider-coverage and analysis-readiness classification helpers.

This module is intentionally side-effect free. It classifies one company using
persisted rows plus deterministic caller-supplied inputs such as the selected
profile provider.
"""
from __future__ import annotations

from datetime import date
from typing import Any

READINESS_ANALYSIS_READY = "analysis_ready"
READINESS_PARTIAL_ANALYSIS = "partial_analysis"
READINESS_PROVIDER_LIMITED = "provider_limited"
READINESS_UNSUPPORTED = "unsupported_for_analysis"
READINESS_TRACKING_ONLY = "tracking_only"

READINESS_STATUSES: frozenset[str] = frozenset({
    READINESS_ANALYSIS_READY,
    READINESS_PARTIAL_ANALYSIS,
    READINESS_PROVIDER_LIMITED,
    READINESS_UNSUPPORTED,
    READINESS_TRACKING_ONLY,
})

PROVIDER_DOMAINS: tuple[str, ...] = (
    "profile",
    "price",
    "fundamentals",
    "filings",
    "fx",
)

PROVIDER_MIX_PRIMARY_ONLY = "primary_only"
PROVIDER_MIX_FALLBACK = "fallback_mix"
PROVIDER_MIX_MIXED = "mixed_sources"
PROVIDER_MIX_PRICE_ONLY = "price_only"
PROVIDER_MIX_INSUFFICIENT = "insufficient_coverage"

PROVIDER_MIXES: frozenset[str] = frozenset({
    PROVIDER_MIX_PRIMARY_ONLY,
    PROVIDER_MIX_FALLBACK,
    PROVIDER_MIX_MIXED,
    PROVIDER_MIX_PRICE_ONLY,
    PROVIDER_MIX_INSUFFICIENT,
})

REASON_MISSING_PRICE = "missing_price"
REASON_MISSING_SUPPORTED_FUNDAMENTALS = "missing_supported_fundamentals_path"
REASON_NON_US_FUNDAMENTALS = "non_us_fundamentals_not_supported"
REASON_MISSING_MIN_HISTORY = "missing_min_statement_history"
REASON_MISSING_DILUTED_SHARES = "missing_diluted_shares"
REASON_MISSING_FCF_PATH = "missing_fcf_path"
REASON_NON_VIABLE_FCF = "non_viable_fcf"
REASON_VALUATION_BLOCKED = "valuation_blocked"
REASON_PROVIDER_LIMITED = "provider_limited"
REASON_UNSUPPORTED_INSTRUMENT = "unsupported_instrument"
REASON_VALUATION_PARTIAL = "valuation_partial"
REASON_VALUATION_READY = "valuation_ready"
REASON_STALE_FUNDAMENTALS = "stale_fundamentals"
STALE_FUNDAMENTALS_DAYS = 540

REASON_CODES: tuple[str, ...] = (
    REASON_MISSING_PRICE,
    REASON_MISSING_SUPPORTED_FUNDAMENTALS,
    REASON_NON_US_FUNDAMENTALS,
    REASON_MISSING_MIN_HISTORY,
    REASON_MISSING_DILUTED_SHARES,
    REASON_MISSING_FCF_PATH,
    REASON_NON_VIABLE_FCF,
    REASON_VALUATION_BLOCKED,
    REASON_PROVIDER_LIMITED,
    REASON_UNSUPPORTED_INSTRUMENT,
    REASON_VALUATION_PARTIAL,
    REASON_VALUATION_READY,
    REASON_STALE_FUNDAMENTALS,
)

_PRIMARY_PROVIDER_BY_DOMAIN = {
    "profile": "fmp",
    "price": "fmp",
    "fundamentals": "fmp",
    "filings": "sec_edgar",
    "fx": "ecb",
}

_US_COUNTRY_CODES = {
    "US",
    "USA",
    "UNITED STATES",
    "UNITED STATES OF AMERICA",
}

_SUPPORTED_COMPANY_TYPES = {"non_financial", "financial", "reit", "spac", "utility", "commodity"}
_UNSUPPORTED_INSTRUMENT_TYPES = {
    "bond",
    "crypto",
    "etf",
    "fund",
    "future",
    "index",
    "mutual_fund",
    "option",
    "preferred",
    "warrant",
}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metadata(company: dict[str, Any]) -> dict[str, Any]:
    metadata = company.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _is_supported_instrument(company: dict[str, Any]) -> bool:
    metadata = _metadata(company)
    instrument_type = (
        metadata.get("instrument_type")
        or company.get("instrument_type")
        or metadata.get("security_type")
        or company.get("security_type")
        or "equity"
    )
    instrument_type = str(instrument_type).strip().lower()
    if instrument_type in _UNSUPPORTED_INSTRUMENT_TYPES:
        return False

    company_type = str(company.get("company_type") or "non_financial").strip().lower()
    return company_type in _SUPPORTED_COMPANY_TYPES


def _has_profile(company: dict[str, Any]) -> bool:
    return bool((company.get("ticker") or "").strip()) and bool((company.get("name") or "").strip())


def _is_recent_price_row(latest_price_row: dict[str, Any] | None) -> bool:
    if not latest_price_row:
        return False
    close_val = _safe_float(
        latest_price_row.get("close")
        if latest_price_row.get("close") is not None
        else latest_price_row.get("adjusted_close")
    )
    return close_val is not None and close_val > 0.0


def _annual_statements(statement_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annual_rows = [
        row for row in statement_rows
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


def _selected_fundamentals_provider(statement_rows: list[dict[str, Any]]) -> str | None:
    sources = {str(row.get("source") or "").strip() for row in statement_rows if row.get("source")}
    if "fmp" in sources:
        return "fmp"
    if "sec_edgar" in sources:
        return "sec_edgar"
    if not sources:
        return None
    return sorted(sources)[0]


def _selected_filings_provider(filing_rows: list[dict[str, Any]]) -> str | None:
    sources = [str(row.get("source") or "").strip() for row in filing_rows if row.get("source")]
    if not sources:
        return None
    if "sec_edgar" in sources:
        return "sec_edgar"
    return sources[0]


def _valuation_diagnostics(latest_valuation_row: dict[str, Any] | None) -> dict[str, Any]:
    assumptions = latest_valuation_row.get("assumptions") if latest_valuation_row else {}
    if not isinstance(assumptions, dict):
        return {}
    diagnostics = assumptions.get("diagnostics")
    return diagnostics if isinstance(diagnostics, dict) else {}


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _latest_statement_date(statement_rows: list[dict[str, Any]]) -> date | None:
    latest: date | None = None
    for row in _annual_statements(statement_rows):
        candidate = _parse_date(row.get("period_end_date"))
        if candidate is None:
            continue
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _statement_age_days(
    statement_rows: list[dict[str, Any]],
    *,
    as_of_date: str | None = None,
    latest_price_row: dict[str, Any] | None = None,
    latest_valuation_row: dict[str, Any] | None = None,
    latest_signal_row: dict[str, Any] | None = None,
) -> int | None:
    """Return age in days of the latest annual normalized statement input.

    Source date used for fundamentals recency:
    - ``statements_norm.period_end_date`` from annual rows only.

    Anchor precedence (first available):
    1. latest signal date
    2. latest valuation date
    3. latest price date
    4. caller-provided as_of_date

    The helper is intentionally deterministic and returns ``None`` when no
    anchor is available; it never falls back to wall-clock time.
    """
    latest_statement = _latest_statement_date(statement_rows)
    if latest_statement is None:
        return None

    anchor = None
    if latest_signal_row:
        anchor = _parse_date(latest_signal_row.get("signal_date"))
    if anchor is None and latest_valuation_row:
        anchor = _parse_date(latest_valuation_row.get("valuation_date"))
    if anchor is None and latest_price_row:
        anchor = _parse_date(latest_price_row.get("price_date"))
    if anchor is None and as_of_date:
        anchor = _parse_date(as_of_date)
    if anchor is None:
        return None
    return (anchor - latest_statement).days


def detect_provider_mix(provider_map: dict[str, str | None]) -> str:
    """Return a deterministic provider-mix label for the current coverage."""
    price_provider = provider_map.get("price")
    fundamentals_provider = provider_map.get("fundamentals")

    if price_provider and not fundamentals_provider:
        return PROVIDER_MIX_PRICE_ONLY
    if not price_provider and not fundamentals_provider:
        return PROVIDER_MIX_INSUFFICIENT

    active = {
        domain: provider
        for domain, provider in provider_map.items()
        if provider
    }
    if not active:
        return PROVIDER_MIX_INSUFFICIENT

    has_primary = False
    has_non_primary = False
    for domain, provider in active.items():
        primary = _PRIMARY_PROVIDER_BY_DOMAIN.get(domain)
        if primary is None:
            continue
        if provider == primary:
            has_primary = True
        else:
            has_non_primary = True

    if has_primary and has_non_primary:
        return PROVIDER_MIX_MIXED
    if has_non_primary:
        return PROVIDER_MIX_FALLBACK
    return PROVIDER_MIX_PRIMARY_ONLY


def classify_company_readiness(
    company: dict[str, Any],
    *,
    as_of_date: str | None = None,
    profile_provider: str | None = None,
    latest_price_row: dict[str, Any] | None = None,
    statement_rows: list[dict[str, Any]] | None = None,
    filing_rows: list[dict[str, Any]] | None = None,
    latest_valuation_row: dict[str, Any] | None = None,
    latest_signal_row: dict[str, Any] | None = None,
    fx_provider: str | None = None,
) -> dict[str, Any]:
    """Classify one company using persisted data and deterministic inputs.

    The function does not call providers or repositories. Callers pass already
    loaded rows and any deterministic provider selections that are not yet
    persisted in the schema, such as the profile provider.
    """
    statement_rows = statement_rows or []
    filing_rows = filing_rows or []
    metadata = _metadata(company)

    selected_profile_provider = (
        profile_provider
        or metadata.get("profile_provider")
        or ("fmp" if _has_profile(company) else None)
    )
    selected_price_provider = (
        str(latest_price_row.get("provider")).strip() if latest_price_row and latest_price_row.get("provider") else None
    )
    selected_fundamentals_provider = _selected_fundamentals_provider(statement_rows)
    selected_filings_provider = _selected_filings_provider(filing_rows)
    selected_fx_provider = fx_provider or metadata.get("fx_provider")

    provider_map = {
        "profile": selected_profile_provider,
        "price": selected_price_provider,
        "fundamentals": selected_fundamentals_provider,
        "filings": selected_filings_provider,
        "fx": selected_fx_provider,
    }

    annual_statements = _annual_statements(statement_rows)
    unique_years = {
        int(row.get("fiscal_year"))
        for row in annual_statements
        if row.get("fiscal_year") is not None
    }

    has_profile = _has_profile(company)
    has_recent_price = _is_recent_price_row(latest_price_row)
    has_supported_fundamentals = bool(annual_statements)
    has_min_statement_history = len(unique_years) >= 2
    has_diluted_shares = any((_safe_float(row.get("diluted_shares")) or 0.0) > 0.0 for row in annual_statements)
    has_fcf_path = any(
        row.get("free_cash_flow") is not None
        or (row.get("cfo") is not None and row.get("capex") is not None)
        for row in annual_statements
    )
    has_viable_fcf_path = any(
        ((_safe_float(row.get("free_cash_flow")) or 0.0) > 0.0)
        or (
            row.get("free_cash_flow") is None
            and row.get("cfo") is not None
            and row.get("capex") is not None
        )
        for row in annual_statements
    )
    has_filings = bool(filing_rows)
    has_recent_valuation = latest_valuation_row is not None
    has_recent_signal = latest_signal_row is not None
    statement_age_days = _statement_age_days(
        statement_rows,
        as_of_date=as_of_date,
        latest_price_row=latest_price_row,
        latest_valuation_row=latest_valuation_row,
        latest_signal_row=latest_signal_row,
    )
    has_stale_fundamentals = (
        statement_age_days is not None and statement_age_days > STALE_FUNDAMENTALS_DAYS
    )

    country = str(company.get("country") or "").strip().upper()
    cik = str(company.get("cik") or "").strip()
    fundamentals_path_supported = has_supported_fundamentals or bool(cik) or country in _US_COUNTRY_CODES
    supported_instrument = _is_supported_instrument(company)

    valuation_diagnostics = _valuation_diagnostics(latest_valuation_row)
    valuation_status = str(valuation_diagnostics.get("valuation_status") or "").strip().lower()

    reason_flags: dict[str, bool] = {
        REASON_MISSING_PRICE: not has_recent_price,
        REASON_MISSING_SUPPORTED_FUNDAMENTALS: not fundamentals_path_supported,
        REASON_NON_US_FUNDAMENTALS: (not fundamentals_path_supported) and bool(country) and country not in _US_COUNTRY_CODES,
        REASON_MISSING_MIN_HISTORY: has_supported_fundamentals and not has_min_statement_history,
        REASON_MISSING_DILUTED_SHARES: has_supported_fundamentals and not has_diluted_shares,
        REASON_MISSING_FCF_PATH: has_supported_fundamentals and not has_fcf_path,
        REASON_NON_VIABLE_FCF: has_fcf_path and not has_viable_fcf_path,
        REASON_VALUATION_BLOCKED: valuation_status == "blocked",
        REASON_PROVIDER_LIMITED: False,
        REASON_UNSUPPORTED_INSTRUMENT: not supported_instrument,
        REASON_VALUATION_PARTIAL: valuation_status == "partial",
        REASON_VALUATION_READY: valuation_status == "ok",
        REASON_STALE_FUNDAMENTALS: has_stale_fundamentals,
    }

    has_core_analysis_inputs = (
        has_recent_price
        and has_supported_fundamentals
        and has_min_statement_history
        and has_diluted_shares
        and has_viable_fcf_path
    )

    if not supported_instrument:
        readiness_status = READINESS_UNSUPPORTED
    elif has_stale_fundamentals:
        readiness_status = READINESS_TRACKING_ONLY
    elif has_recent_price and not fundamentals_path_supported:
        readiness_status = READINESS_TRACKING_ONLY if has_profile else READINESS_PROVIDER_LIMITED
    elif has_core_analysis_inputs and valuation_status not in {"partial", "blocked"}:
        readiness_status = READINESS_ANALYSIS_READY
    elif has_supported_fundamentals:
        readiness_status = READINESS_PARTIAL_ANALYSIS
    elif has_recent_price:
        readiness_status = READINESS_TRACKING_ONLY if has_profile else READINESS_PROVIDER_LIMITED
    else:
        readiness_status = READINESS_PROVIDER_LIMITED

    if readiness_status in {READINESS_PROVIDER_LIMITED, READINESS_TRACKING_ONLY}:
        reason_flags[REASON_PROVIDER_LIMITED] = True

    provider_mix = detect_provider_mix(provider_map)

    limiting_domain: str | None = None
    if readiness_status == READINESS_UNSUPPORTED:
        limiting_domain = "profile"
    elif reason_flags[REASON_MISSING_PRICE]:
        limiting_domain = "price"
    elif (
        reason_flags[REASON_STALE_FUNDAMENTALS]
        or reason_flags[REASON_MISSING_SUPPORTED_FUNDAMENTALS]
        or reason_flags[REASON_MISSING_MIN_HISTORY]
        or reason_flags[REASON_MISSING_DILUTED_SHARES]
        or reason_flags[REASON_MISSING_FCF_PATH]
    ):
        limiting_domain = "fundamentals"

    reason_codes = [code for code in REASON_CODES if reason_flags.get(code, False)]

    return {
        "company_id": company.get("id"),
        "ticker": company.get("ticker"),
        "readiness_status": readiness_status,
        "provider_domains": PROVIDER_DOMAINS,
        "provider_map": provider_map,
        "provider_mix": provider_mix,
        "reason_codes": reason_codes,
        "can_track": has_profile and has_recent_price,
        "can_run_valuation": readiness_status in {READINESS_ANALYSIS_READY, READINESS_PARTIAL_ANALYSIS},
        "can_run_signal": readiness_status in {READINESS_ANALYSIS_READY, READINESS_PARTIAL_ANALYSIS},
        "has_profile": has_profile,
        "has_recent_price": has_recent_price,
        "has_supported_fundamentals": has_supported_fundamentals,
        "has_min_statement_history": has_min_statement_history,
        "has_diluted_shares": has_diluted_shares,
        "has_fcf_path": has_fcf_path,
        "has_filings": has_filings,
        "has_recent_valuation": has_recent_valuation,
        "has_recent_signal": has_recent_signal,
        "statement_age_days": statement_age_days,
        "limiting_domain": limiting_domain,
        "last_evaluated_at": None,
    }


__all__ = [
    "PROVIDER_DOMAINS",
    "PROVIDER_MIXES",
    "READINESS_STATUSES",
    "REASON_CODES",
    "classify_company_readiness",
    "detect_provider_mix",
]