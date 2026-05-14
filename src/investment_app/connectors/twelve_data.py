"""Twelve Data connector.

Fetches daily EOD price time-series from the Twelve Data API
(https://api.twelvedata.com).  Used as a price fallback when FMP returns
HTTP 402 / empty data.

Requires a Twelve Data API key passed as ``TWELVE_DATA_API_KEY``.
Free tier: 8 requests/minute → use 8 s minimum interval.

Only the narrow ``get_time_series`` method is exposed — no fundamentals,
no intraday, no other endpoints (Phase 10B scope).

Security notes:
- The API key is appended to requests only inside ``_get``; it is never
  stored in ``ProviderResponse.params`` or in any log message.
- Error messages follow the sanitised ``"provider_request_failed (ClassName)"``
  convention used by all other connectors.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from investment_app.connectors.base import BaseConnector, ProviderResponse
from investment_app.utils.retry import api_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.twelvedata.com"

# Free tier: 8 req/min → 7.5 s between requests; use 8 s for safety.
_MIN_INTERVAL = 8.0


class TwelveDataConnector(BaseConnector):
    """HTTP connector for the Twelve Data daily time-series API."""

    provider_name = "twelve_data"
    _min_request_interval = _MIN_INTERVAL

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("TWELVE_DATA_API_KEY must not be empty.")
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get(self, path: str, params: dict[str, Any]) -> ProviderResponse:
        """Make a GET request to *path* and return a :class:`ProviderResponse`.

        The ``apikey`` query param is added only inside this method and is
        never included in the returned ``params`` dict exposed to callers /
        log subscribers.
        """
        self._rate_limit()
        # Build request params — add api key only for the actual HTTP call.
        request_params = {**params, "apikey": self._api_key}
        url = f"{_BASE_URL}/{path.lstrip('/')}"
        try:
            resp = self._client.get(url, params=request_params)
            success = resp.status_code == 200
            payload: Any = None
            payload_text = resp.text
            if success:
                try:
                    payload = resp.json()
                    # Twelve Data returns {"code": 400, "message": "..."} for
                    # bad requests but still returns HTTP 200.  Treat these
                    # as failures so callers can rely on success=True iff
                    # a usable payload is present.
                    if isinstance(payload, dict) and payload.get("code") in (
                        400, 401, 403, 404, 429
                    ):
                        success = False
                        payload = None
                        logger.warning(
                            "Twelve Data %s → application error %s",
                            path,
                            resp.status_code,
                        )
                except Exception:
                    payload = None
            else:
                logger.warning("Twelve Data %s → HTTP %d", path, resp.status_code)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params,  # intentionally excludes api key
                status_code=resp.status_code,
                success=success,
                payload=payload,
                payload_text=payload_text,
            )
        except httpx.TimeoutException as exc:
            logger.error(
                "Twelve Data timeout on %s (%s)", path, type(exc).__name__
            )
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params,
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"twelve_data_request_failed ({type(exc).__name__})",
            )
        except httpx.RequestError as exc:
            logger.error(
                "Twelve Data request error on %s (%s)", path, type(exc).__name__
            )
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params,
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"twelve_data_request_failed ({type(exc).__name__})",
            )

    @api_retry
    def fetch(self, endpoint: str, params: dict[str, Any]) -> ProviderResponse:
        return self._get(endpoint, params)

    def health_check(self) -> bool:
        resp = self._get("time_series", {"symbol": "AAPL", "interval": "1day", "outputsize": "1"})
        return resp.success

    # ── Domain-level helpers ───────────────────────────────────────────────────

    @api_retry
    def get_time_series(
        self,
        ticker: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        outputsize: int | None = None,
        interval: str = "1day",
    ) -> ProviderResponse:
        """Fetch daily EOD time-series for *ticker*.

        Args:
            ticker: Stock ticker symbol (e.g. ``"ORCL"``).
            start_date: Inclusive start date (``YYYY-MM-DD``).
            end_date: Inclusive end date (``YYYY-MM-DD``).
            outputsize: Number of bars to return (default: Twelve Data default).
            interval: Bar interval — keep ``"1day"`` for price_eod.

        Returns:
            :class:`ProviderResponse` whose ``payload`` (when successful) is::

                {
                    "meta": {"symbol": "ORCL", "currency": "USD", ...},
                    "values": [
                        {"datetime": "2024-01-02", "open": "...", "high": "...",
                         "low": "...", "close": "...", "volume": "..."},
                        ...
                    ]
                }
        """
        params: dict[str, Any] = {"symbol": ticker, "interval": interval}
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        if outputsize is not None:
            params["outputsize"] = outputsize
        return self._get("time_series", params)
