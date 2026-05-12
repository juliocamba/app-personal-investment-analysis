"""News normalisation — GDELT Doc API payload to ``news_events`` rows."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def normalize_gdelt_news(
    payload: dict[str, Any] | list[Any] | None,
    company_id: str | None,
    ticker: str,
    raw_payload_id: str | None = None,
) -> list[dict[str, Any]]:
    """Convert a GDELT artlist response to ``news_events`` rows.

    Args:
        payload: Raw GDELT API response (JSON with 'articles' list).
        company_id: Optional Supabase UUID for the associated company.
        ticker: Ticker symbol (used for logging only).
        raw_payload_id: Optional FK to ``raw_provider_payloads``.

    Returns:
        List of dicts ready to upsert into ``news_events``.
    """
    if not payload or not isinstance(payload, dict):
        logger.debug("Empty or invalid GDELT payload for %s", ticker)
        return []

    articles: list[dict[str, Any]] = payload.get("articles", [])
    if not articles:
        logger.debug("No GDELT articles for %s", ticker)
        return []

    rows: list[dict[str, Any]] = []
    for article in articles:
        url = article.get("url")
        title = article.get("title")
        published_at = article.get("seendate")  # format: YYYYMMDDTHHMMSSZ
        if not url or not title or not published_at:
            continue

        # Convert GDELT date format to ISO8601 if needed.
        if len(published_at) == 16 and "T" in published_at:
            # YYYYMMDDTHHMMSSZ → already a string; store as-is.
            pass

        row: dict[str, Any] = {
            "provider": "gdelt",
            "title": title[:1000],  # guard against very long titles
            "url": url,
            "published_at": published_at,
            "source": article.get("domain"),
            "language": article.get("language"),
            "sentiment_raw": None,
            "relevance": article.get("relevance"),
            "themes": article.get("themes", "").split(";") if article.get("themes") else [],
        }
        if company_id:
            row["company_id"] = company_id
        if raw_payload_id:
            row["raw_payload_id"] = raw_payload_id
        rows.append(row)

    logger.debug("Normalised %d news rows for %s", len(rows), ticker)
    return rows

