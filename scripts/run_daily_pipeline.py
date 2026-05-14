"""Daily pipeline runner.

Usage:
    python scripts/run_daily_pipeline.py
    python scripts/run_daily_pipeline.py --dry-run
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Allow running as a top-level script before the package is installed.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import typer
from rich.console import Console

from investment_app.config.loader import load_providers, load_watchlist
from investment_app.config.settings import get_settings, _is_placeholder
from investment_app.utils.logging import configure_logging

app = typer.Typer(add_completion=False)
console = Console()
logger = logging.getLogger(__name__)

# Currencies to fetch from ECB in every run.
_ECB_CURRENCIES = ("USD", "GBP", "JPY", "CHF")


def _provider_enabled(providers_config: dict[str, Any], provider_name: str) -> bool:
    """Return True when the provider is enabled in providers.yml."""
    providers = providers_config.get("providers", {})
    provider_config = providers.get(provider_name, {})
    return bool(provider_config.get("enabled", False))


def _load_watchlist_companies() -> list[dict[str, Any]]:
    """Return the YAML watchlist companies list."""
    watchlist = load_watchlist()
    return watchlist.get("companies", [])


def _load_live_companies(repo_module: Any) -> tuple[list[dict[str, Any]], str]:
    """Load companies from Supabase watchlist, falling back to YAML on failure.

    Phase 9A authority model (two tiers only)
    -----------------------------------------
    1. ``list_watchlist_active_companies()`` — sole eligibility source.
       ``watchlist_companies.active = true`` is the authoritative state.

       * Success with a non-empty list → process those companies.
       * Success with an **empty** list → process zero companies.  This is an
         intentional "all removed" state; YAML is NOT consulted.

    2. YAML watchlist (``watchlist.yml``) — technical fallback only.
       Reached only when ``list_watchlist_active_companies()`` raises (e.g.
       Supabase unreachable, wrong credentials).  ``companies.active`` is
       never consulted as a fallback.
    """
    try:
        companies = repo_module.list_watchlist_active_companies()
        # Empty list is authoritative: all memberships were soft-removed.
        return companies, "supabase-watchlist"
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load companies via watchlist_companies: %s — "
            "falling back to YAML watchlist",
            exc,
        )
    return _load_watchlist_companies(), "watchlist-fallback"


def _resolve_company_id(company: dict[str, Any], repo_module: Any) -> str | None:
    """Resolve the company UUID from the row itself or by ticker lookup."""
    company_id = company.get("id")
    if company_id:
        return company_id
    ticker = company.get("ticker", "")
    if not ticker:
        return None
    match = repo_module.get_company_by_ticker(ticker)
    if not match:
        return None
    return match.get("id")


def _extract_company_profile_update(payload: Any) -> dict[str, Any] | None:
    """Map the first FMP profile entry into the ``companies`` table shape."""
    if isinstance(payload, list) and payload:
        profile = payload[0]
    elif isinstance(payload, dict):
        profile = payload
    else:
        return None

    if not isinstance(profile, dict):
        return None

    update: dict[str, Any] = {}
    mapping = {
        "companyName": "name",
        "country": "country",
        "currency": "currency",
        "sector": "sector",
        "industry": "industry",
        "cik": "cik",
    }
    for source_key, target_key in mapping.items():
        value = profile.get(source_key)
        if value:
            update[target_key] = value

    exchange = profile.get("exchangeShortName") or profile.get("exchange")
    if exchange:
        update["exchange"] = exchange

    return update or None


def _build_news_query(company: dict[str, Any]) -> str:
    """Build a simple GDELT query from company name and ticker."""
    ticker = company.get("ticker", "")
    name = company.get("name", "")
    if name and ticker:
        return f'"{name}" OR {ticker}'
    return name or ticker


# ── Phase 9B: process pending watchlist add requests ─────────────────────────


_TICKER_VALID_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")


def _is_valid_ticker(ticker: str) -> bool:
    """Return True when *ticker* is non-empty and contains only valid characters."""
    return bool(ticker) and all(c in _TICKER_VALID_CHARS for c in ticker.upper())


def _process_pending_add_requests(
    repo_module: Any,
    fmp: Any | None,
    run_id: str,
    metrics: dict[str, int],
) -> None:
    """Process all pending watchlist add requests before company loading.

    For each pending request the pipeline:
    1. Validates the ticker format.
    2. Checks for an existing company (by ticker+exchange or ticker alone).
    3. Checks for an existing watchlist membership (active or inactive).
    4. Creates a new company from the FMP profile when needed.
    5. Creates or reactivates the watchlist membership.
    6. Marks the request approved / rejected / failed accordingly.

    New metrics keys updated in *metrics*:
      ``add_requests_processed``, ``add_requests_approved``,
      ``add_requests_rejected``, ``add_requests_failed``.
    """
    try:
        requests = repo_module.list_pending_watchlist_add_requests()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not load pending add requests (%s) — skipping stage.",
            type(exc).__name__,
        )
        repo_module.log_pipeline_event(
            run_id,
            stage="add_requests",
            level="warning",
            message="Could not load pending add requests — stage skipped.",
            details={"error_type": type(exc).__name__},
        )
        return

    if not requests:
        return

    repo_module.log_pipeline_event(
        run_id,
        stage="add_requests",
        message=f"Processing {len(requests)} pending add request(s).",
    )

    for req in requests:
        req_id = req["id"]
        raw_ticker = req.get("requested_ticker", "")
        raw_exchange = req.get("requested_exchange")
        watchlist_id = req["watchlist_id"]
        ticker = raw_ticker.upper().strip()
        exchange = raw_exchange.upper().strip() if raw_exchange else None

        metrics["add_requests_processed"] += 1

        try:
            # ── Step 1: validate ticker format ────────────────────────────────
            if not _is_valid_ticker(ticker):
                repo_module.reject_watchlist_add_request(
                    req_id,
                    "invalid_ticker",
                    f"Ticker '{ticker}' contains invalid characters.",
                )
                metrics["add_requests_rejected"] += 1
                repo_module.log_pipeline_event(
                    run_id,
                    stage="add_requests",
                    level="warning",
                    message=f"Rejected request for '{ticker}': invalid ticker format.",
                    details={"request_id": req_id, "error_code": "invalid_ticker"},
                )
                continue

            # ── Step 2: look up existing company ─────────────────────────────
            if exchange:
                existing_company = repo_module.get_company_by_ticker_exchange(ticker, exchange)
                if existing_company is None:
                    # Exchange was specified but does not match — check by ticker alone
                    # to detect exchange mismatch vs completely new ticker.
                    all_matching = repo_module.list_companies_by_ticker(ticker)
                    if all_matching:
                        # Ticker exists on a different exchange.
                        repo_module.reject_watchlist_add_request(
                            req_id,
                            "exchange_mismatch",
                            (
                                f"Ticker '{ticker}' exists on "
                                f"{all_matching[0].get('exchange', 'another exchange')}, "
                                f"not '{exchange}'."
                            ),
                        )
                        metrics["add_requests_rejected"] += 1
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="add_requests",
                            level="warning",
                            message=(
                                f"Rejected request for '{ticker}': "
                                "exchange mismatch."
                            ),
                            details={"request_id": req_id, "error_code": "exchange_mismatch"},
                        )
                        continue
                    # else: ticker doesn't exist at all — fall through to FMP.
            else:
                all_matching = repo_module.list_companies_by_ticker(ticker)
                if len(all_matching) > 1:
                    # Ambiguous: ticker exists on multiple exchanges.
                    repo_module.reject_watchlist_add_request(
                        req_id,
                        "ambiguous_ticker",
                        (
                            f"Ticker '{ticker}' exists on multiple exchanges. "
                            "Please specify an exchange."
                        ),
                    )
                    metrics["add_requests_rejected"] += 1
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="add_requests",
                        level="warning",
                        message=(
                            f"Rejected request for '{ticker}': "
                            "ambiguous ticker (multiple exchanges)."
                        ),
                        details={"request_id": req_id, "error_code": "ambiguous_ticker"},
                    )
                    continue
                existing_company = all_matching[0] if all_matching else None

            # ── Step 3: if company exists, check/manage membership ────────────
            if existing_company:
                company_id = existing_company["id"]
                membership = repo_module.get_watchlist_membership(watchlist_id, company_id)

                if membership and membership.get("active"):
                    # Already on the watchlist — reject as duplicate.
                    repo_module.reject_watchlist_add_request(
                        req_id,
                        "already_active",
                        f"'{ticker}' is already active in this watchlist.",
                    )
                    metrics["add_requests_rejected"] += 1
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="add_requests",
                        level="warning",
                        message=f"Rejected request for '{ticker}': already active.",
                        details={"request_id": req_id, "error_code": "already_active"},
                    )
                    continue

                if membership and not membership.get("active"):
                    # Inactive membership — reactivate it.
                    repo_module.reactivate_watchlist_company(membership["id"])
                    repo_module.approve_watchlist_add_request(req_id, company_id)
                    metrics["add_requests_approved"] += 1
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="add_requests",
                        message=(
                            f"Approved request for '{ticker}': "
                            "reactivated existing inactive membership."
                        ),
                        details={"request_id": req_id, "company_id": company_id},
                    )
                    continue

                # No membership — create one.
                repo_module.create_watchlist_membership(watchlist_id, company_id)
                repo_module.approve_watchlist_add_request(req_id, company_id)
                metrics["add_requests_approved"] += 1
                repo_module.log_pipeline_event(
                    run_id,
                    stage="add_requests",
                    message=(
                        f"Approved request for '{ticker}': "
                        "created new watchlist membership for existing company."
                    ),
                    details={"request_id": req_id, "company_id": company_id},
                )
                continue

            # ── Step 4: company does not exist — validate via FMP ─────────────
            if fmp is None:
                repo_module.fail_watchlist_add_request(
                    req_id,
                    "provider_unavailable",
                    "FMP provider is not configured; cannot validate new ticker.",
                )
                metrics["add_requests_failed"] += 1
                repo_module.log_pipeline_event(
                    run_id,
                    stage="add_requests",
                    level="warning",
                    message=f"Failed request for '{ticker}': FMP not available.",
                    details={"request_id": req_id, "error_code": "provider_unavailable"},
                )
                continue

            try:
                profile_resp = fmp.get_profile(ticker)
            except Exception as fmp_exc:  # noqa: BLE001
                repo_module.fail_watchlist_add_request(
                    req_id,
                    "fmp_request_failed",
                    "Provider request failed; please try again later.",
                )
                metrics["add_requests_failed"] += 1
                logger.warning(
                    "FMP profile fetch failed for %s (%s)",
                    ticker,
                    type(fmp_exc).__name__,
                )
                repo_module.log_pipeline_event(
                    run_id,
                    stage="add_requests",
                    level="error",
                    message=f"Failed request for '{ticker}': FMP request error.",
                    details={
                        "request_id": req_id,
                        "error_code": "fmp_request_failed",
                        "error_type": type(fmp_exc).__name__,
                    },
                )
                continue

            if not profile_resp.success:
                repo_module.fail_watchlist_add_request(
                    req_id,
                    "provider_unavailable",
                    "Provider returned an error; please try again later.",
                )
                metrics["add_requests_failed"] += 1
                repo_module.log_pipeline_event(
                    run_id,
                    stage="add_requests",
                    level="error",
                    message=f"Failed request for '{ticker}': provider error.",
                    details={"request_id": req_id, "error_code": "provider_unavailable"},
                )
                continue

            payload = profile_resp.payload
            if not payload:
                repo_module.reject_watchlist_add_request(
                    req_id,
                    "invalid_ticker",
                    f"Ticker '{ticker}' was not found in the data provider.",
                )
                metrics["add_requests_rejected"] += 1
                repo_module.log_pipeline_event(
                    run_id,
                    stage="add_requests",
                    level="warning",
                    message=f"Rejected request for '{ticker}': not found in FMP.",
                    details={"request_id": req_id, "error_code": "invalid_ticker"},
                )
                continue

            # ── Resolve profile from potentially multi-profile response ─────
            # FMP may return multiple profiles when a ticker trades on several
            # exchanges.  Blindly using payload[0] would silently create the
            # wrong company row, so we handle every case explicitly.
            profiles = payload if isinstance(payload, list) else [payload]

            if len(profiles) > 1:
                if exchange:
                    matched = [
                        p for p in profiles
                        if (p.get("exchangeShortName") or p.get("exchange") or "").upper().strip() == exchange
                    ]
                    if len(matched) == 1:
                        profile = matched[0]
                    elif len(matched) == 0:
                        repo_module.reject_watchlist_add_request(
                            req_id,
                            "exchange_mismatch",
                            f"FMP reports '{ticker}' on multiple exchanges, none matching '{exchange}'.",
                        )
                        metrics["add_requests_rejected"] += 1
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="add_requests",
                            level="warning",
                            message=f"Rejected request for '{ticker}': no FMP profile matches exchange '{exchange}'.",
                            details={"request_id": req_id, "error_code": "exchange_mismatch"},
                        )
                        continue
                    else:
                        # Multiple profiles even after filtering by exchange — ambiguous.
                        repo_module.reject_watchlist_add_request(
                            req_id,
                            "ambiguous_ticker",
                            f"Ticker '{ticker}' has multiple ambiguous listings on '{exchange}'.",
                        )
                        metrics["add_requests_rejected"] += 1
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="add_requests",
                            level="warning",
                            message=f"Rejected request for '{ticker}': ambiguous FMP listings.",
                            details={"request_id": req_id, "error_code": "ambiguous_ticker"},
                        )
                        continue
                else:
                    repo_module.reject_watchlist_add_request(
                        req_id,
                        "ambiguous_ticker",
                        f"Ticker '{ticker}' exists on multiple exchanges. Specify an exchange to disambiguate.",
                    )
                    metrics["add_requests_rejected"] += 1
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="add_requests",
                        level="warning",
                        message=f"Rejected request for '{ticker}': FMP returned multiple profiles.",
                        details={"request_id": req_id, "error_code": "ambiguous_ticker"},
                    )
                    continue
            else:
                profile = profiles[0]

            fmp_exchange = (profile.get("exchangeShortName") or profile.get("exchange") or "")
            fmp_exchange = fmp_exchange.upper().strip()

            # If the user specified an exchange and it does not match the
            # single resolved profile, reject with exchange_mismatch.
            if exchange and fmp_exchange and exchange != fmp_exchange:
                repo_module.reject_watchlist_add_request(
                    req_id,
                    "exchange_mismatch",
                    (
                        f"FMP reports '{ticker}' on '{fmp_exchange}', "
                        f"not '{exchange}'."
                    ),
                )
                metrics["add_requests_rejected"] += 1
                repo_module.log_pipeline_event(
                    run_id,
                    stage="add_requests",
                    level="warning",
                    message=f"Rejected request for '{ticker}': FMP exchange mismatch.",
                    details={"request_id": req_id, "error_code": "exchange_mismatch"},
                )
                continue

            # ── Step 5: create company + membership ───────────────────────────
            new_company = repo_module.create_company(
                ticker=ticker,
                name=profile.get("companyName") or ticker,
                exchange=fmp_exchange or exchange or None,
                country=profile.get("country") or None,
                currency=profile.get("currency") or None,
                sector=profile.get("sector") or None,
                industry=profile.get("industry") or None,
                cik=profile.get("cik") or None,
            )
            new_company_id = new_company["id"]
            repo_module.create_watchlist_membership(watchlist_id, new_company_id)
            repo_module.approve_watchlist_add_request(req_id, new_company_id)
            metrics["add_requests_approved"] += 1
            repo_module.log_pipeline_event(
                run_id,
                stage="add_requests",
                message=(
                    f"Approved request for '{ticker}': "
                    "created new company and watchlist membership."
                ),
                details={"request_id": req_id, "company_id": new_company_id},
            )

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Unexpected error processing add request %s (%s)",
                req_id,
                type(exc).__name__,
            )
            try:
                repo_module.fail_watchlist_add_request(
                    req_id,
                    "internal_error",
                    "An unexpected error occurred; please try again later.",
                )
                metrics["add_requests_failed"] += 1
            except Exception:  # noqa: BLE001
                pass
            repo_module.log_pipeline_event(
                run_id,
                stage="add_requests",
                level="error",
                message=f"Unexpected error processing add request {req_id}.",
                details={"request_id": req_id, "error_type": type(exc).__name__},
            )




def _build_sec_document_url(
    cik: str | int | None,
    accession_number: str | None,
    primary_document: str | None,
) -> str | None:
    """Build a full SEC archive document URL when the payload contains enough data."""
    if not cik or not accession_number or not primary_document:
        return None
    cik_str = str(cik).lstrip("0")
    accession_no_dashes = accession_number.replace("-", "")
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_str}/{accession_no_dashes}/{primary_document}"
    )


def _try_twelve_price_fallback(
    *,
    twelve: Any | None,
    company_id: str,
    ticker: str,
    currency: str,
    fallback_reason: str,
    run_id: str,
    metrics: dict[str, int],
    repo_module: Any,
    store_raw_response_fn: Any,
    normalize_twelve_fn: Any,
) -> None:
    """Attempt Twelve Data as a price_eod fallback (Phase 10B).

    Emits safe compact pipeline events.  Never raises — any failure is caught
    and logged so the rest of the company pipeline continues uninterrupted.

    Preconditions already evaluated by the caller:
    - FMP price data is unusable for this run/ticker.
    """
    # ── Guard: Twelve Data connector not configured ───────────────────────────
    if twelve is None:
        repo_module.log_pipeline_event(
            run_id,
            stage="price_fallback",
            level="warning",
            company_id=company_id,
            message=f"Twelve Data price fallback unavailable for {ticker}: provider not configured.",
            details={
                "ticker": ticker,
                "event": "price_fallback_unavailable_provider_disabled",
                "fallback_reason": fallback_reason,
                "provider": "twelve_data",
            },
        )
        return

    # ── Started ───────────────────────────────────────────────────────────────
    repo_module.log_pipeline_event(
        run_id,
        stage="price_fallback",
        company_id=company_id,
        message=f"Twelve Data price fallback started for {ticker}.",
        details={
            "ticker": ticker,
            "event": "price_fallback_started",
            "fallback_reason": fallback_reason,
            "provider": "twelve_data",
        },
    )

    # ── Stage 1: fetch time-series from Twelve Data ───────────────────────────
    try:
        resp = twelve.get_time_series(ticker)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Twelve Data price fallback fetch error for %s (%s)",
            ticker,
            type(exc).__name__,
        )
        repo_module.log_pipeline_event(
            run_id,
            stage="price_fallback",
            level="error",
            company_id=company_id,
            message=f"Twelve Data price fallback fetch error for {ticker}.",
            details={
                "ticker": ticker,
                "event": "price_fallback_failed",
                "stage": "twelve_fetch",
                "fallback_reason": fallback_reason,
                "provider": "twelve_data",
                "error_type": type(exc).__name__,
            },
        )
        return

    if not resp.success or not resp.payload:
        repo_module.log_pipeline_event(
            run_id,
            stage="price_fallback",
            level="warning",
            company_id=company_id,
            message=f"Twelve Data price fallback failed for {ticker}: fetch unsuccessful.",
            details={
                "ticker": ticker,
                "event": "price_fallback_failed",
                "stage": "twelve_fetch",
                "fallback_reason": fallback_reason,
                "provider": "twelve_data",
                "status_code": resp.status_code,
            },
        )
        return

    # ── Stage 2: persist raw payload ─────────────────────────────────────────
    try:
        raw_id = store_raw_response_fn(resp, company_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Twelve Data price fallback raw-store error for %s (%s)",
            ticker,
            type(exc).__name__,
        )
        repo_module.log_pipeline_event(
            run_id,
            stage="price_fallback",
            level="error",
            company_id=company_id,
            message=f"Twelve Data price fallback raw-store error for {ticker}.",
            details={
                "ticker": ticker,
                "event": "price_fallback_failed",
                "stage": "raw_payload_read",
                "fallback_reason": fallback_reason,
                "provider": "twelve_data",
                "error_type": type(exc).__name__,
            },
        )
        return

    # ── Stage 3: normalise ────────────────────────────────────────────────────
    try:
        rows = normalize_twelve_fn(
            resp.payload,
            company_id,
            ticker,
            currency,
            raw_payload_id=raw_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Twelve Data price fallback normalize error for %s (%s)",
            ticker,
            type(exc).__name__,
        )
        repo_module.log_pipeline_event(
            run_id,
            stage="price_fallback",
            level="error",
            company_id=company_id,
            message=f"Twelve Data price fallback normalise error for {ticker}.",
            details={
                "ticker": ticker,
                "event": "price_fallback_failed",
                "stage": "price_normalize",
                "fallback_reason": fallback_reason,
                "provider": "twelve_data",
                "error_type": type(exc).__name__,
            },
        )
        return

    if not rows:
        repo_module.log_pipeline_event(
            run_id,
            stage="price_fallback",
            level="warning",
            company_id=company_id,
            message=f"Twelve Data price fallback produced no rows for {ticker}.",
            details={
                "ticker": ticker,
                "event": "price_fallback_no_rows",
                "fallback_reason": fallback_reason,
                "provider": "twelve_data",
            },
        )
        return

    # ── Stage 4: upsert ───────────────────────────────────────────────────────
    try:
        upserted = repo_module.upsert_price_eod(rows)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Twelve Data price fallback upsert error for %s (%s)",
            ticker,
            type(exc).__name__,
        )
        repo_module.log_pipeline_event(
            run_id,
            stage="price_fallback",
            level="error",
            company_id=company_id,
            message=f"Twelve Data price fallback upsert error for {ticker}.",
            details={
                "ticker": ticker,
                "event": "price_fallback_failed",
                "stage": "price_upsert",
                "fallback_reason": fallback_reason,
                "provider": "twelve_data",
                "error_type": type(exc).__name__,
            },
        )
        return

    metrics["price_fallback_upserted"] += upserted
    repo_module.log_pipeline_event(
        run_id,
        stage="price_fallback",
        company_id=company_id,
        message=f"Twelve Data price fallback succeeded for {ticker}: {upserted} rows upserted.",
        details={
            "ticker": ticker,
            "event": "price_fallback_succeeded",
            "fallback_reason": fallback_reason,
            "provider": "twelve_data",
            "rows_normalized": len(rows),
            "rows_upserted": upserted,
        },
    )


def _try_sec_statements_fallback(
    *,
    sec: Any | None,
    cik: str,
    company_id: str,
    ticker: str,
    currency: str,
    fallback_reason: str,
    run_id: str,
    metrics: dict[str, int],
    repo_module: Any,
    store_raw_response_fn: Any,
    normalize_sec_fn: Any,
) -> None:
    """Attempt SEC companyfacts as annual statements fallback (Phase 10A).

    Emits safe compact pipeline events.  Never raises — any failure is caught
    and logged so the rest of the company pipeline continues uninterrupted.

    Preconditions already evaluated by the caller:
    - FMP annual statements are unusable for this run/ticker.

    This function evaluates:
    - SEC connector available.
    - Valid CIK present.
    Then it fetches, normalises, and upserts up to 5 years of annual statements.
    """
    # ── Guard: missing CIK ────────────────────────────────────────────────────
    if not cik:
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="warning",
            company_id=company_id,
            message=f"SEC fallback unavailable for {ticker}: missing CIK.",
            details={
                "ticker": ticker,
                "event": "sec_fallback_unavailable_missing_cik",
                "fallback_reason": fallback_reason,
            },
        )
        return

    # ── Guard: SEC connector not configured ───────────────────────────────────
    if sec is None:
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="warning",
            company_id=company_id,
            message=f"SEC fallback unavailable for {ticker}: provider not configured.",
            details={
                "ticker": ticker,
                "event": "sec_fallback_unavailable_provider_disabled",
                "fallback_reason": fallback_reason,
            },
        )
        return

    # ── Started ───────────────────────────────────────────────────────────────
    repo_module.log_pipeline_event(
        run_id,
        stage="sec_fallback",
        company_id=company_id,
        message=f"SEC fundamentals fallback started for {ticker}.",
        details={
            "ticker": ticker,
            "event": "sec_fallback_started",
            "fallback_reason": fallback_reason,
        },
    )

    # ── Stage 1a: fetch companyfacts from SEC ────────────────────────────────
    try:
        facts_resp = sec.get_company_facts(cik)
    except Exception as exc:  # noqa: BLE001
        logger.error("SEC fallback fetch error for %s (%s)", ticker, type(exc).__name__)
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="error",
            company_id=company_id,
            message=f"SEC fallback fetch error for {ticker}.",
            details={
                "ticker": ticker,
                "cik": cik,
                "event": "sec_fallback_failed",
                "stage": "sec_fetch",
                "fallback_reason": fallback_reason,
                "error_type": type(exc).__name__,
            },
        )
        return

    if not facts_resp.success or not facts_resp.payload:
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="warning",
            company_id=company_id,
            message=f"SEC fallback failed for {ticker}: companyfacts fetch unsuccessful.",
            details={
                "ticker": ticker,
                "cik": cik,
                "event": "sec_fallback_failed",
                "stage": "sec_fetch",
                "fallback_reason": fallback_reason,
                "status_code": facts_resp.status_code,
            },
        )
        return

    # ── Stage 1b: persist raw payload ────────────────────────────────────────
    try:
        raw_payload_id = store_raw_response_fn(facts_resp, company_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("SEC fallback raw store error for %s (%s)", ticker, type(exc).__name__)
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="error",
            company_id=company_id,
            message=f"SEC fallback raw payload store error for {ticker}.",
            details={
                "ticker": ticker,
                "cik": cik,
                "event": "sec_fallback_failed",
                "stage": "raw_payload_read",
                "fallback_reason": fallback_reason,
                "error_type": type(exc).__name__,
            },
        )
        return

    # ── Stage 2: normalize ────────────────────────────────────────────────────
    try:
        sec_rows, diag = normalize_sec_fn(
            facts_resp.payload,
            company_id,
            ticker,
            cik,
            currency=currency,
            fallback_reason=fallback_reason,
            raw_payload_id=raw_payload_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("SEC fallback normalize error for %s (%s)", ticker, type(exc).__name__)
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="error",
            company_id=company_id,
            message=f"SEC fallback normalize error for {ticker}.",
            details={
                "ticker": ticker,
                "event": "sec_fallback_failed",
                "stage": "sec_normalize",
                "fallback_reason": fallback_reason,
                "error_type": type(exc).__name__,
            },
        )
        return

    if not sec_rows:
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="warning",
            company_id=company_id,
            message=f"SEC fallback yielded no usable rows for {ticker}.",
            details={
                "ticker": ticker,
                "event": "sec_fallback_no_rows",
                "fallback_reason": fallback_reason,
                "missing_fields": diag.get("missing_fields", []),
            },
        )
        return

    # ── Stage 3: upsert statements_norm ─────────────────────────────────────
    try:
        upserted = repo_module.upsert_statements_norm(sec_rows)
    except Exception as exc:  # noqa: BLE001
        logger.error("SEC fallback upsert error for %s (%s)", ticker, type(exc).__name__)
        repo_module.log_pipeline_event(
            run_id,
            stage="sec_fallback",
            level="error",
            company_id=company_id,
            message=f"SEC fallback statements upsert error for {ticker}.",
            details={
                "ticker": ticker,
                "cik": cik,
                "event": "sec_fallback_failed",
                "stage": "statements_upsert",
                "fallback_reason": fallback_reason,
                "error_type": type(exc).__name__,
                "rows_normalized": diag.get("rows_normalized", 0),
            },
        )
        return

    metrics["sec_fallback_upserted"] += upserted

    # Decide succeeded vs partial based on essential field coverage.
    _essential = {"revenue", "net_income", "total_assets"}
    missing = set(diag.get("missing_fields", []))
    event_name = (
        "sec_fallback_partial"
        if _essential & missing
        else "sec_fallback_succeeded"
    )

    repo_module.log_pipeline_event(
        run_id,
        stage="sec_fallback",
        company_id=company_id,
        message=(
            f"SEC fallback {event_name.replace('sec_fallback_', '')} for {ticker}: "
            f"{upserted} rows upserted."
        ),
        details={
            "ticker": ticker,
            "event": event_name,
            "fallback_reason": fallback_reason,
            "rows_normalized": diag.get("rows_normalized", 0),
            "missing_fields": diag.get("missing_fields", []),
            "weak_fallbacks": diag.get("weak_fallbacks", []),
        },
    )


def _run_live_pipeline(
    *,
    repo_module: Any,
    providers_config: dict[str, Any],
    fmp: Any | None,
    sec: Any | None,
    ecb: Any | None,
    gdelt: Any | None,
    twelve: Any | None = None,
    store_raw_response_fn: Any,
    normalize_prices_fn: Any,
    normalize_statements_fn: Any,
    normalize_news_fn: Any,
    compute_features_fn: Any | None = None,
    compute_valuation_fn: Any | None = None,
    compute_qualitative_fn: Any | None = None,
    compute_signal_fn: Any | None = None,
    process_alerts_fn: Any | None = None,
    settings: Any | None = None,
) -> dict[str, int]:
    """Run the live ingestion and Phases 3-7 pipeline flow."""
    pipeline_run = repo_module.insert_pipeline_run(run_type="daily")
    run_id = pipeline_run["id"]
    metrics: dict[str, int] = {
        "companies_processed": 0,
        "profiles_updated": 0,
        "prices_upserted": 0,
        "statements_upserted": 0,
        "filings_upserted": 0,
        "fx_rates_upserted": 0,
        "news_upserted": 0,
        "ratios_upserted": 0,
        "valuation_runs_upserted": 0,
        "qualitative_scores_upserted": 0,
        "signal_runs_upserted": 0,
        "alerts_sent": 0,
        "alert_history_written": 0,
        "alerts_deduplicated": 0,
        # Phase 9B
        "add_requests_processed": 0,
        "add_requests_approved": 0,
        "add_requests_rejected": 0,
        "add_requests_failed": 0,
        # Phase 10A
        "sec_fallback_upserted": 0,
        # Phase 10B
        "price_fallback_upserted": 0,
        # Phase 10C
        "readiness_classified": 0,
        "readiness_skipped_valuation": 0,
        "readiness_skipped_signal": 0,
        "readiness_errors": 0,
    }

    try:
        # ── Phase 9B: process pending add requests ────────────────────────────
        _process_pending_add_requests(repo_module, fmp, run_id, metrics)

        companies, company_source = _load_live_companies(repo_module)
        console.print(f"Watchlist   : {len(companies)} companies")
        repo_module.log_pipeline_event(
            run_id,
            stage="startup",
            message=f"Loaded {len(companies)} active companies from {company_source}.",
        )

        if not companies:
            repo_module.finish_pipeline_run(
                run_id,
                status="success",
                message="No active companies found.",
                metrics=metrics,
            )
            return metrics

        gdelt_enabled = _provider_enabled(providers_config, "gdelt") and gdelt is not None
        if not gdelt_enabled:
            repo_module.log_pipeline_event(
                run_id,
                stage="news",
                message="News ingestion skipped because GDELT is disabled.",
            )

        for company in companies:
            ticker: str = company.get("ticker", "")
            cik: str = company.get("cik", "")
            currency: str = company.get("currency", "USD")
            company_id = _resolve_company_id(company, repo_module)

            if not company_id:
                repo_module.log_pipeline_event(
                    run_id,
                    stage="company",
                    level="warning",
                    message=f"Skipping {ticker or 'unknown'} because no company row was found.",
                )
                continue

            repo_module.log_pipeline_event(
                run_id,
                stage="company",
                message=f"Processing {ticker}.",
                company_id=company_id,
            )

            try:
                if fmp is not None:
                    profile_resp = fmp.get_profile(ticker)
                    profile_raw_id = store_raw_response_fn(profile_resp, company_id)
                    if profile_resp.success and profile_resp.payload:
                        profile_update = _extract_company_profile_update(profile_resp.payload)
                        if profile_update:
                            repo_module.update_company_profile(company_id, profile_update)
                            metrics["profiles_updated"] += 1

                    price_resp = fmp.get_historical_prices(ticker)
                    price_raw_id = store_raw_response_fn(price_resp, company_id)
                    price_rows: list[Any] = []
                    if price_resp.success and price_resp.payload:
                        price_rows = normalize_prices_fn(
                            price_resp.payload,
                            company_id,
                            ticker,
                            currency,
                            price_raw_id,
                        )
                        metrics["prices_upserted"] += repo_module.upsert_price_eod(price_rows)

                    # ── Phase 10B: Twelve Data price fallback ─────────────────
                    from investment_app.etl.normalize_prices import (
                        fmp_prices_need_fallback,
                        normalize_twelve_data_prices as _normalize_twelve_prices,
                    )
                    needs_price_fallback, price_fallback_reason = fmp_prices_need_fallback(
                        price_resp, price_rows
                    )
                    if needs_price_fallback:
                        _try_twelve_price_fallback(
                            twelve=twelve,
                            company_id=company_id,
                            ticker=ticker,
                            currency=currency,
                            fallback_reason=price_fallback_reason,
                            run_id=run_id,
                            metrics=metrics,
                            repo_module=repo_module,
                            store_raw_response_fn=store_raw_response_fn,
                            normalize_twelve_fn=_normalize_twelve_prices,
                        )

                    inc_resp = fmp.get_income_statement(ticker, period="annual", limit=5)
                    bal_resp = fmp.get_balance_sheet(ticker, period="annual", limit=5)
                    cf_resp = fmp.get_cash_flow(ticker, period="annual", limit=5)
                    for resp in (inc_resp, bal_resp, cf_resp):
                        store_raw_response_fn(resp, company_id)
                    stmt_rows = normalize_statements_fn(
                        inc_resp.payload,
                        bal_resp.payload,
                        cf_resp.payload,
                        company_id,
                        ticker,
                        currency,
                    )
                    metrics["statements_upserted"] += repo_module.upsert_statements_norm(
                        stmt_rows
                    )

                    # ── Phase 10A: SEC fundamentals fallback ──────────────────
                    from investment_app.etl.normalize_sec_companyfacts import (
                        fmp_statements_need_fallback,
                        normalize_sec_companyfacts_annual as _normalize_sec_annual,
                    )
                    needs_fallback, fallback_reason = fmp_statements_need_fallback(
                        inc_resp, bal_resp, cf_resp, stmt_rows
                    )
                    if needs_fallback:
                        _try_sec_statements_fallback(
                            sec=sec,
                            cik=cik,
                            company_id=company_id,
                            ticker=ticker,
                            currency=currency,
                            fallback_reason=fallback_reason,
                            run_id=run_id,
                            metrics=metrics,
                            repo_module=repo_module,
                            store_raw_response_fn=store_raw_response_fn,
                            normalize_sec_fn=_normalize_sec_annual,
                        )

                if sec is not None and cik:
                    sub_resp = sec.get_submissions(cik)
                    sub_raw_id = store_raw_response_fn(sub_resp, company_id)
                    if sub_resp.success and sub_resp.payload:
                        filing_rows = _extract_filings_index(
                            sub_resp.payload,
                            company_id,
                            ticker,
                            raw_payload_id=sub_raw_id,
                        )
                        metrics["filings_upserted"] += repo_module.upsert_filings_index(
                            filing_rows
                        )
                    # SEC companyfacts are now fetched lazily in
                    # _try_sec_statements_fallback only when needed.

                if gdelt_enabled:
                    news_resp = gdelt.search_news(_build_news_query(company), max_records=10)
                    news_raw_id = store_raw_response_fn(news_resp, company_id)
                    if news_resp.success and news_resp.payload:
                        news_rows = normalize_news_fn(
                            news_resp.payload,
                            company_id,
                            ticker,
                            news_raw_id,
                        )
                        metrics["news_upserted"] += repo_module.upsert_news_events(news_rows)

                metrics["companies_processed"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Error processing %s (%s)", ticker, type(exc).__name__)
                repo_module.log_pipeline_event(
                    run_id,
                    stage="company",
                    level="error",
                    company_id=company_id,
                    message=f"Error processing {ticker}.",
                    details={"error_type": type(exc).__name__},
                )
                console.print(f"  [red]Error for {ticker}: {type(exc).__name__}[/red]")

        if ecb is not None:
            repo_module.log_pipeline_event(
                run_id,
                stage="fx",
                message="Fetching ECB FX rates.",
            )
            for currency in _ECB_CURRENCIES:
                try:
                    fx_resp = ecb.get_fx_rate(currency, last_n=5)
                    store_raw_response_fn(fx_resp, company_id=None)
                    if fx_resp.success and fx_resp.payload:
                        fx_rows = _extract_ecb_fx_rates(fx_resp.payload, currency)
                        metrics["fx_rates_upserted"] += repo_module.upsert_fx_rates(fx_rows)
                except Exception as exc:  # noqa: BLE001
                    logger.error("ECB FX fetch failed for %s (%s)", currency, type(exc).__name__)
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="fx",
                        level="error",
                        message=f"FX fetch failed for {currency}.",
                        details={"error_type": type(exc).__name__, "currency": currency},
                    )

        # ── Phase 3: feature / ratio computation ─────────────────────────────────
        # factor_date is shared by Phases 3, 4, and 5; initialise it here so
        # later stanzas can use it even when earlier phases are skipped.
        from datetime import date as _date

        factor_date = _date.today().isoformat()

        if compute_features_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="features",
                message="Starting ratio and feature computation.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                currency: str = company.get("currency", "USD")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    ratio_row = compute_features_fn(
                        company_id, repo_module, factor_date,
                        company_currency=currency,
                    )
                    if ratio_row:
                        n = repo_module.upsert_ratios_factors([ratio_row])
                        metrics["ratios_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="features",
                            company_id=company_id,
                            message=f"Ratios computed for {ticker}.",
                            details={"factor_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="features",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped ratios for {ticker}: "
                                "insufficient data."
                            ),
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Feature computation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="features",
                        level="error",
                        company_id=company_id,
                        message=f"Ratio computation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 10C: readiness classification ──────────────────────────────
        from investment_app.pipeline_readiness import (
            classify_company_for_pipeline as _classify_readiness,
            should_skip_valuation as _should_skip_valuation,
            should_skip_signal as _should_skip_signal,
        )
        _readiness_by_company_id: dict[str, dict[str, Any]] = {}
        if companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="readiness",
                message="Starting readiness classification.",
            )
            for company in companies:
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                _r = _classify_readiness(
                    company, company_id,
                    repo_module=repo_module,
                    run_id=run_id,
                    factor_date=factor_date,
                    metrics=metrics,
                )
                if _r is not None:
                    _readiness_by_company_id[company_id] = _r

        # ── Phase 4: valuation ────────────────────────────────────────────────
        if compute_valuation_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="valuation",
                message="Starting valuation computation.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                currency: str = company.get("currency", "USD")
                sector: str = company.get("sector", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                # ── Phase 10C: readiness gate ─────────────────────────────────
                _readiness = _readiness_by_company_id.get(company_id)
                if _should_skip_valuation(_readiness):
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="valuation",
                        company_id=company_id,
                        message=(
                            f"Valuation skipped for {ticker}: readiness gate "
                            f"({_readiness['readiness_status']})."
                        ),
                        details={
                            "ticker": ticker,
                            "event": "readiness_skipped_valuation",
                            "readiness_status": _readiness["readiness_status"],
                            "reason_codes": _readiness["reason_codes"],
                        },
                    )
                    metrics["readiness_skipped_valuation"] += 1
                    continue
                try:
                    skip_diag: dict[str, Any] = {}
                    valuation_row = compute_valuation_fn(
                        company_id,
                        repo_module,
                        factor_date,
                        sector=sector,
                        company_currency=currency,
                        diagnostics_out=skip_diag,
                    )
                    if valuation_row:
                        n = repo_module.upsert_valuation_run([valuation_row])
                        metrics["valuation_runs_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="valuation",
                            company_id=company_id,
                            message=f"Valuation computed for {ticker}.",
                            details={"valuation_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="valuation",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped valuation for {ticker}: "
                                "insufficient data."
                            ),
                            details={"ticker": ticker, **skip_diag},
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Valuation computation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="valuation",
                        level="error",
                        company_id=company_id,
                        message=f"Valuation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 5: qualitative scoring ──────────────────────────────────────
        if compute_qualitative_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="qualitative",
                message="Starting qualitative scoring.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    qual_row = compute_qualitative_fn(
                        company_id,
                        repo_module,
                        factor_date,
                    )
                    if qual_row:
                        n = repo_module.upsert_qualitative_scores([qual_row])
                        metrics["qualitative_scores_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="qualitative",
                            company_id=company_id,
                            message=f"Qualitative score computed for {ticker}.",
                            details={"score_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="qualitative",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped qualitative score for {ticker}: "
                                "insufficient data."
                            ),
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Qualitative scoring failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="qualitative",
                        level="error",
                        company_id=company_id,
                        message=f"Qualitative scoring failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 6: probabilistic signal ───────────────────────────────────
        if compute_signal_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="signal",
                message="Starting probabilistic signal scoring.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                # ── Phase 10C: readiness gate ─────────────────────────────────
                _readiness = _readiness_by_company_id.get(company_id)
                if _should_skip_signal(_readiness):
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="signal",
                        company_id=company_id,
                        message=(
                            f"Signal skipped for {ticker}: readiness gate "
                            f"({_readiness['readiness_status']})."
                        ),
                        details={
                            "ticker": ticker,
                            "event": "readiness_skipped_signal",
                            "readiness_status": _readiness["readiness_status"],
                            "reason_codes": _readiness["reason_codes"],
                        },
                    )
                    metrics["readiness_skipped_signal"] += 1
                    continue
                try:
                    signal_row = compute_signal_fn(
                        company_id,
                        repo_module,
                        factor_date,
                    )
                    if signal_row:
                        n = repo_module.upsert_signal_runs([signal_row])
                        metrics["signal_runs_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="signal",
                            company_id=company_id,
                            message=f"Signal computed for {ticker}.",
                            details={"signal_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="signal",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped signal for {ticker}: "
                                "insufficient data."
                            ),
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Signal computation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="signal",
                        level="error",
                        company_id=company_id,
                        message=f"Signal computation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 7: alerts ─────────────────────────────────────────────────
        if process_alerts_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="alerts",
                message="Starting alert evaluation.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    alert_metrics = process_alerts_fn(
                        company_id,
                        repo_module,
                        factor_date,
                        company=company,
                        settings=settings,
                    )
                    metrics["alerts_sent"] += int(alert_metrics.get("alerts_sent", 0))
                    metrics["alert_history_written"] += int(
                        alert_metrics.get("alert_history_written", 0)
                    )
                    metrics["alerts_deduplicated"] += int(
                        alert_metrics.get("alerts_deduplicated", 0)
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="alerts",
                        company_id=company_id,
                        message=f"Alerts evaluated for {ticker}.",
                        details=alert_metrics,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Alert evaluation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="alerts",
                        level="error",
                        company_id=company_id,
                        message=f"Alert evaluation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        repo_module.finish_pipeline_run(
            run_id,
            status="success",
            message="Pipeline complete.",
            metrics=metrics,
        )
        return metrics
    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline failed (%s)", type(exc).__name__)
        repo_module.log_pipeline_event(
            run_id,
            stage="pipeline",
            level="error",
            message="Pipeline failed.",
            details={"error_type": type(exc).__name__},
        )
        repo_module.finish_pipeline_run(
            run_id,
            status="failed",
            message="Pipeline failed.",
            metrics=metrics,
        )
        raise


@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Load config only; do not fetch data."),
) -> None:
    """Run the daily investment-analysis pipeline."""
    settings = get_settings()
    configure_logging(settings.log_level)

    mode = "DRY RUN" if dry_run else "LIVE"
    console.print(f"[bold cyan]Daily pipeline starting ({mode})…[/bold cyan]")
    console.print(f"Environment : {settings.app_env}")

    if not dry_run:
        missing = settings.missing_required()
        if missing:
            console.print("[bold red]Pipeline aborted: missing required configuration.[/bold red]")
            for name in missing:
                console.print(f"  - [yellow]{name.upper()}[/yellow]")
            raise typer.Exit(code=1)

    if dry_run:
        companies = _load_watchlist_companies()
        providers_config = load_providers()
        console.print(f"Watchlist   : {len(companies)} companies")
        console.print("[bold]Would fetch:[/bold]")
        for company in companies:
            ticker = company.get("ticker", "?")
            cik = company.get("cik", "")
            console.print(f"  FMP profile / prices / statements : {ticker}")
            if cik:
                console.print(f"  SEC filings              : {ticker} (CIK {cik})")
        for currency in _ECB_CURRENCIES:
            console.print(f"  ECB FX rate              : EUR/{currency}")
        if _provider_enabled(providers_config, "gdelt"):
            console.print("  GDELT news               : enabled")
        else:
            console.print("  GDELT news               : skipped (disabled in providers.yml)")
        console.print("  Ratio computation      : would compute ratios_factors for each company")
        console.print("  Valuation computation  : would compute valuation_runs for each company")
        console.print("  Qualitative scoring    : would compute qualitative_scores for each company")
        console.print("  Signal scoring         : would compute signal_runs for each company")
        console.print("  Alert evaluation       : would evaluate alert_rules and write alert_history")
        console.print("[yellow]Dry run complete — no data was fetched.[/yellow]")
        return

    # ── Live mode ──────────────────────────────────────────────────────────────
    from investment_app.connectors.ecb import ECBConnector
    from investment_app.connectors.fmp import FMPConnector
    from investment_app.connectors.gdelt import GDELTConnector
    from investment_app.connectors.sec_edgar import SECEdgarConnector
    from investment_app.connectors.twelve_data import TwelveDataConnector
    from investment_app.alerts import process_company_alerts
    from investment_app.db import repositories as repo
    from investment_app.etl.normalize_news import normalize_gdelt_news
    from investment_app.etl.normalize_prices import normalize_fmp_prices
    from investment_app.etl.normalize_statements import normalize_fmp_statements
    from investment_app.etl.raw_store import store_raw_response
    from investment_app.features import compute_all_features
    from investment_app.scoring.probabilistic import compute_signal_run
    from investment_app.scoring.qualitative import compute_qualitative_score
    from investment_app.valuation import compute_valuation_run
    providers_config = load_providers()

    # Check FMP key — warn but continue; many calls may fail but we should not abort.
    fmp_key = settings.fmp_api_key
    fmp_available = (
        _provider_enabled(providers_config, "fmp")
        and not _is_placeholder(fmp_key)
        and bool(fmp_key)
    )
    if not fmp_available:
        console.print(
            "[yellow]Warning: FMP_API_KEY not set — price/statement ingestion will be skipped.[/yellow]"
        )

    sec_user_agent = settings.sec_user_agent
    sec_available = (
        _provider_enabled(providers_config, "sec_edgar")
        and not _is_placeholder(sec_user_agent)
        and bool(sec_user_agent)
    )
    if not sec_available:
        console.print(
            "[yellow]Warning: SEC_USER_AGENT not set — SEC filing ingestion will be skipped.[/yellow]"
        )

    twelve_data_key = settings.twelve_data_api_key
    twelve_available = (
        _provider_enabled(providers_config, "twelve_data")
        and not _is_placeholder(twelve_data_key)
        and bool(twelve_data_key)
    )

    # Initialise connectors.
    fmp: FMPConnector | None = FMPConnector(fmp_key) if fmp_available else None
    sec: SECEdgarConnector | None = (
        SECEdgarConnector(sec_user_agent) if sec_available else None
    )
    ecb = ECBConnector() if _provider_enabled(providers_config, "ecb") else None
    gdelt = (
        GDELTConnector() if _provider_enabled(providers_config, "gdelt") else None
    )
    twelve = TwelveDataConnector(twelve_data_key) if twelve_available else None

    metrics = _run_live_pipeline(
        repo_module=repo,
        providers_config=providers_config,
        fmp=fmp,
        sec=sec,
        ecb=ecb,
        gdelt=gdelt,
        twelve=twelve,
        store_raw_response_fn=store_raw_response,
        normalize_prices_fn=normalize_fmp_prices,
        normalize_statements_fn=normalize_fmp_statements,
        normalize_news_fn=normalize_gdelt_news,
        compute_features_fn=compute_all_features,
        compute_valuation_fn=compute_valuation_run,
        compute_qualitative_fn=compute_qualitative_score,
        compute_signal_fn=compute_signal_run,
        process_alerts_fn=process_company_alerts,
        settings=settings,
    )

    console.print("[bold green]Pipeline complete.[/bold green]")
    for key, value in metrics.items():
        console.print(f"  {key}: {value}")


# ── Helper functions ───────────────────────────────────────────────────────────


def _extract_filings_index(
    payload: dict[str, Any],
    company_id: str,
    ticker: str,
    raw_payload_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract recent 10-K / 10-Q filings from SEC submissions payload."""
    rows: list[dict[str, Any]] = []
    filings: dict[str, Any] = payload.get("filings", {}).get("recent", {})
    cik = payload.get("cik")
    forms: list[str] = filings.get("form", [])
    accessions: list[str] = filings.get("accessionNumber", [])
    dates: list[str] = filings.get("filingDate", [])
    descriptions: list[str] = filings.get("primaryDocument", [])

    target_forms = {"10-K", "10-Q", "20-F"}
    for i, form in enumerate(forms):
        if form not in target_forms:
            continue
        try:
            rows.append(
                {
                    "company_id": company_id,
                    "source": "sec_edgar",
                    "filing_type": form,
                    "accession_number": accessions[i] if i < len(accessions) else None,
                    "filing_date": dates[i] if i < len(dates) else None,
                    "document_url": _build_sec_document_url(
                        cik,
                        accessions[i] if i < len(accessions) else None,
                        descriptions[i] if i < len(descriptions) else None,
                    ),
                }
            )
            if raw_payload_id:
                rows[-1]["raw_payload_id"] = raw_payload_id
        except (IndexError, KeyError):
            logger.debug("Skipping malformed filing index entry for %s index %d", ticker, i)
    return rows


