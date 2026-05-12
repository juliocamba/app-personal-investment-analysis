"""Unit tests for utility modules."""
from __future__ import annotations

from datetime import date, timezone

from investment_app.utils.checksum import sha256_json, sha256_str
from investment_app.utils.dates import to_iso_date, today_utc, utc_now


# ── Checksum ──────────────────────────────────────────────────────────────────

def test_sha256_str_deterministic() -> None:
    assert sha256_str("hello") == sha256_str("hello")


def test_sha256_str_different_inputs() -> None:
    assert sha256_str("hello") != sha256_str("world")


def test_sha256_str_returns_hex_string() -> None:
    result = sha256_str("test")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_sha256_json_key_order_independent() -> None:
    a = sha256_json({"b": 2, "a": 1})
    b = sha256_json({"a": 1, "b": 2})
    assert a == b


def test_sha256_json_different_values() -> None:
    assert sha256_json({"a": 1}) != sha256_json({"a": 2})


# ── Dates ─────────────────────────────────────────────────────────────────────

def test_utc_now_is_timezone_aware() -> None:
    dt = utc_now()
    assert dt.tzinfo == timezone.utc


def test_today_utc_returns_date_type() -> None:
    d = today_utc()
    assert isinstance(d, date)


def test_to_iso_date_format() -> None:
    d = date(2024, 1, 15)
    assert to_iso_date(d) == "2024-01-15"
