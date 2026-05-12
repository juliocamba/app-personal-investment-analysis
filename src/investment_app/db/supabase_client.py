"""Supabase backend client.

Creates a service-role Supabase client for trusted backend use only.
Never use this module in frontend code or expose the service-role key publicly.
"""
from __future__ import annotations

from supabase import Client, create_client

from investment_app.config.settings import get_settings


def get_supabase_client() -> Client:
    """Create and return a Supabase service-role client.

    Raises:
        ValueError: if SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY are missing
            or still hold placeholder/sentinel values.
    """
    settings = get_settings()
    invalid = settings.missing_required()
    if invalid:
        names = ", ".join(n.upper() for n in sorted(invalid))
        raise ValueError(
            f"Cannot create Supabase client: configure {names} before connecting."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
