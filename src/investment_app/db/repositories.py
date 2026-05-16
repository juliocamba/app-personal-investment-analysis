"""Data-access repository functions for the investment analysis pipeline.

All functions accept an optional ``client`` keyword argument for easy unit
testing.  When *client* is ``None`` the module obtains a live connection by
calling :func:`~investment_app.db.supabase_client.get_supabase_client`.
"""
from __future__ import annotations

from typing import Any

from investment_app.utils.dates import utc_now


def _db(client: Any) -> Any:
    """Return *client* when provided; otherwise fetch a live Supabase client."""
    if client is not None:
        return client
    from investment_app.db.supabase_client import get_supabase_client  # lazy import

    return get_supabase_client()


# ── Companies ─────────────────────────────────────────────────────────────────


def list_active_companies(*, client: Any = None) -> list[dict[str, Any]]:
    """Return all rows from ``companies`` where ``active = true``.

    .. deprecated::
        Prefer :func:`list_watchlist_active_companies` which uses
        ``watchlist_companies.active`` as the authoritative membership flag
        (Phase 9A).  This function is retained as a fallback only.
    """
    response = _db(client).table("companies").select("*").eq("active", True).execute()
    return response.data


def list_watchlist_active_companies(*, client: Any = None) -> list[dict[str, Any]]:
    """Return distinct company rows linked to active watchlist memberships.

    Uses ``watchlist_companies.active = true`` as the source of truth for
    which companies the daily pipeline should process and which the dashboard
    should display.

    Implementation uses two queries to remain compatible with the existing
    mock infrastructure:

    1. Fetch distinct ``company_id`` values from ``watchlist_companies`` where
       ``active = true``.
    2. Fetch the full company rows for those IDs.

    Returns an empty list when there are no active memberships.
    """
    db = _db(client)
    # Step 1: collect active company IDs from the membership table.
    wc_resp = (
        db.table("watchlist_companies")
        .select("company_id")
        .eq("active", True)
        .execute()
    )
    company_ids = list(
        {row["company_id"] for row in wc_resp.data if row.get("company_id")}
    )
    if not company_ids:
        return []
    # Step 2: fetch full company records for those IDs.
    companies_resp = (
        db.table("companies")
        .select("*")
        .in_("id", company_ids)
        .execute()
    )
    return companies_resp.data