def _extract_ecb_fx_rates(
    payload: dict[str, Any], quote_currency: str
) -> list[dict[str, Any]]:
    """Parse ECB JSON data format into ``fx_rates`` rows."""
    rows: list[dict[str, Any]] = []
    try:
        datasets: list[dict[str, Any]] = payload.get("dataSets", [])
        if not datasets:
            return rows
        series_key = list(datasets[0].get("series", {}).keys())
        if not series_key:
            return rows
        observations: dict[str, list[Any]] = (
            datasets[0]["series"][series_key[0]].get("observations", {})
        )
        # Map period index to date string from structure.
        structure = payload.get("structure", {})
        time_periods: list[str] = (
            structure.get("dimensions", {}).get("observation", [{}])[-1].get("values", [])
        )
        for idx_str, obs_list in observations.items():
            idx = int(idx_str)
            rate_val = obs_list[0] if obs_list else None
            date_str = time_periods[idx]["id"] if idx < len(time_periods) else None
            if rate_val is None or date_str is None:
                continue
            try:
                rows.append(
                    {
                        "rate_date": date_str,
                        "base_currency": "EUR",
                        "quote_currency": quote_currency,
                        "rate": float(rate_val),
                        "provider": "ecb",
                    }
                )
            except (TypeError, ValueError):
                continue
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Failed to parse ECB FX payload for %s: %s", quote_currency, exc)
    return rows


if __name__ == "__main__":
    app()

