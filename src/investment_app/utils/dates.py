"""Date and time utilities."""
from __future__ import annotations

from datetime import date, datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(tz=timezone.utc)


def today_utc() -> date:
    """Return today's date in UTC."""
    return utc_now().date()


def to_iso_date(d: date) -> str:
    """Return an ISO-8601 date string (YYYY-MM-DD)."""
    return d.isoformat()
