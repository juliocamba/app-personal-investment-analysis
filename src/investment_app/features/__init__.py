"""Features package — Phase 3.

The top-level ``compute_all_features`` function orchestrates the full ratio
and feature computation for one company on one date.  It reads already-stored
data from Supabase (via *repo_module*) and returns a single ``ratios_factors``
row ready for persistence.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from investment_app.features.market_features import compute_market_features
from investment_app.features.news_features import compute_news_features
from investment_app.features.quality_features import compute_data_quality_score
from investment_app.features.ratios import compute_financial_ratios


def compute_all_features(
    company_id: str,
    repo_module: Any,
    factor_date: str,
    *,
    company_currency: str = "USD",
) -> dict[str, Any] | None:
    """Fetch company data and compute all ratios/features for *factor_date*.

    Parameters
    ----------
    company_id:
        UUID of the company row in Supabase.
    repo_module:
        Object exposing ``get_statements_for_company``,
        ``get_prices_for_company``, ``get_news_for_company``, and
        ``get_filings_for_company``.  In production this is the
        ``repositories`` module; in tests it is a fake.
    factor_date:
        ISO date string (``YYYY-MM-DD``) to stamp the ``ratios_factors`` row.
        All repo reads use this date as an upper-bound ceiling, ensuring
        point-in-time safety — no future data leaks into the snapshot.
    company_currency:
        ISO 4217 currency code for the company's reporting currency (e.g.
        ``"USD"``, ``"EUR"``).  Used to derive the ``has_fx_if_needed`` flag
        in the data-quality score: USD companies require no FX conversion, so
        they are always awarded that point.  Non-USD companies are scored
        conservatively as False (FX data availability is not verified here).

    Returns
    -------
    dict or None
        A ``ratios_factors``-shaped dict, or ``None`` when there is no data at
        all to compute from (i.e. no statements *and* no prices).
    """
    statements: list[dict[str, Any]] = repo_module.get_statements_for_company(
        company_id, as_of_date=factor_date
    )
    price_rows: list[dict[str, Any]] = repo_module.get_prices_for_company(
        company_id, as_of_date=factor_date
    )
    news_rows: list[dict[str, Any]] = repo_module.get_news_for_company(
        company_id, as_of_date=factor_date
    )
    filings_rows: list[dict[str, Any]] = repo_module.get_filings_for_company(
        company_id, as_of_date=factor_date
    )

    # Annual statements only.
    # Sort by a five-level key (all descending) so that restatement selection
    # is fully deterministic regardless of the order rows arrive from the DB:
    #   1. fiscal_year      — newer year first
    #   2. period_end_date  — later end-date first (handles different period spans)
    #   3. restated_flag    — True (restated/amended) before False (original)
    #   4. created_at       — later ingestion first (same-date multi-source tiebreak)
    #   5. id               — UUID string tiebreaker for complete determinism
    # After sorting, deduplicate by (fiscal_year, fiscal_period): the first row
    # for each reporting period is the most authoritative version.
    annual_raw = [
        s for s in statements if s.get("fiscal_period") in ("FY", "annual")
    ]

    def _stmt_sort_key(s: dict[str, Any]) -> tuple:
        return (
            s.get("fiscal_year") or 0,
            s.get("period_end_date") or "",
            bool(s.get("restated_flag")),
            s.get("created_at") or "",
            s.get("id") or "",
        )

    annual_raw.sort(key=_stmt_sort_key, reverse=True)
    seen_periods: set[tuple] = set()
    annual: list[dict[str, Any]] = []
    for stmt in annual_raw:
        fy: int = stmt.get("fiscal_year") or 0
        fp: str = stmt.get("fiscal_period") or ""
        period_key = (fy, fp)
        if period_key not in seen_periods:
            seen_periods.add(period_key)
            annual.append(stmt)

    if not annual and not price_rows:
        return None

    latest_price = price_rows[0] if price_rows else None

    # --- Financial ratios ---------------------------------------------------
    ratios = compute_financial_ratios(annual, latest_price_row=latest_price)

    # --- Market features ----------------------------------------------------
    market = compute_market_features(price_rows)

    # --- News features ------------------------------------------------------
    as_of = date.fromisoformat(factor_date)
    news = compute_news_features(news_rows, as_of=as_of)

    # --- Data-quality score -------------------------------------------------
    has_shares = bool(annual) and annual[0].get("diluted_shares") is not None
    has_market_cap = latest_price is not None and (
        latest_price.get("market_cap") is not None
        or latest_price.get("close") is not None
    )
    # FX is only needed when the company reports in a non-USD currency.
    # USD companies never require FX conversion, so they always satisfy this
    # criterion.  Non-USD companies are scored conservatively (False) since
    # FX data availability is not verified within this function.
    has_fx_if_needed: bool = company_currency.upper() == "USD"
    # Derive filings and news availability from fetched data.
    has_filings: bool = bool(filings_rows)
    has_news: bool = bool(news_rows)
    quality = compute_data_quality_score(
        has_price=bool(price_rows),
        has_annual_statement=bool(annual),
        has_shares=has_shares,
        has_market_cap=has_market_cap,
        has_fx_if_needed=has_fx_if_needed,
        has_filings=has_filings,
        has_required_fields=bool(annual) and bool(price_rows),
    )

    row: dict[str, Any] = {
        "company_id": company_id,
        "factor_date": factor_date,
        "data_quality_score": quality,
        "metadata": {},
        **ratios,
        **market,
        "news_sentiment_7d": news.get("news_sentiment_7d"),
        "news_volume_7d": news.get("news_volume_7d"),
    }
    return row
