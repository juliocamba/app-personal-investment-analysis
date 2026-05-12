"""Connector abstractions and transport dataclasses.

All provider connectors must implement :class:`BaseConnector`.
:class:`ProviderRequest` and :class:`ProviderResponse` are the shared
transport objects used across connectors, the ETL layer, and the raw store.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Transport dataclasses ──────────────────────────────────────────────────────


@dataclass
class ProviderRequest:
    """Describes a single request to an external provider."""

    provider: str
    endpoint: str
    params: dict[str, Any]
    company_id: str | None = None


@dataclass
class ProviderResponse:
    """Carries the result of a single provider request."""

    provider: str
    endpoint: str
    params: dict[str, Any]
    status_code: int
    success: bool
    payload: dict[str, Any] | list[Any] | None
    payload_text: str | None
    error_message: str | None = None


# ── Base connector ─────────────────────────────────────────────────────────────


class BaseConnector(ABC):
    """Common interface that all provider connectors must implement."""

    provider_name: str = "unknown"

    #: Minimum gap between consecutive requests in seconds (override per subclass).
    _min_request_interval: float = 0.0
    _last_request_time: float = 0.0

    def _rate_limit(self) -> None:
        """Block until the minimum inter-request interval has elapsed."""
        if self._min_request_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    @abstractmethod
    def fetch(self, endpoint: str, params: dict[str, Any]) -> ProviderResponse:
        """Fetch data from the provider endpoint."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        ...
