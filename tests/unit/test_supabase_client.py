"""Unit tests for investment_app.db.supabase_client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_get_supabase_client_raises_when_url_blank() -> None:
    """ValueError raised when SUPABASE_URL is blank (autouse fixture blanks it)."""
    from investment_app.db.supabase_client import get_supabase_client

    with pytest.raises(ValueError, match="configure"):
        get_supabase_client()


def test_get_supabase_client_raises_when_key_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError raised when only the service-role key is blank."""
    monkeypatch.setenv("SUPABASE_URL", "https://abc123.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")

    from investment_app.db.supabase_client import get_supabase_client

    with pytest.raises(ValueError, match="configure"):
        get_supabase_client()


def test_get_supabase_client_raises_on_placeholder_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError raised when URL still holds a placeholder sentinel value."""
    monkeypatch.setenv("SUPABASE_URL", "https://your-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "real-service-key-xyz")

    from investment_app.db.supabase_client import get_supabase_client

    with pytest.raises(ValueError, match="configure"):
        get_supabase_client()


def test_get_supabase_client_raises_on_replace_me_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError raised when the service-role key is the 'replace_me' sentinel."""
    monkeypatch.setenv("SUPABASE_URL", "https://abc123.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "replace_me")

    from investment_app.db.supabase_client import get_supabase_client

    with pytest.raises(ValueError, match="configure"):
        get_supabase_client()


def test_get_supabase_client_calls_create_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_supabase_client() delegates to create_client with the correct args."""
    monkeypatch.setenv("SUPABASE_URL", "https://abc123.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "real-service-key-xyz")

    fake_client = MagicMock()
    with patch(
        "investment_app.db.supabase_client.create_client", return_value=fake_client
    ) as mock_create:
        from investment_app.db.supabase_client import get_supabase_client

        result = get_supabase_client()

    mock_create.assert_called_once_with(
        "https://abc123.supabase.co", "real-service-key-xyz"
    )
    assert result is fake_client


def test_get_supabase_client_error_message_omits_secret_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError message must contain the variable NAME, not its value."""
    monkeypatch.setenv("SUPABASE_URL", "https://abc123.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")

    from investment_app.db.supabase_client import get_supabase_client

    with pytest.raises(ValueError) as exc_info:
        get_supabase_client()

    msg = str(exc_info.value)
    assert "SUPABASE_SERVICE_ROLE_KEY" in msg
    # The actual blank value must not appear — there is nothing to leak here,
    # but we verify the name is used for diagnostics.
    assert "abc123" not in msg
