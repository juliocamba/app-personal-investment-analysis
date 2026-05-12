"""ECB Statistical Data Warehouse (SDW) connector.

Fetches EUR-based reference exchange rates published by the European Central
Bank.  No API key required.

The ECB SDW REST API endpoint used:
    /service/data/EXR/D.{currency}.EUR.SP00.A
where {currency} is e.g. USD, GBP, JPY.

Returns daily observation series in JSON (structureSpecificData).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from investment_app.connectors.base import BaseConnector, ProviderResponse
from investment_app.utils.retry import api_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://data-api.ecb.europa.eu/service"
_MIN_INTERVAL = 1.0  # be conservative with the free public API

# Currencies we need for MVP: USD quoted against EUR.
DEFAULT_CURRENCIES = ("USD", "GBP", "JPY", "CHF")


class ECBConnector(BaseConnector):
    """HTTP connector for the ECB Statistical Data Warehouse REST API."""

    provider_name = "ecb"
    _min_request_interval = _MIN_INTERVAL

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json"},
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
                logger.warning("ECB %s → HTTP %d", path, resp.status_code)
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
            logger.error("ECB timeout on %s (%s)", path, type(exc).__name__)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params or {},
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"ecb_request_failed ({type(exc).__name__})",
            )
        except httpx.RequestError as exc:
            logger.error("ECB request error on %s (%s)", path, type(exc).__name__)
            return ProviderResponse(
                provider=self.provider_name,
                endpoint=path,
                params=params or {},
                status_code=0,
                success=False,
                payload=None,
                payload_text=None,
                error_message=f"ecb_request_failed ({type(exc).__name__})",
            )

    @api_retry
    def fetch(self, endpoint: str, params: dict[str, Any]) -> ProviderResponse:
        return self._get(endpoint, params)

    def health_check(self) -> bool:
        resp = self.get_fx_rate("USD", last_n=1)
        return resp.success

    @api_retry
    def get_fx_rate(
        self,
        currency: str,
        *,
        start_period: str | None = None,
        end_period: str | None = None,
        last_n: int | None = None,
    ) -> ProviderResponse:
        """Fetch daily EUR/{currency} exchange rate observations.

        Args:
            currency: Quote currency code (e.g. 'USD').
            start_period: Inclusive start date in YYYY-MM-DD or YYYY format.
            end_period: Inclusive end date in YYYY-MM-DD or YYYY format.
            last_n: If set, return only the most recent *last_n* observations.
        """
        path = f"data/EXR/D.{currency.upper()}.EUR.SP00.A"
        params: dict[str, Any] = {"detail": "dataonly", "format": "jsondata"}
        if start_period:
            params["startPeriod"] = start_period
        if end_period:
            params["endPeriod"] = end_period
        if last_n is not None:
            params["lastNObservations"] = last_n
        return self._get(path, params)

