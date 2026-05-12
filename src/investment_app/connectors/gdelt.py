"""GDELT Project news connector.

Fetches news articles and event data from the GDELT Doc API v2.
No API key required.

GDELT is disabled by default in providers.yml (enabled: false).
This connector is included for completeness; ingestion skips it unless enabled.

Endpoint used:
    /api/v2/doc/doc?query=...&mode=artlist&maxrecords=25&format=json
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from investment_app.connectors.base import BaseConnector, ProviderResponse
from investment_app.utils.retry import api_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.gdeltproject.org/api/v2"
_MIN_INTERVAL = 1.0

_MAX_RECORDS = 25


class GDELTConnector(BaseConnector):
    """HTTP connector for the GDELT Doc API v2."""

    provider_name = "gdelt"
    _min_request_interval = _MIN_INTERVAL

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> ProviderResponse:
        self._rate_limit()
        url = f"{_BASE_URL}/{path.lstrip('/')}"
        try:
            resp = self._client.get(url, params=params or {})
            success = resp.status_code == 200
            payload: Any = None
            payload_text = resp.text
            if success:
                try:
                    payload = resp.json()
                except Exception:
                    # GDELT sometimes returns plain text on errors
                    payload = None
            else:
                logger.warning("GDELT %s → HTTP %d", path, resp.status_code)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params or {},
                status_code=resp.status_code,
                success=success,
                payload=payload,
                payload_text=payload_text,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            logger.error("GDELT request error on %s (%s)", path, type(exc).__name__)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params or {},
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"gdelt_request_failed ({type(exc).__name__})",
            )

    @api_retry
    def fetch(self, endpoint: str, params: dict[str, Any]) -> ProviderResponse:
        return self._get(endpoint, params)

    def health_check(self) -> bool:
        resp = self.search_news("Apple", max_records=1)
        return resp.success

    @api_retry
    def search_news(
        self,
        query: str,
        *,
        max_records: int = _MAX_RECORDS,
        timespan: str = "1d",
    ) -> ProviderResponse:
        """Search recent news articles matching *query*.

        Args:
            query: Free-text search query (e.g. company name or ticker).
            max_records: Maximum articles to return (GDELT caps at 250).
            timespan: GDELT timespan string e.g. '1d', '7d', '1m'.
        """
        params: dict[str, Any] = {
            "query": query,
            "mode": "artlist",
            "maxrecords": min(max_records, 250),
            "timespan": timespan,
            "format": "json",
        }
        return self._get("doc/doc", params)

