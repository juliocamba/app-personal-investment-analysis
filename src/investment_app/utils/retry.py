"""Retry decorator for external API calls."""
from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

# Default retry policy: 3 attempts with exponential back-off (1 s → 10 s).
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
