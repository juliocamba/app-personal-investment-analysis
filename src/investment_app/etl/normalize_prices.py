"""Price normalisation — FMP EOD historical price payloads to ``price_eod``.

Handles two response shapes:
- *Stable API* (``/stable/historical-price-eod/full``): flat list
  ``[{date, open, high, low, close, volume, ...}, ...]``.
- *Legacy v3 API* (``/api/v3/historical-price-full/{ticker}``): wrapped dict
  ``{"symbol": "AAPL", "historical": [{...}, ...]}``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    """Return float or None without raising."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_fmp_prices(
    payload: dict[str, Any] | list[Any] | None,
    company_id: str,
    ticker: str,
    currency: str = "USD",
    raw_payload_id: str | None = None,
) -> list[dict[str, Any]]:
    """Convert an FMP historical-price payload to ``price_eod`` rows.

    Accepts both the stable API flat-list format and the legacy v3 wrapped-dict
    format transparently.

    Args:
        payload: Raw FMP response payload — either a flat list (stable) or a
            dict with a ``"historical"`` key (v3 legacy).
        company_id: Supabase UUID for the company.
        ticker: Ticker symbol (used for logging only).
        currency: ISO currency code for the price data.
        raw_payload_id: Optional FK to ``raw_provider_payloads``.

    Returns:
        List of dicts ready to upsert into ``price_eod``.
    """
    if not payload:
        logger.warning("Empty or invalid FMP price payload for %s", ticker)
        return []

    # Stable API returns a flat list; legacy v3 wraps data in {"historical": [...]}.
    if isinstance(payload, list):
        historical: list[dict[str, Any]] = payload
    elif isinstance(payload, dict):
        historical = payload.get("historical", [])
    else:
        logger.warning("Empty or invalid FMP price payload for %s", ticker)
        return []

    if not historical:
        logger.warning("No historical price entries for %s", ticker)
        return []

    rows: list[dict[str, Any]] = []
    for entry in historical:
        date_str = entry.get("date")
        close_val = _safe_float(entry.get("close") or entry.get("adjClose"))
        if not date_str or close_val is None:
            continue

        row: dict[str, Any] = {
            "company_id": company_id,
            "price_date": date_str,
            "open": _safe_float(entry.get("open")),
            "high": _safe_float(entry.get("high")),
            "low": _safe_float(entry.get("low")),
            "close": close_val,
            "adjusted_close": _safe_float(entry.get("adjClose")),
            "volume": _safe_float(entry.get("volume")),
            "market_cap": None,
            "shares_outstanding": None,
            "currency": currency,
            "provider": "fmp",
        }
        if raw_payload_id:
            row["raw_payload_id"] = raw_payload_id
        rows.append(row)

    logger.debug("Normalised %d price rows for %s", len(rows), ticker)
    return rows


def normalize_twelve_data_prices(
    payload: dict[str, Any] | None,
    company_id: str,
    ticker: str,
    currency: str = "USD",
    raw_payload_id: str | None = None,
) -> list[dict[str, Any]]:
    """Convert a Twelve Data time-series payload to ``price_eod`` rows.

    Expected payload shape::

        {
            "meta":   {"symbol": "ORCL", "currency": "USD", ...},
            "values": [
                {"datetime": "2024-01-02", "open": "...", "high": "...",
                 "low": "...", "close": "...", "volume": "..."},
                ...
            ]
        }

    Args:
        payload: Raw Twelve Data response payload.
        company_id: Supabase UUID for the company.
        ticker: Ticker symbol (used for logging only).
        currency: ISO currency code fallback (overridden by ``meta.currency``).
        raw_payload_id: Optional FK to ``raw_provider_payloads``.

    Returns:
        List of dicts ready to upsert into ``price_eod``.
    """
    if not payload or not isinstance(payload, dict):
        logger.warning("Empty or invalid Twelve Data payload for %s", ticker)
        return []

    values: list[Any] = payload.get("values") or []
    if not values:
        logger.warning("No values in Twelve Data payload for %s", ticker)
        return []

    # Prefer currency from the meta block when present.
    meta_currency: str = payload.get("meta", {}).get("currency") or currency

    rows: list[dict[str, Any]] = []
    for entry in values:
        if not isinstance(entry, dict):
            continue
        date_str = entry.get("datetime")
        close_val = _safe_float(entry.get("close"))
        if not date_str or close_val is None:
            continue

        row: dict[str, Any] = {
            "company_id": company_id,
            "price_date": date_str,
            "open": _safe_float(entry.get("open")),
            "high": _safe_float(entry.get("high")),
            "low": _safe_float(entry.get("low")),
            "close": close_val,
            "adjusted_close": _safe_float(entry.get("close")),  # Twelve Data free tier: no adj
            "volume": _safe_float(entry.get("volume")),
            "market_cap": None,
            "shares_outstanding": None,
            "currency": meta_currency,
            "provider": "twelve_data",
            "metadata": {},
        }
        if raw_payload_id:
            row["raw_payload_id"] = raw_payload_id
        rows.append(row)

    logger.debug("Normalised %d Twelve Data price rows for %s", len(rows), ticker)
    return rows


def fmp_prices_need_fallback(
    price_resp: Any,
    price_rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Decide whether to trigger the Twelve Data price fallback.

    Args:
        price_resp: :class:`~investment_app.connectors.base.ProviderResponse`
            returned by the FMP price endpoint.
        price_rows: Rows produced by :func:`normalize_fmp_prices` (may be
            empty if ``price_resp`` was not successful).

    Returns:
        ``(True, reason_code)`` when the fallback should run,
        ``(False, "")`` when FMP succeeded with usable rows.
    """
    if price_resp.status_code == 402:
        return True, "fmp_402"
    if price_resp.status_code == 403:
        return True, "fmp_403"
    if not price_resp.success:
        return True, "fmp_price_fetch_failed"
    if not price_resp.payload:
        return True, "fmp_price_empty_payload"
    if len(price_rows) == 0:
        return True, "fmp_price_normalized_zero_rows"
    return False, ""

