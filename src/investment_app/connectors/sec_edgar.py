"""SEC EDGAR connector.

Fetches company facts (XBRL), company submissions, and filing metadata from
the SEC EDGAR public data API at https://data.sec.gov.

No API key required — only a descriptive ``User-Agent`` header per SEC policy.
Rate limit: 10 requests/second as a conservative ceiling; use 0.12 s interval.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from investment_app.connectors.base import BaseConnector, ProviderResponse
from investment_app.utils.retry import api_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://data.sec.gov"
# SEC asks for ≤10 req/s; use 0.15 s to stay safely below.
_MIN_INTERVAL = 0.15


def _normalise_cik(cik: str) -> str:
    """Return a zero-padded 10-digit CIK string."""
    return cik.lstrip("0").zfill(10) if cik else cik


class SECEdgarConnector(BaseConnector):
    """HTTP connector for the SEC EDGAR public data API."""

    provider_name = "sec_edgar"
    _min_request_interval = _MIN_INTERVAL

    def __init__(self, user_agent: str, timeout: float = 60.0) -> None:
        if not user_agent:
            raise ValueError(
                "SEC_USER_AGENT must be set (e.g. 'MyApp contact@example.com')."
            )
        self._timeout = timeout
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

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
                    payload = None
            else:
                logger.warning("SEC EDGAR %s → HTTP %d", path, resp.status_code)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params or {},
                status_code=resp.status_code,
                success=success,
                payload=payload,
                payload_text=payload_text,
            )
        except httpx.TimeoutException as exc:
            logger.error("SEC EDGAR timeout on %s (%s)", path, type(exc).__name__)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params or {},
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"sec_edgar_request_failed ({type(exc).__name__})",
            )
        except httpx.RequestError as exc:
            logger.error("SEC EDGAR request error on %s (%s)", path, type(exc).__name__)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params or {},
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"sec_edgar_request_failed ({type(exc).__name__})",
            )

    @api_retry
    def fetch(self, endpoint: str, params: dict[str, Any]) -> ProviderResponse:
        return self._get(endpoint, params)

    def health_check(self) -> bool:
        resp = self._get("submissions/CIK0000320193.json")
        return resp.success

    @api_retry
    def get_submissions(self, cik: str) -> ProviderResponse:
        """Return the company submissions JSON for a CIK."""
        padded = _normalise_cik(cik)
        return self._get(f"submissions/CIK{padded}.json")

    @api_retry
    def get_company_facts(self, cik: str) -> ProviderResponse:
        """Return all XBRL company facts for a CIK."""
        padded = _normalise_cik(cik)
        return self._get(f"api/xbrl/companyfacts/CIK{padded}.json")

