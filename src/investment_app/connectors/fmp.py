"""Financial Modeling Prep (FMP) connector.

Fetches EOD prices, income statements, balance sheets, cash flows, and company
profiles.  All requests require an API key passed via ``FMP_API_KEY``.

Uses the FMP *stable* API (``/stable/``) by default.  Legacy ``/api/v3``
endpoints return HTTP 403 on current FMP plans and are no longer used.

Only endpoints needed for Phase 2 MVP ingestion are implemented here.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from investment_app.connectors.base import BaseConnector, ProviderResponse
from investment_app.utils.retry import api_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/stable"

# 300 req/min → ~0.2 s between requests; use 0.25 s to stay comfortably below.
_MIN_INTERVAL = 0.25


class FMPConnector(BaseConnector):
    """HTTP connector for the Financial Modeling Prep stable API."""

    provider_name = "fmp"
    _min_request_interval = _MIN_INTERVAL

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("FMP_API_KEY must not be empty.")
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get(self, path: str, params: dict[str, Any]) -> ProviderResponse:
        """Make a GET request to *path* and return a ProviderResponse."""
        self._rate_limit()
        merged = {**params, "apikey": self._api_key}
        url = f"{_BASE_URL}/{path.lstrip('/')}"
        try:
            resp = self._client.get(url, params=merged)
            success = resp.status_code == 200
            payload: Any = None
            payload_text = resp.text
            if success:
                try:
                    payload = resp.json()
                except Exception:
                    payload = None
            else:
                logger.warning("FMP %s → HTTP %d", path, resp.status_code)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params,
                status_code=resp.status_code,
                success=success,
                payload=payload,
                payload_text=payload_text,
            )
        except httpx.TimeoutException as exc:
            logger.error("FMP timeout on %s (%s)", path, type(exc).__name__)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params,
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"fmp_request_failed ({type(exc).__name__})",
            )
        except httpx.RequestError as exc:
            logger.error("FMP request error on %s (%s)", path, type(exc).__name__)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params,
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"fmp_request_failed ({type(exc).__name__})",
            )

    @api_retry
    def fetch(self, endpoint: str, params: dict[str, Any]) -> ProviderResponse:
        return self._get(endpoint, params)

    def health_check(self) -> bool:
        resp = self._get("profile", {"symbol": "AAPL"})
        return resp.success

    # ── Domain-level helpers ───────────────────────────────────────────────────

    @api_retry
    def get_profile(self, ticker: str) -> ProviderResponse:
        """Fetch the company profile for *ticker*."""
        return self._get("profile", {"symbol": ticker})

    @api_retry
    def get_historical_prices(
        self, ticker: str, *, from_date: str | None = None, to_date: str | None = None
    ) -> ProviderResponse:
        """Fetch EOD historical price data for *ticker*.

        Args:
            ticker: Stock ticker symbol.
            from_date: Inclusive start date (YYYY-MM-DD). Defaults to last 30 days.
            to_date: Inclusive end date (YYYY-MM-DD). Defaults to today.
        """
        params: dict[str, Any] = {"symbol": ticker}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._get("historical-price-eod/full", params)

    @api_retry
    def get_income_statement(
        self, ticker: str, *, period: str = "annual", limit: int = 5
    ) -> ProviderResponse:
        """Fetch income statement for *ticker*."""
        return self._get(
            "income-statement", {"symbol": ticker, "period": period, "limit": limit}
        )

    @api_retry
    def get_balance_sheet(
        self, ticker: str, *, period: str = "annual", limit: int = 5
    ) -> ProviderResponse:
        """Fetch balance sheet for *ticker*."""
        return self._get(
            "balance-sheet-statement", {"symbol": ticker, "period": period, "limit": limit}
        )

    @api_retry
    def get_cash_flow(
        self, ticker: str, *, period: str = "annual", limit: int = 5
    ) -> ProviderResponse:
        """Fetch cash flow statement for *ticker*."""
        return self._get(
            "cash-flow-statement", {"symbol": ticker, "period": period, "limit": limit}
        )

