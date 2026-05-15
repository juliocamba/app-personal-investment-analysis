"""Schema validation helpers for the Supabase database.

Separated from the CLI script so the logic is easily unit-tested
without invoking a subprocess.
"""
from __future__ import annotations

from typing import Any

REQUIRED_TABLES: tuple[str, ...] = (
    "companies",
    "watchlists",
    "watchlist_companies",
    "raw_provider_payloads",
    "price_eod",
    "filings_index",
    "statements_norm",
    "ratios_factors",
    "qualitative_scores",
    "valuation_runs",
    "signal_runs",
    "alert_rules",
    "alert_history",
    "pipeline_runs",
    "company_analysis_readiness",
)


def validate_tables(client: Any) -> tuple[list[str], list[str]]:
    """Probe each required table and return ``(present, missing)`` name lists.

    Uses ``SELECT id LIMIT 1`` on every table so no meaningful data is read.
    The service-role key bypasses RLS, so this works even on tables with
    restrictive authenticated-user policies.

    Args:
        client: An initialised Supabase ``Client`` instance.

    Returns:
        A 2-tuple of ``(present_tables, missing_tables)`` as string lists.
    """
    present: list[str] = []
    missing: list[str] = []
    for table in REQUIRED_TABLES:
        try:
            client.table(table).select("id").limit(1).execute()
            present.append(table)
        except Exception:  # noqa: BLE001
            missing.append(table)
    return present, missing
