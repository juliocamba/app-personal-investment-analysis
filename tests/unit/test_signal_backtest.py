"""Unit tests for Phase 12F.1 historical signal-validation helpers."""
from __future__ import annotations

import pytest

from investment_app.backtest import (
    build_signal_backtest_observation,
    build_signal_backtest_observations,
    refresh_signal_backtest_observations,
)


def test_build_observation_uses_first_available_trading_day_on_or_after_horizon() -> None:
    signal_row = {
        "id": "signal-1",
        "company_id": "company-1",
        "signal_date": "2025-01-01",
        "model_version": "signal_rule_v2",
        "valuation_run_id": "valuation-1",
        "final_signal": "buy",
        "p_buy": 0.72,
        "p_buy_adjusted": 0.72,
        "p_sell": 0.12,
    }
    price_rows = [
        {
            "company_id": "company-1",
            "price_date": "2024-12-31",
            "close": 100.0,
            "currency": "USD",
            "market_cap": 1_000.0,
        },
        {
            "company_id": "company-1",
            "price_date": "2025-01-02",
            "close": 101.0,
            "currency": "USD",
            "market_cap": 1_010.0,
        },
        {
            "company_id": "company-1",
            "price_date": "2025-01-31",
            "close": 110.0,
            "currency": "USD",
            "market_cap": 1_100.0,
        },
        {
            "company_id": "company-1",
            "price_date": "2025-04-01",
            "close": 90.0,
            "currency": "USD",
            "market_cap": 900.0,
        },
    ]

    row = build_signal_backtest_observation(
        signal_row,
        company_row={"id": "company-1", "sector": "Technology"},
        valuation_row={
            "id": "valuation-1",
            "margin_of_safety_conservative": 0.1,
            "assumptions": {"diagnostics": {"uncertainty_category": "moderate"}},
        },
        dq_snapshot_row=None,
        price_rows=price_rows,
    )

    assert row["signal_price"] == 100.0
    assert row["price_30d"] == 110.0
    assert row["price_date_30d"] == "2025-01-31"
    assert row["has_price_30d"] is True
    assert row["coverage_gap_30d"] is False
    assert row["return_30d"] == pytest.approx(0.1)
    assert row["price_90d"] == 90.0
    assert row["price_date_90d"] == "2025-04-01"
    assert row["readiness_status_at_signal"] is None


def test_build_observation_prefers_exact_signal_date_price_for_anchor() -> None:
    signal_row = {
        "id": "signal-exact",
        "company_id": "company-exact",
        "signal_date": "2025-01-15",
        "model_version": "signal_rule_v2",
        "valuation_run_id": None,
        "final_signal": "buy",
        "p_buy": 0.7,
        "p_buy_adjusted": 0.7,
        "p_sell": 0.1,
    }
    price_rows = [
        {
            "company_id": "company-exact",
            "price_date": "2025-01-14",
            "close": 95.0,
            "currency": "USD",
            "market_cap": 950.0,
        },
        {
            "company_id": "company-exact",
            "price_date": "2025-01-15",
            "close": 100.0,
            "currency": "USD",
            "market_cap": 1_000.0,
        },
        {
            "company_id": "company-exact",
            "price_date": "2025-02-14",
            "close": 105.0,
            "currency": "USD",
            "market_cap": 1_050.0,
        },
    ]

    row = build_signal_backtest_observation(
        signal_row,
        company_row={"id": "company-exact", "sector": "Technology"},
        valuation_row=None,
        dq_snapshot_row=None,
        price_rows=price_rows,
    )

    assert row["signal_price"] == 100.0
    assert row["signal_price_currency"] == "USD"
    assert row["return_30d"] == pytest.approx(0.05)


def test_build_observation_uses_most_recent_prior_price_when_exact_signal_date_price_missing() -> None:
    signal_row = {
        "id": "signal-prior",
        "company_id": "company-prior",
        "signal_date": "2025-01-15",
        "model_version": "signal_rule_v2",
        "valuation_run_id": None,
        "final_signal": "hold",
        "p_buy": 0.5,
        "p_buy_adjusted": 0.5,
        "p_sell": 0.2,
    }
    price_rows = [
        {
            "company_id": "company-prior",
            "price_date": "2025-01-10",
            "close": 90.0,
            "currency": "USD",
            "market_cap": 900.0,
        },
        {
            "company_id": "company-prior",
            "price_date": "2025-01-14",
            "close": 95.0,
            "currency": "USD",
            "market_cap": 950.0,
        },
        {
            "company_id": "company-prior",
            "price_date": "2025-02-14",
            "close": 104.5,
            "currency": "USD",
            "market_cap": 1_045.0,
        },
    ]

    row = build_signal_backtest_observation(
        signal_row,
        company_row={"id": "company-prior", "sector": "Industrials"},
        valuation_row=None,
        dq_snapshot_row=None,
        price_rows=price_rows,
    )

    assert row["signal_price"] == 95.0
    assert row["market_cap_at_signal"] == 950.0
    assert row["return_30d"] == pytest.approx(0.1)


