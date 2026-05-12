"""Unit tests for investment_app.features.market_features."""
from __future__ import annotations

import math

import pytest

from investment_app.features.market_features import (
    compute_market_features,
    compute_price_momentum,
    compute_rolling_volatility,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _price_rows(closes: list[float]) -> list[dict]:
    """Build a list of price rows sorted newest-first from *closes* list."""
    return [{"price_date": f"2024-01-{(len(closes) - i):02d}", "close": c} for i, c in enumerate(closes)]


# ---------------------------------------------------------------------------
# compute_price_momentum
# ---------------------------------------------------------------------------


def test_momentum_insufficient_data_returns_none():
    rows = _price_rows([100.0] * 10)  # only 10 rows, window=20
    assert compute_price_momentum(rows, 20) is None


def test_momentum_exact_boundary_returns_none():
    # Need window+1 rows; exactly window rows is not enough.
    rows = _price_rows([100.0] * 20)
    assert compute_price_momentum(rows, 20) is None


def test_momentum_positive_return():
    # Most recent price higher than 20 days ago.
    closes = [110.0] + [100.0] * 25  # closes[0]=110, closes[20]=100
    rows = _price_rows(closes)
    result = compute_price_momentum(rows, 20)
    assert result == pytest.approx(0.10)


def test_momentum_negative_return():
    closes = [90.0] + [100.0] * 25
    rows = _price_rows(closes)
    result = compute_price_momentum(rows, 20)
    assert result == pytest.approx(-0.10)


def test_momentum_zero_base_price_returns_none():
    closes = [110.0] + [0.0] * 25
    rows = _price_rows(closes)
    assert compute_price_momentum(rows, 20) is None


def test_momentum_none_close_returns_none():
    rows = [{"price_date": f"2024-01-{i:02d}", "close": None} for i in range(30)]
    assert compute_price_momentum(rows, 20) is None


def test_momentum_empty_rows_returns_none():
    assert compute_price_momentum([], 20) is None


# ---------------------------------------------------------------------------
# compute_rolling_volatility
# ---------------------------------------------------------------------------


def test_volatility_insufficient_data_returns_none():
    rows = _price_rows([100.0] * 10)
    assert compute_rolling_volatility(rows, 30) is None


def test_volatility_constant_prices_returns_zero():
    # Constant price → zero log returns → zero std → zero volatility.
    rows = _price_rows([100.0] * 35)
    result = compute_rolling_volatility(rows, 30)
    assert result == pytest.approx(0.0, abs=1e-10)


def test_volatility_returns_positive_float():
    import random

    random.seed(42)
    closes = [100.0]
    for _ in range(100):
        closes.append(closes[-1] * (1 + random.gauss(0, 0.01)))
    rows = _price_rows(closes)
    result = compute_rolling_volatility(rows, 30)
    assert result is not None
    assert result > 0


def test_volatility_none_close_returns_none():
    rows = [{"price_date": f"2024-01-{i:02d}", "close": None} for i in range(35)]
    assert compute_rolling_volatility(rows, 30) is None


def test_volatility_annualised():
    """Verify annualisation factor: daily vol × sqrt(252) == annualised vol."""
    # One row with a large drop followed by flat; gives a known daily vol.
    closes = [100.0, 99.0] + [99.0] * 32
    rows = _price_rows(closes)
    daily_returns = [math.log(closes[i] / closes[i + 1]) for i in range(30)]
    n = len(daily_returns)
    mean = sum(daily_returns) / n
    variance = sum((r - mean) ** 2 for r in daily_returns) / (n - 1)
    expected_annual = math.sqrt(variance * 252)
    result = compute_rolling_volatility(rows, 30)
    assert result == pytest.approx(expected_annual, rel=1e-6)


# ---------------------------------------------------------------------------
# compute_market_features (integration)
# ---------------------------------------------------------------------------


def test_compute_market_features_empty_returns_all_none():
    result = compute_market_features([])
    assert result["momentum_20d"] is None
    assert result["momentum_60d"] is None
    assert result["momentum_250d"] is None
    assert result["volatility_30d"] is None
    assert result["volatility_90d"] is None


def test_compute_market_features_keys_present():
    rows = _price_rows([100.0] * 5)
    result = compute_market_features(rows)
    expected_keys = {"momentum_20d", "momentum_60d", "momentum_250d", "volatility_30d", "volatility_90d"}
    assert set(result.keys()) == expected_keys


def test_compute_market_features_with_sufficient_data():
    closes = [100.0 * (1 + 0.001 * i) for i in range(300)]
    closes.reverse()  # newest first
    rows = _price_rows(closes)
    result = compute_market_features(rows)
    # With enough data, 20d, 60d, 250d momentum should all be non-None.
    assert result["momentum_20d"] is not None
    assert result["momentum_60d"] is not None
    assert result["momentum_250d"] is not None
    assert result["volatility_30d"] is not None
    assert result["volatility_90d"] is not None