def soft_remove_watchlist_company(
    membership_id: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Soft-remove a watchlist membership by setting ``active = false``.

    Sets ``removed_at`` to the current UTC timestamp.
    Does not delete the ``watchlist_companies`` row or any historical data.

    Parameters
    ----------
    membership_id:
        The UUID of the ``watchlist_companies`` row (``wc.id``).
    """
    response = (
        _db(client)
        .table("watchlist_companies")
        .update({"active": False, "removed_at": utc_now().isoformat()})
        .eq("id", membership_id)
        .execute()
    )
    return response.data[0] if response.data else None


def reactivate_watchlist_company(
    membership_id: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Reactivate a previously removed watchlist membership.

    Sets ``active = true`` and clears ``removed_at``.
    All historical data for the company is automatically included in the
    next pipeline run without any further action.

    Parameters
    ----------
    membership_id:
        The UUID of the ``watchlist_companies`` row (``wc.id``).
    """
    response = (
        _db(client)
        .table("watchlist_companies")
        .update({"active": True, "removed_at": None})
        .eq("id", membership_id)
        .execute()
    )
    return response.data[0] if response.data else None


def get_company_by_ticker(ticker: str, *, client: Any = None) -> dict[str, Any] | None:
    """Return the first company row matching *ticker* (case-insensitive), or ``None``."""
    response = (
        _db(client)
        .table("companies")
        .select("*")
        .eq("ticker", ticker.upper())
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def list_companies_by_ticker(ticker: str, *, client: Any = None) -> list[dict[str, Any]]:
    """Return all company rows matching *ticker* (exact, case-insensitive).

    Used by the pipeline to detect whether a company already exists (possibly
    on multiple exchanges) before creating a new one.
    """
    response = (
        _db(client)
        .table("companies")
        .select("*")
        .eq("ticker", ticker.upper())
        .execute()
    )
    return response.data


def get_company_by_ticker_exchange(
    ticker: str,
    exchange: str | None,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Return a company row matching *ticker* and optionally *exchange*.

    When *exchange* is provided the lookup is exact (ticker + exchange).
    When *exchange* is ``None`` the first row matching ticker alone is returned.
    """
    ticker_upper = ticker.upper()
    if exchange:
        response = (
            _db(client)
            .table("companies")
            .select("*")
            .eq("ticker", ticker_upper)
            .eq("exchange", exchange.upper())
            .limit(1)
            .execute()
        )
    else:
        response = (
            _db(client)
            .table("companies")
            .select("*")
            .eq("ticker", ticker_upper)
            .limit(1)
            .execute()
        )
    return response.data[0] if response.data else None


def create_company(
    ticker: str,
    name: str,
    exchange: str | None = None,
    country: str | None = None,
    currency: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    cik: str | None = None,
    *,
    client: Any = None,
) -> dict[str, Any]:
    """Insert a new company row and return it.

    Used exclusively by the backend pipeline.  The frontend never calls this.
    ``cik`` may be ``None`` when FMP does not provide it.
    """
    payload: dict[str, Any] = {
        "ticker": ticker.upper(),
        "name": name,
        "active": True,
    }
    if exchange is not None:
        payload["exchange"] = exchange.upper()
    if country is not None:
        payload["country"] = country
    if currency is not None:
        payload["currency"] = currency
    if sector is not None:
        payload["sector"] = sector
    if industry is not None:
        payload["industry"] = industry
    if cik is not None:
        payload["cik"] = cik
    response = _db(client).table("companies").insert(payload).execute()
    return response.data[0]


def get_watchlist_membership(
    watchlist_id: str,
    company_id: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Return the ``watchlist_companies`` row for a given watchlist/company pair, or ``None``."""
    response = (
        _db(client)
        .table("watchlist_companies")
        .select("*")
        .eq("watchlist_id", watchlist_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def create_watchlist_membership(
    watchlist_id: str,
    company_id: str,
    *,
    client: Any = None,
) -> dict[str, Any]:
    """Insert a new active ``watchlist_companies`` row and return it.

    Used exclusively by the backend pipeline; the frontend cannot INSERT
    into ``watchlist_companies`` (no INSERT grant to ``authenticated`` role).
    """
    response = (
        _db(client)
        .table("watchlist_companies")
        .insert({"watchlist_id": watchlist_id, "company_id": company_id, "active": True})
        .execute()
    )
    return response.data[0]


# ── Phase 9B: Watchlist add requests ─────────────────────────────────────────


def list_pending_watchlist_add_requests(*, client: Any = None) -> list[dict[str, Any]]:
    """Return all ``watchlist_add_requests`` rows with ``status = 'pending'``.

    Ordered by ``requested_at`` ascending (process oldest first).
    Called by the pipeline before loading active companies.
    """
    response = (
        _db(client)
        .table("watchlist_add_requests")
        .select("*")
        .eq("status", "pending")
        .order("requested_at", desc=False)
        .execute()
    )
    return response.data


def approve_watchlist_add_request(
    request_id: str,
    company_id: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Mark a request as approved, recording the resulting company UUID."""
    response = (
        _db(client)
        .table("watchlist_add_requests")
        .update(
            {
                "status": "approved",
                "company_id": company_id,
                "processed_at": utc_now().isoformat(),
            }
        )
        .eq("id", request_id)
        .execute()
    )
    return response.data[0] if response.data else None


def reject_watchlist_add_request(
    request_id: str,
    error_code: str,
    error_message: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Mark a request as rejected with a safe error code and message."""
    response = (
        _db(client)
        .table("watchlist_add_requests")
        .update(
            {
                "status": "rejected",
                "error_code": error_code,
                "error_message": error_message,
                "processed_at": utc_now().isoformat(),
            }
        )
        .eq("id", request_id)
        .execute()
    )
    return response.data[0] if response.data else None


def fail_watchlist_add_request(
    request_id: str,
    error_code: str,
    error_message: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Mark a request as failed due to a technical error (e.g. provider unavailable)."""
    response = (
        _db(client)
        .table("watchlist_add_requests")
        .update(
            {
                "status": "failed",
                "error_code": error_code,
                "error_message": error_message,
                "processed_at": utc_now().isoformat(),
            }
        )
        .eq("id", request_id)
        .execute()
    )
    return response.data[0] if response.data else None


def update_company_profile(
    company_id: str,
    fields: dict[str, Any],
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Update a company master row with profile fields from ingestion."""
    if not fields:
        return None
    response = (
        _db(client).table("companies").update(fields).eq("id", company_id).execute()
    )
    return response.data[0] if response.data else None


# ── Pipeline runs ──────────────────────────────────────────────────────────────


def insert_pipeline_run(
    *,
    run_type: str = "daily",
    git_sha: str | None = None,
    model_version: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Insert a new ``pipeline_runs`` row with ``status = 'running'`` and return it."""
    payload: dict[str, Any] = {
        "run_type": run_type,
        "status": "running",
        "started_at": utc_now().isoformat(),
    }
    if git_sha is not None:
        payload["git_sha"] = git_sha
    if model_version is not None:
        payload["model_version"] = model_version
    response = _db(client).table("pipeline_runs").insert(payload).execute()
    return response.data[0]


def finish_pipeline_run(
    run_id: str,
    *,
    status: str,
    message: str | None = None,
    metrics: dict[str, Any] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Update a ``pipeline_runs`` row to reflect completion."""
    payload: dict[str, Any] = {
        "status": status,
        "finished_at": utc_now().isoformat(),
    }
    if message is not None:
        payload["message"] = message
    if metrics is not None:
        payload["metrics"] = metrics
    response = (
        _db(client).table("pipeline_runs").update(payload).eq("id", run_id).execute()
    )
    return response.data[0]


def log_pipeline_event(
    pipeline_run_id: str,
    *,
    stage: str,
    message: str,
    level: str = "info",
    company_id: str | None = None,
    details: dict[str, Any] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Insert a ``pipeline_run_events`` row and return it."""
    payload: dict[str, Any] = {
        "pipeline_run_id": pipeline_run_id,
        "level": level,
        "stage": stage,
        "message": message,
        "details": details or {},
    }
    if company_id is not None:
        payload["company_id"] = company_id
    response = _db(client).table("pipeline_run_events").insert(payload).execute()
    return response.data[0]


# ── Price EOD ──────────────────────────────────────────────────────────────────


def upsert_price_eod(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert price rows into ``price_eod``.

    Uses the unique constraint on (company_id, price_date, provider) to avoid
    duplicates.  Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("price_eod")
        .upsert(rows, on_conflict="company_id,price_date,provider")
        .execute()
    )
    return len(response.data)


# ── Statements norm ────────────────────────────────────────────────────────────


def upsert_statements_norm(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert normalised statement rows into ``statements_norm``.

    Unique constraint: (company_id, fiscal_year, fiscal_period, source).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("statements_norm")
        .upsert(rows, on_conflict="company_id,fiscal_year,fiscal_period,source")
        .execute()
    )
    return len(response.data)


# ── FX rates ───────────────────────────────────────────────────────────────────


def upsert_fx_rates(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert FX rate rows into ``fx_rates``.

    Unique constraint: (rate_date, base_currency, quote_currency, provider).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("fx_rates")
        .upsert(rows, on_conflict="rate_date,base_currency,quote_currency,provider")
        .execute()
    )
    return len(response.data)


# ── Filings index ──────────────────────────────────────────────────────────────


def upsert_filings_index(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert filing index rows into ``filings_index``.

    Unique constraint: (source, accession_number).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("filings_index")
        .upsert(rows, on_conflict="source,accession_number")
        .execute()
    )
    return len(response.data)


# ── News events ────────────────────────────────────────────────────────────────


def upsert_news_events(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert news event rows into ``news_events``.

    Unique constraint: (provider, url).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("news_events")
        .upsert(rows, on_conflict="provider,url")
        .execute()
    )
    return len(response.data)


# ── Phase 3: Feature data reads ────────────────────────────────────────────────


def get_statements_for_company(
    company_id: str,
    *,
    as_of_date: str | None = None,
    limit: int = 10,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return normalised statement rows for *company_id*, newest period first.

    Fetches from ``statements_norm`` ordered by ``period_end_date`` descending.
    When *as_of_date* is provided only rows with ``period_end_date ≤ as_of_date``
    are returned, enforcing point-in-time safety.
    Returns at most *limit* rows (default 10, enough for 5 annual + 5 quarterly).
    """
    q = (
        _db(client)
        .table("statements_norm")
        .select("*")
        .eq("company_id", company_id)
    )
    if as_of_date is not None:
        q = q.lte("period_end_date", as_of_date)
    return q.order("period_end_date", desc=True).limit(limit).execute().data


def get_prices_for_company(
    company_id: str,
    *,
    as_of_date: str | None = None,
    limit: int = 300,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return EOD price rows for *company_id*, newest date first.

    Fetches from ``price_eod`` ordered by ``price_date`` descending.
    When *as_of_date* is provided only rows with ``price_date ≤ as_of_date``
    are returned, enforcing point-in-time safety.
    Returns at most *limit* rows (default 300, ~1.2 trading years).
    """
    q = (
        _db(client)
        .table("price_eod")
        .select("*")
        .eq("company_id", company_id)
    )
    if as_of_date is not None:
        q = q.lte("price_date", as_of_date)
    return q.order("price_date", desc=True).limit(limit).execute().data


def get_news_for_company(
    company_id: str,
    *,
    as_of_date: str | None = None,
    limit: int = 100,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return news event rows for *company_id*, newest first.

    Fetches from ``news_events`` ordered by ``published_at`` descending.
    When *as_of_date* is provided only rows with ``published_at ≤ as_of_date``
    are returned, enforcing point-in-time safety.
    Returns at most *limit* rows (default 100).
    """
    q = (
        _db(client)
        .table("news_events")
        .select("*")
        .eq("company_id", company_id)
    )
    if as_of_date is not None:
        q = q.lte("published_at", as_of_date)
    return q.order("published_at", desc=True).limit(limit).execute().data


def get_filings_for_company(
    company_id: str,
    *,
    as_of_date: str | None = None,
    limit: int = 10,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return filing index rows for *company_id*, newest first.

    Fetches from ``filings_index`` ordered by ``filing_date`` descending.
    When *as_of_date* is provided only rows with ``filing_date ≤ as_of_date``
    are returned, enforcing point-in-time safety.
    Returns at most *limit* rows (default 10).
    """
    q = (
        _db(client)
        .table("filings_index")
        .select("*")
        .eq("company_id", company_id)
    )
    if as_of_date is not None:
        q = q.lte("filing_date", as_of_date)
    return q.order("filing_date", desc=True).limit(limit).execute().data


# ── Phase 3: Ratios persist ────────────────────────────────────────────────────


def upsert_ratios_factors(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert ratio/feature snapshot rows into ``ratios_factors``.

    Unique constraint: (company_id, factor_date).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("ratios_factors")
        .upsert(rows, on_conflict="company_id,factor_date")
        .execute()
    )
    return len(response.data)


# ── Phase 4: Valuation ────────────────────────────────────────────────────────


def get_ratios_for_company(
    company_id: str,
    *,
    as_of_date: str | None = None,
    limit: int = 12,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return ``ratios_factors`` rows for *company_id*, newest first.

    Parameters
    ----------
    as_of_date:
        ISO date string (YYYY-MM-DD).  When provided, only rows whose
        ``factor_date <= as_of_date`` are returned (point-in-time safe).
    limit:
        Maximum number of rows to fetch (default 12 ≈ one year of monthly).
    """
    query = (
        _db(client)
        .table("ratios_factors")
        .select("*")
        .eq("company_id", company_id)
        .order("factor_date", desc=True)
        .limit(limit)
    )
    if as_of_date is not None:
        query = query.lte("factor_date", as_of_date)
    response = query.execute()
    return response.data


def upsert_valuation_run(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert valuation run rows into ``valuation_runs``.

    Unique constraint: (company_id, valuation_date, model_version).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("valuation_runs")
        .upsert(rows, on_conflict="company_id,valuation_date,model_version")
        .execute()
    )
    return len(response.data)


def get_latest_valuation_run(
    company_id: str,
    *,
    as_of_date: str | None = None,
    client: Any = None,
) -> dict[str, Any] | None:
    """Return the newest valuation run for *company_id* up to *as_of_date*."""
    query = (
        _db(client)
        .table("valuation_runs")
        .select("*")
        .eq("company_id", company_id)
        .order("valuation_date", desc=True)
        .limit(1)
    )
    if as_of_date is not None:
        query = query.lte("valuation_date", as_of_date)
    response = query.execute()
    return response.data[0] if response.data else None


def get_valuation_runs_for_company(
    company_id: str,
    *,
    as_of_date: str | None = None,
    limit: int = 2,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return valuation runs for *company_id*, newest first."""
    query = (
        _db(client)
        .table("valuation_runs")
        .select("*")
        .eq("company_id", company_id)
        .order("valuation_date", desc=True)
        .limit(limit)
    )
    if as_of_date is not None:
        query = query.lte("valuation_date", as_of_date)
    return query.execute().data


# ── Phase 5: Qualitative scoring ──────────────────────────────────────────────


def upsert_qualitative_scores(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert qualitative score rows into ``qualitative_scores``.

    Unique constraint: (company_id, score_date, model_version).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("qualitative_scores")
        .upsert(rows, on_conflict="company_id,score_date,model_version")
        .execute()
    )
    return len(response.data)


def get_latest_qualitative_score(
    company_id: str,
    *,
    as_of_date: str | None = None,
    client: Any = None,
) -> dict[str, Any] | None:
    """Return the newest qualitative score row for *company_id* up to *as_of_date*."""
    query = (
        _db(client)
        .table("qualitative_scores")
        .select("*")
        .eq("company_id", company_id)
        .order("score_date", desc=True)
        .limit(1)
    )
    if as_of_date is not None:
        query = query.lte("score_date", as_of_date)
    response = query.execute()
    return response.data[0] if response.data else None


def upsert_signal_runs(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert probabilistic signal rows into ``signal_runs``."""
    if not rows:
        return 0
    response = (
        _db(client)
        .table("signal_runs")
        .upsert(rows, on_conflict="company_id,signal_date,model_version")
        .execute()
    )
    return len(response.data)


def get_signal_runs_for_company(
    company_id: str,
    *,
    as_of_date: str | None = None,
    limit: int = 2,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return signal runs for *company_id*, newest first."""
    query = (
        _db(client)
        .table("signal_runs")
        .select("*")
        .eq("company_id", company_id)
        .order("signal_date", desc=True)
        .limit(limit)
    )
    if as_of_date is not None:
        query = query.lte("signal_date", as_of_date)
    return query.execute().data


def get_enabled_alert_rules(
    company_id: str | None = None,
    *,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return enabled alert rules, including global rules for *company_id*."""
    response = (
        _db(client)
        .table("alert_rules")
        .select("*")
        .eq("enabled", True)
        .execute()
    )
    rows = response.data
    if company_id is None:
        return rows
    return [row for row in rows if row.get("company_id") in (None, company_id)]


def get_alert_history_by_dedupe(
    dedupe_key: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Return the first alert_history row matching *dedupe_key*, if any."""
    response = (
        _db(client)
        .table("alert_history")
        .select("*")
        .eq("dedupe_key", dedupe_key)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def insert_alert_history(
    row: dict[str, Any],
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Insert one alert_history row and return it."""
    response = _db(client).table("alert_history").insert(row).execute()
    return response.data[0] if response.data else None


# ── Phase 10C.3: Readiness snapshots ──────────────────────────────────────────

def upsert_company_analysis_readiness(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert current-state readiness snapshot rows into ``company_analysis_readiness``.

    Each row represents the latest readiness classification for one company.
    The primary key is ``company_id``, so this always overwrites the previous
    snapshot for that company.

    Returns the number of rows written.
    """
    if not rows:
        return 0
    response = (
        _db(client)
        .table("company_analysis_readiness")
        .upsert(rows, on_conflict="company_id")
        .execute()
    )
    return len(response.data)


def upsert_company_data_quality_snapshots(
    rows: list[dict[str, Any]], *, client: Any = None
) -> int:
    """Upsert one per-company per-date diagnostics snapshot row."""
    if not rows:
        return 0
    response = (
        _db(client)
        .table("company_data_quality_snapshots")
        .upsert(rows, on_conflict="company_id,snapshot_date")
        .execute()
    )
    return len(response.data)


def list_dashboard_positions(*, client: Any = None) -> list[dict[str, Any]]:
    """Return rows from the read-only dashboard_positions_latest view."""
    response = _db(client).table("dashboard_positions_latest").select("*").execute()
    return response.data


def list_position_entry_profiles(*, client: Any = None) -> list[dict[str, Any]]:
    """Return all position entry profiles visible to the caller."""
    response = _db(client).table("position_entry_profiles").select("*").execute()
    return response.data


def list_position_review_alerts(*, client: Any = None) -> list[dict[str, Any]]:
    """Return all position review alerts visible to the caller."""
    response = _db(client).table("position_review_alerts").select("*").execute()
    return response.data


def get_position_review_alert_by_dedupe(
    dedupe_key: str,
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Return the first position_review_alert row matching *dedupe_key*."""
    response = (
        _db(client)
        .table("position_review_alerts")
        .select("*")
        .eq("dedupe_key", dedupe_key)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def insert_position_review_alert(
    row: dict[str, Any],
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Insert one position_review_alert row and return it."""
    response = _db(client).table("position_review_alerts").insert(row).execute()
    return response.data[0] if response.data else None


def update_position_review_alert(
    alert_id: str,
    fields: dict[str, Any],
    *,
    client: Any = None,
) -> dict[str, Any] | None:
    """Update one position_review_alert row and return it."""
    response = (
        _db(client)
        .table("position_review_alerts")
        .update(fields)
        .eq("id", alert_id)
        .execute()
    )
    return response.data[0] if response.data else None

