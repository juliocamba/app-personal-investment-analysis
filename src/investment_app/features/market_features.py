"""Market feature calculations — Phase 3.

All functions accept a list of ``price_eod`` rows sorted by ``price_date``
**descending** (most-recent first).  Returns ``None`` for any metric when
there are insufficient rows or invalid prices.
"""
from __future__ import annotations

import math
from typing import Any


def _close(row: dict[str, Any]) -> float | None:
    """Extract a positive close price from a price row, or return ``None``."""
    val = row.get("close")
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def compute_price_momentum(
    price_rows: list[dict[str, Any]],
    window: int,
) -> float | None:
    """Return the simple price return over *window* trading days.

    ``price_rows`` must be sorted newest-first.  The return is computed as
    ``(close[0] - close[window]) / close[window]``; ``None`` is returned when
    there are fewer than ``window + 1`` rows or prices are invalid.
    """
    if len(price_rows) <= window:
        return None
    close_now = _close(price_rows[0])
    close_then = _close(price_rows[window])
    if close_now is None or close_then is None or close_then == 0:
        return None
    return (close_now - close_then) / close_then


def compute_rolling_volatility(
    price_rows: list[dict[str, Any]],
    window: int,
) -> float | None:
    """Return annualised volatility (std of daily log returns) over *window* days.

    Requires at least ``window + 1`` rows.  Returns ``None`` on insufficient
    data or any invalid/non-positive close price.
    """
    if len(price_rows) < window + 1:
        return None
    closes: list[float] = []
    for row in price_rows[: window + 1]:
        c = _close(row)
        if c is None:
            return None
        closes.append(c)
    log_returns = [
        math.log(closes[i] / closes[i + 1]) for i in range(window)
    ]
    n = len(log_returns)
    if n < 2:
        return None
    mean = sum(log_returns) / n
    variance = sum((r - mean) ** 2 for r in log_returns) / (n - 1)
    return math.sqrt(variance * 252)  # annualise to trading-year convention


def compute_market_features(
    price_rows: list[dict[str, Any]],
) -> dict[str, float | None]:
    """Compute all market features from a price history.

    Parameters
    ----------
    price_rows:
        Rows from ``price_eod`` sorted by ``price_date`` descending.

    Returns
    -------
    dict
        Keys: ``momentum_20d``, ``momentum_60d``, ``momentum_250d``,
        ``volatility_30d``, ``volatility_90d``.
    """
    return {
        "momentum_20d": compute_price_momentum(price_rows, 20),
        "momentum_60d": compute_price_momentum(price_rows, 60),
        "momentum_250d": compute_price_momentum(price_rows, 250),
        "volatility_30d": compute_rolling_volatility(price_rows, 30),
        "volatility_90d": compute_rolling_volatility(price_rows, 90),
    }
