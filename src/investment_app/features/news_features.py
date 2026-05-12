"""News sentiment and volume features — Phase 3.

Computes simple aggregate features from ``news_events`` rows.  For MVP,
sentiment is the provider-supplied ``sentiment_raw`` field; no additional NLP
is applied at this phase.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _parse_date(value: Any) -> date | None:
    """Parse a ``published_at`` value to a ``date``, returning ``None`` on failure."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            # Handle both 'Z' and '+HH:MM' timezone suffixes.
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            return None
    return None


def compute_news_features(
    news_rows: list[dict[str, Any]],
    *,
    as_of: date,
) -> dict[str, Any]:
    """Compute news sentiment and volume features over a 7-day look-back.

    Parameters
    ----------
    news_rows:
        Rows from ``news_events``, any order.
    as_of:
        Reference date (typically today).  Rows with ``published_at`` on or
        after ``as_of - 7 days`` are included.

    Returns
    -------
    dict
        ``news_sentiment_7d``: average ``sentiment_raw`` over 7 days, or
        ``None`` when no sentiment data exists.
        ``news_volume_7d``: count of articles in the 7-day window.
    """
    cutoff_7d = as_of - timedelta(days=7)

    rows_7d: list[dict[str, Any]] = []
    for row in news_rows:
        pub_date = _parse_date(row.get("published_at"))
        if pub_date is not None and pub_date >= cutoff_7d:
            rows_7d.append(row)

    sentiments = [
        float(r["sentiment_raw"])
        for r in rows_7d
        if r.get("sentiment_raw") is not None
    ]
    avg_sentiment = (sum(sentiments) / len(sentiments)) if sentiments else None

    return {
        "news_sentiment_7d": avg_sentiment,
        "news_volume_7d": len(rows_7d),
    }
