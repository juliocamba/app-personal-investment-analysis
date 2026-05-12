"""Unit tests for CLI commands."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from investment_app.cli import app

runner = CliRunner()


def test_health_exits_zero() -> None:
    result = runner.invoke(app, ["health"])
    assert result.exit_code == 0


def test_health_shows_version() -> None:
    result = runner.invoke(app, ["health"])
    assert "0.1.0" in result.output


def test_health_shows_environment() -> None:
    result = runner.invoke(app, ["health"])
    assert "local" in result.output


def test_config_check_fails_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Secrets are already cleared by conftest autouse fixture.
    result = runner.invoke(app, ["config-check"])
    assert result.exit_code == 1
    output_lower = result.output.lower()
    assert "supabase_url" in output_lower or "SUPABASE_URL" in result.output


def test_config_check_passes_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-key")
    result = runner.invoke(app, ["config-check"])
    assert result.exit_code == 0
    assert "passed" in result.output.lower()


def test_config_check_does_not_reveal_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-value")
    result = runner.invoke(app, ["config-check"])
    assert "super-secret-value" not in result.output


def test_help_is_available() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "health" in result.output
    assert "config-check" in result.output


def test_config_check_fails_when_placeholder_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copying .env.example verbatim must not pass config-check."""
    monkeypatch.setenv("SUPABASE_URL", "https://your-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "replace_me")
    result = runner.invoke(app, ["config-check"])
    assert result.exit_code == 1


def test_config_check_does_not_reveal_placeholder_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error output must show the variable name only, never its value."""
    monkeypatch.setenv("SUPABASE_URL", "https://your-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "replace_me")
    result = runner.invoke(app, ["config-check"])
    assert "your-project.supabase.co" not in result.output
    assert "replace_me" not in result.output
