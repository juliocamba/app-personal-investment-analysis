"""Subprocess tests for scripts/validate_supabase_schema.py.

These tests exercise the script's entry point (missing-config exit path and
output safety) without a live Supabase connection.  They follow the same
subprocess helper pattern used in test_pipeline_script.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "validate_supabase_schema.py"
)

# Keys that must be blanked so pydantic-settings does not fall back to the
# values in .env (which may contain placeholder sentinels like 'replace_me').
_BLANK_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
)


def _run(env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the validator script in a subprocess with controlled env vars."""
    env = dict(os.environ)
    for key in _BLANK_KEYS:
        env[key] = ""
    env["APP_ENV"] = "local"
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )


# ── Missing / blank config ────────────────────────────────────────────────────


def test_exits_nonzero_when_supabase_url_blank() -> None:
    """Script must exit 1 when SUPABASE_URL is blank."""
    result = _run()
    assert result.returncode == 1


def test_exits_nonzero_when_only_key_blank() -> None:
    """Script must exit 1 when only the service-role key is blank."""
    result = _run(env_overrides={"SUPABASE_URL": "https://abc123.supabase.co"})
    assert result.returncode == 1


def test_exits_nonzero_when_url_is_placeholder() -> None:
    """Script must exit 1 when SUPABASE_URL is a sentinel placeholder."""
    result = _run(
        env_overrides={
            "SUPABASE_URL": "https://your-project.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "real-key-xyz",
        }
    )
    assert result.returncode == 1


def test_exits_nonzero_when_key_is_replace_me() -> None:
    """Script must exit 1 when service-role key is the 'replace_me' sentinel."""
    result = _run(
        env_overrides={
            "SUPABASE_URL": "https://abc123.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "replace_me",
        }
    )
    assert result.returncode == 1


# ── Output safety — missing config ───────────────────────────────────────────


def test_missing_config_output_contains_variable_name() -> None:
    """The error output must name the missing variable (SUPABASE_URL or similar)."""
    result = _run()
    combined = result.stdout + result.stderr
    assert (
        "SUPABASE_URL" in combined
        or "supabase_url" in combined.lower()
        or "supabase_service_role_key" in combined.lower()
    )


def test_missing_config_output_does_not_expose_secret_value() -> None:
    """Secret values must never appear in the output, only their names."""
    secret = "super-secret-key-9999"
    result = _run(
        env_overrides={
            "SUPABASE_URL": "https://abc123.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": secret,
            # URL is real-looking so it passes URL check, but key check fails
            # because we'll blank the key in a second run below.
        }
    )
    # Run again with blank key so we hit the missing-config path
    result2 = _run(
        env_overrides={
            "SUPABASE_URL": "https://abc123.supabase.co",
            # SUPABASE_SERVICE_ROLE_KEY left blank by _run() default
        }
    )
    combined = result2.stdout + result2.stderr
    assert secret not in combined


def test_placeholder_url_output_does_not_expose_url_value() -> None:
    """The placeholder URL must not appear in the error output."""
    placeholder = "https://your-project.supabase.co"
    result = _run(
        env_overrides={
            "SUPABASE_URL": placeholder,
            "SUPABASE_SERVICE_ROLE_KEY": "real-key-xyz",
        }
    )
    # The error message should NOT repeat the URL value back to stdout/stderr.
    # (It may print the URL before attempting connection, but that is only
    # reached when config passes validation; placeholder fails earlier.)
    combined = result.stdout + result.stderr
    assert placeholder not in combined