def test_build_observation_does_not_use_future_price_as_signal_anchor() -> None:
    signal_row = {
        "id": "signal-future-only",
        "company_id": "company-future-only",
        "signal_date": "2025-01-15",
        "model_version": "signal_rule_v2",
        "valuation_run_id": None,
        "final_signal": "sell",
        "p_buy": 0.1,
        "p_buy_adjusted": 0.1,
        "p_sell": 0.8,
    }
    price_rows = [
        {
            "company_id": "company-future-only",
            "price_date": "2025-01-16",
            "close": 110.0,
            "currency": "USD",
            "market_cap": 1_100.0,
        },
        {
            "company_id": "company-future-only",
            "price_date": "2025-02-14",
            "close": 120.0,
            "currency": "USD",
            "market_cap": 1_200.0,
        },
    ]

    row = build_signal_backtest_observation(
        signal_row,
        company_row={"id": "company-future-only", "sector": "Energy"},
        valuation_row=None,
        dq_snapshot_row=None,
        price_rows=price_rows,
    )

    assert row["signal_price"] is None
    assert row["signal_price_currency"] is None
    assert row["return_30d"] is None
    assert row["has_price_30d"] is False
    assert row["coverage_gap_30d"] is True


def test_build_observation_leaves_missing_forward_prices_null_without_imputation() -> None:
    signal_row = {
        "id": "signal-2",
        "company_id": "company-2",
        "signal_date": "2025-01-01",
        "model_version": "signal_rule_v2",
        "valuation_run_id": None,
        "final_signal": "hold",
        "p_buy": 0.4,
        "p_buy_adjusted": 0.4,
        "p_sell": 0.25,
    }
    price_rows = [
        {
            "company_id": "company-2",
            "price_date": "2024-12-31",
            "close": 50.0,
            "currency": "USD",
            "market_cap": None,
        },
        {
            "company_id": "company-2",
            "price_date": "2025-01-02",
            "close": 51.0,
            "currency": "USD",
            "market_cap": None,
        },
    ]

    row = build_signal_backtest_observation(
        signal_row,
        company_row={"id": "company-2", "sector": "Utilities"},
        valuation_row=None,
        dq_snapshot_row=None,
        price_rows=price_rows,
    )

    assert row["signal_price"] == 50.0
    assert row["price_30d"] is None
    assert row["return_30d"] is None
    assert row["has_price_30d"] is False
    assert row["coverage_gap_30d"] is True
    assert row["price_365d"] is None
    assert row["coverage_gap_365d"] is True


def test_build_observations_uses_exact_signal_date_for_historical_data_quality_snapshot() -> None:
    signal_rows = [
        {
            "id": "signal-3",
            "company_id": "company-3",
            "signal_date": "2025-02-10",
            "model_version": "signal_rule_v2",
            "valuation_run_id": None,
            "final_signal": "sell",
            "p_buy": 0.1,
            "p_buy_adjusted": 0.1,
            "p_sell": 0.7,
        }
    ]
    observations = build_signal_backtest_observations(
        signal_rows,
        companies=[{"id": "company-3", "sector": "Financials"}],
        valuation_rows=[],
        dq_snapshots=[
            {
                "company_id": "company-3",
                "snapshot_date": "2025-02-10",
                "price_validation_status": "critical",
                "warning_codes": ["price_divergence_critical"],
                "details": {},
            },
            {
                "company_id": "company-3",
                "snapshot_date": "2025-03-10",
                "price_validation_status": "ok",
                "warning_codes": [],
                "details": {},
            },
        ],
        price_rows=[
            {
                "company_id": "company-3",
                "price_date": "2025-02-10",
                "close": 80.0,
                "currency": "USD",
                "market_cap": 2_000.0,
            },
            {
                "company_id": "company-3",
                "price_date": "2025-03-12",
                "close": 76.0,
                "currency": "USD",
                "market_cap": 1_900.0,
            },
        ],
    )

    assert observations[0]["data_quality_status_at_signal"] == "critical"


def test_refresh_signal_backtest_observations_reads_only_persisted_sources_and_upserts() -> None:
    class RepoStub:
        def __init__(self) -> None:
            self.upserted_rows = []

        def list_signal_runs_for_backtest(self, *, client=None):
            return [{
                "id": "signal-4",
                "company_id": "company-4",
                "signal_date": "2025-01-15",
                "model_version": "signal_rule_v2",
                "valuation_run_id": "valuation-4",
                "final_signal": "strong_buy",
                "p_buy": 0.9,
                "p_buy_adjusted": 0.88,
                "p_sell": 0.05,
            }]

        def list_companies_for_backtest(self, *, client=None):
            return [{"id": "company-4", "sector": "Industrials"}]

        def list_valuation_runs_for_backtest(self, *, client=None):
            return [{
                "id": "valuation-4",
                "company_id": "company-4",
                "margin_of_safety_conservative": 0.22,
                "assumptions": {"diagnostics": {"uncertainty_category": "low"}},
            }]

        def list_company_data_quality_snapshots_for_backtest(self, *, client=None):
            return []

        def list_price_history_for_backtest(self, *, client=None):
            return [
                {
                    "company_id": "company-4",
                    "price_date": "2025-01-15",
                    "close": 20.0,
                    "currency": "USD",
                    "market_cap": 500.0,
                },
                {
                    "company_id": "company-4",
                    "price_date": "2025-02-14",
                    "close": 24.0,
                    "currency": "USD",
                    "market_cap": 600.0,
                },
            ]

        def upsert_signal_backtest_observations(self, rows, *, client=None):
            self.upserted_rows = rows
            return len(rows)

    repo = RepoStub()
    written = refresh_signal_backtest_observations(repo_module=repo)

    assert written == 1
    assert len(repo.upserted_rows) == 1
    assert repo.upserted_rows[0]["signal_run_id"] == "signal-4"
    assert repo.upserted_rows[0]["valuation_mos_at_signal"] == 0.22
    assert repo.upserted_rows[0]["return_30d"] == pytest.approx(0.2)
