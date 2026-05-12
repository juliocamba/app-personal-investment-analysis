"""Unit tests for investment_app.features.news_features and quality_features."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from investment_app.features.news_features import _parse_date, compute_news_features
from investment_app.features.quality_features import compute_data_quality_score


# ===========================================================================
# news_features
# ===========================================================================


# ---------------------------------------------------------------------------
# _parse_date helper
# ---------------------------------------------------------------------------


def test_parse_date_from_iso_string():
    assert _parse_date("2024-01-15T10:00:00Z") == date(2024, 1, 15)


def test_parse_date_from_iso_string_with_offset():
    assert _parse_date("2024-01-15T10:00:00+05:00") == date(2024, 1, 15)


def test_parse_date_from_datetime_object():
    dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
    assert _parse_date(dt) == date(2024, 1, 15)


def test_parse_date_from_date_object():
    assert _parse_date(date(2024, 1, 15)) == date(2024, 1, 15)


def test_parse_date_none_returns_none():
    assert _parse_date(None) is None


def test_parse_date_invalid_string_returns_none():
    assert _parse_date("not-a-date") is None


# ---------------------------------------------------------------------------
# compute_news_features
# ---------------------------------------------------------------------------


def _make_news(published_at: str, sentiment: float | None = None) -> dict:
    return {
        "published_at": published_at,
        "sentiment_raw": sentiment,
        "title": "Test article",
    }


def test_news_features_empty_rows():
    result = compute_news_features([], as_of=date(2024, 1, 20))
    assert result["news_sentiment_7d"] is None
    assert result["news_volume_7d"] == 0


def test_news_features_counts_within_7d():
    rows = [
        _make_news("2024-01-14T00:00:00Z"),  # 6 days ago: inside window
        _make_news("2024-01-13T00:00:00Z"),  # 7 days ago: on boundary (inclusive)
        _make_news("2024-01-12T00:00:00Z"),  # 8 days ago: outside window
    ]
    result = compute_news_features(rows, as_of=date(2024, 1, 20))
    assert result["news_volume_7d"] == 2


def test_news_features_sentiment_average():
    rows = [
        _make_news("2024-01-18T00:00:00Z", sentiment=0.8),
        _make_news("2024-01-17T00:00:00Z", sentiment=0.4),
        _make_news("2024-01-16T00:00:00Z", sentiment=0.6),
    ]
    result = compute_news_features(rows, as_of=date(2024, 1, 20))
    assert result["news_sentiment_7d"] == pytest.approx((0.8 + 0.4 + 0.6) / 3)


def test_news_features_sentiment_none_when_no_sentiment_values():
    rows = [
        _make_news("2024-01-18T00:00:00Z", sentiment=None),
        _make_news("2024-01-17T00:00:00Z", sentiment=None),
    ]
    result = compute_news_features(rows, as_of=date(2024, 1, 20))
    assert result["news_sentiment_7d"] is None
    assert result["news_volume_7d"] == 2  # still counted


def test_news_features_mixed_sentiment():
    rows = [
        _make_news("2024-01-18T00:00:00Z", sentiment=0.9),
        _make_news("2024-01-17T00:00:00Z", sentiment=None),  # no sentiment
        _make_news("2024-01-15T00:00:00Z", sentiment=0.1),
    ]
    result = compute_news_features(rows, as_of=date(2024, 1, 20))
    # Average of (0.9, 0.1) only; None skipped.
    assert result["news_sentiment_7d"] == pytest.approx(0.5)
    assert result["news_volume_7d"] == 3


def test_news_features_excludes_old_articles():
    rows = [
        _make_news("2024-01-01T00:00:00Z", sentiment=0.9),  # 19 days ago
        _make_news("2023-12-01T00:00:00Z", sentiment=0.5),  # months ago
    ]
    result = compute_news_features(rows, as_of=date(2024, 1, 20))
    assert result["news_volume_7d"] == 0
    assert result["news_sentiment_7d"] is None


# ===========================================================================
# quality_features
# ===========================================================================


def test_full_quality_score_is_100():
    score = compute_data_quality_score(
        has_price=True,
        has_annual_statement=True,
        has_shares=True,
        has_market_cap=True,
        has_fx_if_needed=True,
        has_filings=True,
        has_required_fields=True,
    )
    assert score == 100.0


def test_no_data_quality_score_is_0():
    score = compute_data_quality_score(
        has_price=False,
        has_annual_statement=False,
        has_shares=False,
        has_market_cap=False,
        has_fx_if_needed=False,
        has_filings=False,
        has_required_fields=False,
    )
    assert score == 0.0


def test_partial_quality_score():
    # has_price (20) + has_annual_statement (30) + has_shares (10) = 60
    score = compute_data_quality_score(
        has_price=True,
        has_annual_statement=True,
        has_shares=True,
        has_market_cap=False,
        has_fx_if_needed=False,
        has_filings=False,
        has_required_fields=False,
    )
    assert score == 60.0


def test_quality_score_price_only():
    score = compute_data_quality_score(
        has_price=True,
        has_annual_statement=False,
        has_shares=False,
        has_market_cap=False,
        has_fx_if_needed=False,
        has_filings=False,
        has_required_fields=False,
    )
    assert score == 20.0


def test_quality_score_returns_float():
    score = compute_data_quality_score(
        has_price=True,
        has_annual_statement=False,
        has_shares=False,
        has_market_cap=False,
        has_fx_if_needed=False,
        has_filings=False,
        has_required_fields=False,
    )
    assert isinstance(score, float)
