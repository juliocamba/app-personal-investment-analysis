"""Historical signal-validation helpers for Phase 12F.1.

This module builds a point-in-time-safe research dataset from already
persisted signal and price history. It is intentionally separate from live
signal generation and does not make strategy or performance claims.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from investment_app.db import repositories

HORIZON_DAYS: tuple[int, ...] = (30, 90, 180, 365)
_DQ_WARNING_CODES = (
    "price_divergence_warning",
    "price_divergence_critical",
    "incomplete_statement_set",
    "missing_key_fields",
    "insufficient_period_coverage",
    "fundamentals_provider_discrepancy",
)


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _compute_data_quality_status(snapshot: dict[str, Any] | None) -> str | None:
    """Mirror the historical status derivation without using latest-only views."""
    if not snapshot:
        return None
    warning_codes = snapshot.get("warning_codes") or []
    if not warning_codes:
        return "healthy"

    details = snapshot.get("details") or {}
    provider_comparison = details.get("fundamentals_provider_comparison") or {}
    discrepancy_level = provider_comparison.get("discrepancy_level")
    if snapshot.get("price_validation_status") == "critical" or discrepancy_level == "critical":
        return "critical"

    if not any(code in warning_codes for code in _DQ_WARNING_CODES):
        return "not_comparable"
    return "warning"


def _first_price_on_or_after(
    price_rows: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any] | None:
    for row in price_rows:
        row_date = _parse_date(row.get("price_date"))
        if row_date is None:
            continue
        if row_date >= target_date and row.get("close") is not None:
            return row
    return None


def _latest_price_on_or_before(
    price_rows: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any] | None:
    latest_match: dict[str, Any] | None = None
    latest_date: date | None = None
    for row in price_rows:
        row_date = _parse_date(row.get("price_date"))
        if row_date is None or row.get("close") is None:
            continue
        if row_date <= target_date and (latest_date is None or row_date > latest_date):
            latest_match = row
            latest_date = row_date
    return latest_match


def build_signal_backtest_observation(
    signal_row: dict[str, Any],
    *,
    company_row: dict[str, Any] | None,
    valuation_row: dict[str, Any] | None,
    dq_snapshot_row: dict[str, Any] | None,
    price_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one persisted research observation from historical signal state."""
    signal_date = _parse_date(signal_row["signal_date"])
    if signal_date is None:  # pragma: no cover - defensive only
        raise ValueError("signal_date is required")

    anchor_price = _latest_price_on_or_before(price_rows, signal_date)
    signal_price = anchor_price.get("close") if anchor_price else None
    signal_currency = anchor_price.get("currency") if anchor_price else None
    signal_market_cap = anchor_price.get("market_cap") if anchor_price else None

    assumptions = (valuation_row or {}).get("assumptions") or {}
    diagnostics = assumptions.get("diagnostics") or {}

    observation: dict[str, Any] = {
        "signal_run_id": signal_row["id"],
        "company_id": signal_row["company_id"],
        "signal_date": signal_row["signal_date"],
        "model_version": signal_row["model_version"],
        "final_signal": signal_row["final_signal"],
        "p_buy": signal_row.get("p_buy"),
        "p_buy_adjusted": signal_row.get("p_buy_adjusted"),
        "p_sell": signal_row.get("p_sell"),
        "signal_price": signal_price,
        "signal_price_currency": signal_currency,
        # Historical readiness snapshots do not exist as a time series yet.
        "readiness_status_at_signal": None,
        "data_quality_status_at_signal": _compute_data_quality_status(dq_snapshot_row),
        "sector_at_signal": (company_row or {}).get("sector"),
        "market_cap_at_signal": signal_market_cap,
        "valuation_mos_at_signal": (valuation_row or {}).get("margin_of_safety_conservative"),
        "valuation_uncertainty_category_at_signal": diagnostics.get("uncertainty_category"),
    }

    for horizon in HORIZON_DAYS:
        forward_price = _first_price_on_or_after(price_rows, signal_date + timedelta(days=horizon))
        has_price = bool(
            anchor_price
            and forward_price
            and anchor_price.get("currency")
            and forward_price.get("currency") == anchor_price.get("currency")
        )
        observation[f"price_{horizon}d"] = forward_price.get("close") if has_price else None
        observation[f"price_date_{horizon}d"] = (
            forward_price.get("price_date") if has_price else None
        )
        observation[f"has_price_{horizon}d"] = has_price
        observation[f"coverage_gap_{horizon}d"] = not has_price
        observation[f"return_{horizon}d"] = (
            (forward_price["close"] / anchor_price["close"]) - 1
            if has_price and anchor_price["close"]
            else None
        )

    return observation


def build_signal_backtest_observations(
    signal_rows: list[dict[str, Any]],
    *,
    companies: list[dict[str, Any]],
    valuation_rows: list[dict[str, Any]],
    dq_snapshots: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build all observation rows from persisted historical inputs only."""
    companies_by_id = {row["id"]: row for row in companies}
    valuations_by_id = {row["id"]: row for row in valuation_rows if row.get("id")}
    dq_by_company_date = {
        (row["company_id"], row["snapshot_date"]): row
        for row in dq_snapshots
        if row.get("company_id") and row.get("snapshot_date")
    }
    prices_by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in price_rows:
        company_id = row.get("company_id")
        if company_id:
            prices_by_company[company_id].append(row)
    for rows in prices_by_company.values():
        rows.sort(key=lambda row: row.get("price_date") or "")

    observations: list[dict[str, Any]] = []
    for signal_row in signal_rows:
        signal_date = signal_row["signal_date"]
        observations.append(
            build_signal_backtest_observation(
                signal_row,
                company_row=companies_by_id.get(signal_row["company_id"]),
                valuation_row=valuations_by_id.get(signal_row.get("valuation_run_id")),
                dq_snapshot_row=dq_by_company_date.get((signal_row["company_id"], signal_date)),
                price_rows=prices_by_company.get(signal_row["company_id"], []),
            )
        )
    return observations


def refresh_signal_backtest_observations(
    *,
    client: Any = None,
    repo_module: Any = repositories,
) -> int:
    """Refresh the persisted research dataset from already stored history only."""
    signal_rows = repo_module.list_signal_runs_for_backtest(client=client)
    if not signal_rows:
        return 0

    observations = build_signal_backtest_observations(
        signal_rows,
        companies=repo_module.list_companies_for_backtest(client=client),
        valuation_rows=repo_module.list_valuation_runs_for_backtest(client=client),
        dq_snapshots=repo_module.list_company_data_quality_snapshots_for_backtest(client=client),
        price_rows=repo_module.list_price_history_for_backtest(client=client),
    )
    return repo_module.upsert_signal_backtest_observations(
        observations,
        client=client,
    )
