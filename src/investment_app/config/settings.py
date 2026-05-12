"""Application settings loaded from environment variables."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Lowercase substrings that indicate a value was copied from .env.example
# and never replaced with a real credential.
_PLACEHOLDER_PATTERNS: frozenset[str] = frozenset({
    "replace_me",
    "your-project",
    "your_project_url",
    "your_service_role_key",
    "your_anon_key",
    "changeme",
    "todo",
    "placeholder",
})


def _is_placeholder(value: str) -> bool:
    """Return True when *value* looks like an unconfigured example placeholder."""
    lower = value.lower()
    return any(pattern in lower for pattern in _PLACEHOLDER_PATTERNS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    app_env: Literal["local", "ci", "production"] = Field(default="local")
    log_level: str = Field(default="INFO")
    app_version: str = Field(default="0.1.0")

    # Supabase
    supabase_url: str = Field(default="")
    supabase_service_role_key: str = Field(default="")
    supabase_anon_key: str = Field(default="")

    # Data providers
    data_provider_primary: str = Field(default="fmp")
    fmp_api_key: str = Field(default="")
    finnhub_api_key: str = Field(default="")
    alpha_vantage_api_key: str = Field(default="")
    twelve_data_api_key: str = Field(default="")
    sec_user_agent: str = Field(default="")

    # SMTP
    smtp_enabled: bool = Field(default=False)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    alert_email_from: str = Field(default="")
    alert_email_to: str = Field(default="")

    # Telegram
    telegram_enabled: bool = Field(default=False)
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    # Alerts
    alerts_enabled: bool = Field(default=False)

    @property
    def required_for_production(self) -> list[str]:
        """Field names that must be non-empty in CI or production."""
        return ["supabase_url", "supabase_service_role_key"]

    def missing_required(self) -> list[str]:
        """Return names of required fields that are empty or still placeholder-valued.

        A field is considered missing when its value is either empty or contains
        a known placeholder substring (e.g. 'replace_me', 'your-project').  This
        catches the common mistake of copying .env.example to .env without filling
        in real credentials.  Only the field *name* is ever returned; the actual
        value is never exposed in error output.
        """
        return [
            name
            for name in self.required_for_production
            if not getattr(self, name) or _is_placeholder(getattr(self, name))
        ]


def get_settings() -> Settings:
    """Create and return a Settings instance."""
    return Settings()
