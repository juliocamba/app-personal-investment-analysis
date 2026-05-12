"""Unit tests for the daily pipeline runner script."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

# scripts/ is not a package; import by path manipulation is already done inside
# the script itself, so we import the Typer app directly from the installed package
# path (scripts/ is on sys.path when the package is installed editable).
# Instead, invoke via subprocess to match real CI usage.
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "run_daily_pipeline.py"


def _run(*args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the pipeline script as a subprocess with a clean environment."""
    import os

    # Build a clean env: keep everything except secrets, then explicitly set
    # secrets to empty string.  We cannot simply remove them because
    # pydantic-settings falls back to the .env file when a key is absent;
    # an explicit empty string in os.environ takes priority over .env.
    _BLANK_KEYS = (
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY",
        "FMP_API_KEY", "FINNHUB_API_KEY", "ALPHA_VANTAGE_API_KEY",
        "TWELVE_DATA_API_KEY", "SMTP_PASSWORD", "TELEGRAM_BOT_TOKEN",
    )
    env = {k: v for k, v in os.environ.items()}
    for key in _BLANK_KEYS:
        env[key] = ""
    env["APP_ENV"] = "local"
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_dry_run_exits_zero_without_secrets() -> None:
    result = _run("--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr


def test_dry_run_reports_company_count() -> None:
    result = _run("--dry-run")
    assert "companies" in result.stdout.lower()


def test_live_run_exits_nonzero_when_secrets_missing() -> None:
    result = _run()  # no --dry-run, no secrets
    assert result.returncode == 1


def test_live_run_reports_missing_variable_names() -> None:
    result = _run()
    assert "SUPABASE_URL" in result.stdout or "supabase_url" in result.stdout.lower()


def test_live_run_does_not_reveal_secret_values() -> None:
    result = _run(env_overrides={"SUPABASE_SERVICE_ROLE_KEY": "very-secret-value"})
    assert "very-secret-value" not in result.stdout
    assert "very-secret-value" not in result.stderr


def test_live_run_exits_nonzero_when_supabase_is_unreachable() -> None:
    result = _run(env_overrides={
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "fake-key",
    })
    assert result.returncode != 0


def test_live_run_exits_nonzero_when_url_is_placeholder() -> None:
    """A copied-from-example URL must abort the live pipeline."""
    result = _run(env_overrides={
        "SUPABASE_URL": "https://your-project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "real-looking-key-abc123",
    })
    assert result.returncode == 1


def test_live_run_exits_nonzero_when_key_is_replace_me() -> None:
    """A 'replace_me' sentinel key must abort the live pipeline."""
    result = _run(env_overrides={
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "replace_me",
    })
    assert result.returncode == 1


def test_live_run_does_not_reveal_placeholder_values() -> None:
    """Error output must show only the variable name, never its value."""
    result = _run(env_overrides={
        "SUPABASE_URL": "https://your-project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "replace_me",
    })
    assert "your-project.supabase.co" not in result.stdout
    assert "replace_me" not in result.stdout
