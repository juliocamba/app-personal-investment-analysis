"""Unit tests for settings module."""
from __future__ import annotations

import pytest

from investment_app.config.settings import Settings, get_settings


def test_default_settings_load() -> None:
    settings = Settings()
    assert settings.app_env == "local"
    assert settings.log_level == "INFO"
    assert settings.app_version == "0.1.0"
    assert settings.smtp_enabled is False
    assert settings.telegram_enabled is False


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.app_env == "ci"
    assert settings.log_level == "DEBUG"


def test_missing_required_when_empty() -> None:
    settings = Settings()
    missing = settings.missing_required()
    assert "supabase_url" in missing
    assert "supabase_service_role_key" in missing


def test_missing_required_clears_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    settings = Settings()
    assert settings.missing_required() == []


def test_get_settings_returns_settings_instance() -> None:
    result = get_settings()
    assert isinstance(result, Settings)


def test_smtp_port_default() -> None:
    settings = Settings()
    assert settings.smtp_port == 587


def test_data_provider_primary_default() -> None:
    settings = Settings()
    assert settings.data_provider_primary == "fmp"


def test_app_env_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings()


def test_app_env_accepts_all_valid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("local", "ci", "production"):
        monkeypatch.setenv("APP_ENV", value)
        settings = Settings()
        assert settings.app_env == value


# ── Placeholder detection ─────────────────────────────────────────────────────

def test_missing_required_when_url_is_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copied-from-example URL must be treated as unconfigured."""
    monkeypatch.setenv("SUPABASE_URL", "https://your-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "real-looking-key-abc123")
    settings = Settings()
    assert "supabase_url" in settings.missing_required()


def test_missing_required_when_key_is_replace_me(monkeypatch: pytest.MonkeyPatch) -> None:
    """'replace_me' sentinel must be treated as unconfigured."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "replace_me")
    settings = Settings()
    assert "supabase_service_role_key" in settings.missing_required()


def test_missing_required_clears_when_real_values_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real (non-placeholder) values must clear the required list."""
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefgh.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake")
    settings = Settings()
    assert settings.missing_required() == []


def test_is_placeholder_detects_known_sentinels() -> None:
    from investment_app.config.settings import _is_placeholder

    assert _is_placeholder("replace_me")
    assert _is_placeholder("https://your-project.supabase.co")
    assert _is_placeholder("REPLACE_ME")          # case-insensitive
    assert _is_placeholder("changeme")
    assert _is_placeholder("TODO")
    assert _is_placeholder("placeholder_value")
    assert not _is_placeholder("https://abcdefgh.supabase.co")
    assert not _is_placeholder("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.real")
