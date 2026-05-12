"""Shared test fixtures and configuration."""
from __future__ import annotations

from pathlib import Path

import pytest

# Secrets that must never bleed into tests from the developer's real .env
_SECRET_KEYS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "FMP_API_KEY",
    "FINNHUB_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "TWELVE_DATA_API_KEY",
    "SMTP_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
]


@pytest.fixture(autouse=True)
def clear_env_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank out secrets before every test.

    We *set* each key to an empty string rather than deleting it.  When a key
    is deleted, pydantic-settings falls back to the .env file and picks up
    placeholder values (e.g. 'replace_me').  An explicit empty string in
    os.environ takes priority over the .env file, so missing_required() works
    correctly during tests even when a .env file is present.
    """
    for key in _SECRET_KEYS:
        monkeypatch.setenv(key, "")


@pytest.fixture()
def configs_dir() -> Path:
    """Return the absolute path to the configs directory."""
    return Path(__file__).parent.parent / "configs"
