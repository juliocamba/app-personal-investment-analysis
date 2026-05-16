"""Unit tests for investment_app.db.repositories."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from investment_app.db import repositories as repo


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_client(data: list[dict[str, Any]]) -> MagicMock:
    """Return a mock Supabase client whose .execute() always yields *data*."""
    response = MagicMock()
    response.data = data

    mock = MagicMock()
    # SELECT chains: .select().eq().execute() and .select().eq().limit().execute()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        response
    )
    mock.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
        response
    )
    # INSERT chain: .insert().execute()
    mock.table.return_value.insert.return_value.execute.return_value = response
    # UPDATE chain: .update().eq().execute()
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        response
    )
    return mock


# ── list_active_companies ─────────────────────────────────────────────────────


def test_list_active_companies_returns_data() -> None:
    rows = [{"id": "1", "ticker": "AAPL"}, {"id": "2", "ticker": "MSFT"}]
    client = _make_client(rows)

    result = repo.list_active_companies(client=client)

    assert result == rows
    client.table.assert_called_once_with("companies")


def test_list_active_companies_filters_active() -> None:
    client = _make_client([])
    repo.list_active_companies(client=client)

    # Verify the .eq("active", True) call was made
    client.table.return_value.select.return_value.eq.assert_called_once_with(
        "active", True
    )


def test_list_active_companies_empty_result() -> None:
    client = _make_client([])
    assert repo.list_active_companies(client=client) == []


# ── get_company_by_ticker ─────────────────────────────────────────────────────


def test_get_company_by_ticker_found() -> None:
    row = {"id": "abc", "ticker": "AAPL", "name": "Apple Inc."}
    client = _make_client([row])

    result = repo.get_company_by_ticker("aapl", client=client)

    assert result == row


def test_get_company_by_ticker_uppercases_input() -> None:
    client = _make_client([{"id": "1", "ticker": "AAPL"}])
    repo.get_company_by_ticker("aapl", client=client)

    client.table.return_value.select.return_value.eq.assert_called_once_with(
        "ticker", "AAPL"
    )


def test_get_company_by_ticker_not_found() -> None:
    client = _make_client([])
    assert repo.get_company_by_ticker("ZZZZ", client=client) is None


# ── insert_pipeline_run ───────────────────────────────────────────────────────


def test_insert_pipeline_run_returns_row() -> None:
    row = {"id": "run-1", "status": "running", "run_type": "daily"}
    client = _make_client([row])

    result = repo.insert_pipeline_run(client=client)

    assert result == row
    client.table.assert_called_once_with("pipeline_runs")


def test_insert_pipeline_run_default_status_running() -> None:
    client = _make_client([{"id": "run-1", "status": "running"}])
    repo.insert_pipeline_run(client=client)

    inserted_payload = client.table.return_value.insert.call_args[0][0]
    assert inserted_payload["status"] == "running"
    assert inserted_payload["run_type"] == "daily"


def test_insert_pipeline_run_includes_optional_fields() -> None:
    client = _make_client([{"id": "run-2"}])
    repo.insert_pipeline_run(
        run_type="backfill",
        git_sha="abc123",
        model_version="v2",
        client=client,
    )

    inserted_payload = client.table.return_value.insert.call_args[0][0]
    assert inserted_payload["run_type"] == "backfill"
    assert inserted_payload["git_sha"] == "abc123"
    assert inserted_payload["model_version"] == "v2"


def test_insert_pipeline_run_omits_none_optional_fields() -> None:
    client = _make_client([{"id": "run-3"}])
    repo.insert_pipeline_run(client=client)

    inserted_payload = client.table.return_value.insert.call_args[0][0]
    assert "git_sha" not in inserted_payload
    assert "model_version" not in inserted_payload


# ── finish_pipeline_run ───────────────────────────────────────────────────────


def test_finish_pipeline_run_returns_row() -> None:
    row = {"id": "run-1", "status": "success"}
    client = _make_client([row])

    result = repo.finish_pipeline_run("run-1", status="success", client=client)

    assert result == row


def test_finish_pipeline_run_updates_correct_id() -> None:
    client = _make_client([{"id": "run-1"}])
    repo.finish_pipeline_run("run-1", status="failed", client=client)

    client.table.return_value.update.return_value.eq.assert_called_once_with(
        "id", "run-1"
    )


def test_finish_pipeline_run_includes_optional_fields() -> None:
    client = _make_client([{"id": "run-1"}])
    repo.finish_pipeline_run(
        "run-1",
        status="success",
        message="All done.",
        metrics={"companies": 5},
        client=client,
    )

    updated_payload = client.table.return_value.update.call_args[0][0]
    assert updated_payload["message"] == "All done."
    assert updated_payload["metrics"] == {"companies": 5}


def test_finish_pipeline_run_omits_none_optional_fields() -> None:
    client = _make_client([{"id": "run-1"}])
    repo.finish_pipeline_run("run-1", status="success", client=client)

    updated_payload = client.table.return_value.update.call_args[0][0]
    assert "message" not in updated_payload
    assert "metrics" not in updated_payload


# ── log_pipeline_event ────────────────────────────────────────────────────────


def test_log_pipeline_event_returns_row() -> None:
    row = {"id": "evt-1", "stage": "fetch", "level": "info"}
    client = _make_client([row])

    result = repo.log_pipeline_event(
        "run-1", stage="fetch", message="Started", client=client
    )

    assert result == row
    client.table.assert_called_once_with("pipeline_run_events")


def test_log_pipeline_event_default_level_info() -> None:
    client = _make_client([{"id": "evt-1"}])
    repo.log_pipeline_event("run-1", stage="fetch", message="ok", client=client)

    inserted_payload = client.table.return_value.insert.call_args[0][0]
    assert inserted_payload["level"] == "info"
    assert inserted_payload["details"] == {}


def test_log_pipeline_event_includes_company_id() -> None:
    client = _make_client([{"id": "evt-2"}])
    repo.log_pipeline_event(
        "run-1",
        stage="price",
        message="Fetched",
        company_id="comp-abc",
        client=client,
    )

    inserted_payload = client.table.return_value.insert.call_args[0][0]
    assert inserted_payload["company_id"] == "comp-abc"


def test_log_pipeline_event_omits_none_company_id() -> None:
    client = _make_client([{"id": "evt-3"}])
    repo.log_pipeline_event("run-1", stage="fetch", message="ok", client=client)

    inserted_payload = client.table.return_value.insert.call_args[0][0]
    assert "company_id" not in inserted_payload


def test_log_pipeline_event_custom_details() -> None:
    client = _make_client([{"id": "evt-4"}])
    repo.log_pipeline_event(
        "run-1",
        stage="parse",
        message="error",
        level="error",
        details={"line": 42, "reason": "invalid JSON"},
        client=client,
    )

    inserted_payload = client.table.return_value.insert.call_args[0][0]
    assert inserted_payload["level"] == "error"
    assert inserted_payload["details"] == {"line": 42, "reason": "invalid JSON"}


# ── Phase 3: read helpers ─────────────────────────────────────────────────────


def _make_read_client(data: list[dict[str, Any]]) -> MagicMock:
    """Mock client for Phase 3 chained reads.

    Supports both paths:
    - without date filter: .table().select().eq().order().limit().execute()
    - with date filter:    .table().select().eq().lte().order().limit().execute()
    Also supports the UPSERT path: .table().upsert().execute()
    """
    response = MagicMock()
    response.data = data

    mock = MagicMock()
    eq_mock = mock.table.return_value.select.return_value.eq.return_value
    # Path without date ceiling (.order.limit.execute)
    eq_mock.order.return_value.limit.return_value.execute.return_value = response
    # Path with date ceiling (.lte.order.limit.execute)
    eq_mock.lte.return_value.order.return_value.limit.return_value.execute.return_value = response
    # UPSERT chain
    mock.table.return_value.upsert.return_value.execute.return_value = response
    return mock


# ── get_statements_for_company ────────────────────────────────────────────────


def test_get_statements_for_company_returns_data() -> None:
    rows = [{"id": "s1", "fiscal_year": 2023}]
    client = _make_read_client(rows)
    result = repo.get_statements_for_company("company-1", client=client)
    assert result == rows
    client.table.assert_called_once_with("statements_norm")


def test_get_statements_for_company_no_date_filter_skips_lte() -> None:
    client = _make_read_client([])
    repo.get_statements_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_not_called()


def test_get_statements_for_company_with_as_of_date_applies_lte() -> None:
    client = _make_read_client([])
    repo.get_statements_for_company("company-1", as_of_date="2023-12-31", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_called_once_with("period_end_date", "2023-12-31")


def test_get_statements_for_company_orders_by_period_end_date_desc() -> None:
    client = _make_read_client([])
    repo.get_statements_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.order.assert_called_once_with("period_end_date", desc=True)


# ── get_prices_for_company ────────────────────────────────────────────────────


def test_get_prices_for_company_returns_data() -> None:
    rows = [{"id": "p1", "price_date": "2024-01-02", "close": 100.0}]
    client = _make_read_client(rows)
    result = repo.get_prices_for_company("company-1", client=client)
    assert result == rows
    client.table.assert_called_once_with("price_eod")


def test_get_prices_for_company_no_date_filter_skips_lte() -> None:
    client = _make_read_client([])
    repo.get_prices_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_not_called()


def test_get_prices_for_company_with_as_of_date_applies_lte() -> None:
    client = _make_read_client([])
    repo.get_prices_for_company("company-1", as_of_date="2023-06-30", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_called_once_with("price_date", "2023-06-30")


def test_get_prices_for_company_orders_by_price_date_desc() -> None:
    client = _make_read_client([])
    repo.get_prices_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.order.assert_called_once_with("price_date", desc=True)


# ── get_news_for_company ──────────────────────────────────────────────────────


def test_get_news_for_company_returns_data() -> None:
    rows = [{"id": "n1", "published_at": "2024-01-28T12:00:00Z"}]
    client = _make_read_client(rows)
    result = repo.get_news_for_company("company-1", client=client)
    assert result == rows
    client.table.assert_called_once_with("news_events")


def test_get_news_for_company_no_date_filter_skips_lte() -> None:
    client = _make_read_client([])
    repo.get_news_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_not_called()


def test_get_news_for_company_with_as_of_date_applies_lte() -> None:
    client = _make_read_client([])
    repo.get_news_for_company("company-1", as_of_date="2024-01-31", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_called_once_with("published_at", "2024-01-31")


def test_get_news_for_company_orders_by_published_at_desc() -> None:
    client = _make_read_client([])
    repo.get_news_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.order.assert_called_once_with("published_at", desc=True)


# ── get_filings_for_company ───────────────────────────────────────────────────


def test_get_filings_for_company_returns_data() -> None:
    rows = [{"id": "f1", "filing_date": "2024-01-15"}]
    client = _make_read_client(rows)
    result = repo.get_filings_for_company("company-1", client=client)
    assert result == rows
    client.table.assert_called_once_with("filings_index")


def test_get_filings_for_company_no_date_filter_skips_lte() -> None:
    client = _make_read_client([])
    repo.get_filings_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_not_called()


def test_get_filings_for_company_with_as_of_date_applies_lte() -> None:
    client = _make_read_client([])
    repo.get_filings_for_company("company-1", as_of_date="2024-01-31", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.lte.assert_called_once_with("filing_date", "2024-01-31")


def test_get_filings_for_company_orders_by_filing_date_desc() -> None:
    client = _make_read_client([])
    repo.get_filings_for_company("company-1", client=client)
    eq_mock = client.table.return_value.select.return_value.eq.return_value
    eq_mock.order.assert_called_once_with("filing_date", desc=True)


# ── upsert_ratios_factors ─────────────────────────────────────────────────────


def test_upsert_ratios_factors_returns_row_count() -> None:
    rows = [
        {"company_id": "c1", "factor_date": "2024-01-02", "gross_margin": 0.6},
        {"company_id": "c2", "factor_date": "2024-01-02", "gross_margin": 0.4},
    ]
    client = _make_read_client(rows)
    result = repo.upsert_ratios_factors(rows, client=client)
    assert result == 2


def test_upsert_ratios_factors_empty_list_returns_zero() -> None:
    client = _make_read_client([])
    result = repo.upsert_ratios_factors([], client=client)
    assert result == 0
    client.table.assert_not_called()


def test_upsert_ratios_factors_uses_correct_conflict_columns() -> None:
    rows = [{"company_id": "c1", "factor_date": "2024-01-02"}]
    client = _make_read_client(rows)
    repo.upsert_ratios_factors(rows, client=client)
    client.table.return_value.upsert.assert_called_once_with(
        rows, on_conflict="company_id,factor_date"
    )


# ── upsert_company_analysis_readiness ─────────────────────────────────────────


def test_upsert_company_analysis_readiness_returns_count() -> None:
    rows = [
        {
            "company_id": "c1",
            "readiness_status": "analysis_ready",
            "can_run_valuation": True,
            "can_run_signal": True,
            "readiness_reason_codes": [],
            "readiness_updated_at": "2024-01-02T00:00:00+00:00",
        }
    ]
    client = _make_read_client(rows)
    result = repo.upsert_company_analysis_readiness(rows, client=client)
    assert result == 1


def test_upsert_company_analysis_readiness_returns_zero_for_empty_rows() -> None:
    client = _make_read_client([])
    result = repo.upsert_company_analysis_readiness([], client=client)
    assert result == 0
    client.table.assert_not_called()


def test_upsert_company_analysis_readiness_uses_company_id_conflict_key() -> None:
    rows = [{"company_id": "c1", "readiness_status": "tracking_only",
             "can_run_valuation": False, "can_run_signal": False,
             "readiness_reason_codes": [], "readiness_updated_at": "2024-01-02T00:00:00+00:00"}]
    client = _make_read_client(rows)
    repo.upsert_company_analysis_readiness(rows, client=client)
    client.table.return_value.upsert.assert_called_once_with(rows, on_conflict="company_id")


def test_upsert_company_analysis_readiness_writes_expected_payload() -> None:
    row = {
        "company_id": "abc-123",
        "readiness_status": "partial_analysis",
        "provider_mix": "fmp_only",
        "readiness_reason_codes": ["missing_fundamentals"],
        "can_run_valuation": False,
        "can_run_signal": True,
        "limiting_domain": "fundamentals",
        "readiness_updated_at": "2024-06-01T12:00:00+00:00",
    }
    client = _make_read_client([row])
    repo.upsert_company_analysis_readiness([row], client=client)
    client.table.assert_called_once_with("company_analysis_readiness")
    client.table.return_value.upsert.assert_called_once_with([row], on_conflict="company_id")


def test_upsert_company_data_quality_snapshots_returns_count() -> None:
    rows = [
        {
            "company_id": "c1",
            "snapshot_date": "2024-01-02",
            "price_validation_status": "warning",
            "warning_codes": ["price_divergence_warning"],
            "details": {"price_validation": {"comparison_date": "2024-01-02"}},
        }
    ]
    client = _make_read_client(rows)
    result = repo.upsert_company_data_quality_snapshots(rows, client=client)
    assert result == 1


def test_upsert_company_data_quality_snapshots_returns_zero_for_empty_rows() -> None:
    client = _make_read_client([])
    result = repo.upsert_company_data_quality_snapshots([], client=client)
    assert result == 0
    client.table.assert_not_called()


def test_upsert_company_data_quality_snapshots_uses_company_date_conflict_key() -> None:
    rows = [
        {
            "company_id": "c1",
            "snapshot_date": "2024-01-02",
            "price_validation_status": "ok",
            "warning_codes": [],
            "details": {"price_validation": {"comparison_date": "2024-01-02"}},
        }
    ]
    client = _make_read_client(rows)
    repo.upsert_company_data_quality_snapshots(rows, client=client)
    client.table.assert_called_once_with("company_data_quality_snapshots")
    client.table.return_value.upsert.assert_called_once_with(
        rows, on_conflict="company_id,snapshot_date"
    )
