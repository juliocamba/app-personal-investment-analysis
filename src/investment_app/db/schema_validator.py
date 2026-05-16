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
    "positions",
    "position_entry_profiles",
    "position_review_alerts",
    "alert_rules",
    "alert_history",
    "pipeline_runs",
    "company_analysis_readiness",
    "company_data_quality_snapshots",
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
            # Use SELECT * LIMIT 0 so the probe is column-agnostic (not all
            # tables have an "id" column — e.g. company_analysis_readiness uses
            # company_id as its PK) and does not fetch real rows.
            client.table(table).select("*").limit(0).execute()
            present.append(table)
        except Exception:  # noqa: BLE001
            missing.append(table)
    return present, missing
