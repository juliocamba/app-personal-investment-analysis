"""Unit tests for Phase 10C.2 pipeline readiness integration.

Tests cover:
1. analysis_ready company emits readiness_classified, does not skip valuation/signal.
2. partial_analysis company emits readiness_classified, does not skip valuation/signal.
3. tracking_only company skips valuation with readiness_skipped_valuation event.
4. provider_limited company skips valuation/signal.
5. unsupported_for_analysis company skips both valuation and signal.
6. Classifier repo error does not crash; returns None; no gating applied.
7. No secrets / raw payloads emitted in any event.
8. Schema-valid company_type values (financial, spac, commodity) are not
   classified as unsupported_for_analysis.
"""
from __future__ import annotations

from typing import Any

import pytest

from investment_app.pipeline_readiness import (
    build_readiness_snapshot_row,
    classify_company_for_pipeline,
    should_skip_valuation,
    should_skip_signal,
)


# ---------------------------------------------------------------------------
# Minimal fake repository
# ---------------------------------------------------------------------------


class _FakeRepo:
    """In-memory repo stub — no Supabase, no network."""

    def __init__(
        self,
        *,
        price_rows: list[dict[str, Any]] | None = None,
        statement_rows: list[dict[str, Any]] | None = None,
        filing_rows: list[dict[str, Any]] | None = None,
        valuation_row: dict[str, Any] | None = None,
        signal_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._price_rows = price_rows or []
        self._statement_rows = statement_rows or []
        self._filing_rows = filing_rows or []
        self._valuation_row = valuation_row
        self._signal_rows = signal_rows or []
        self.events: list[dict[str, Any]] = []
        self.readiness_snapshots: list[dict[str, Any]] = []

    def get_prices_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 1
    ) -> list[dict[str, Any]]:
        return self._price_rows[:limit]

    def get_statements_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        return self._statement_rows[:limit]

    def get_filings_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        return self._filing_rows[:limit]

    def get_latest_valuation_run(
        self, company_id: str, *, as_of_date: str | None = None
    ) -> dict[str, Any] | None:
        return self._valuation_row

    def get_signal_runs_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 1
    ) -> list[dict[str, Any]]:
        return self._signal_rows[:limit]

    def log_pipeline_event(
        self,
        run_id: str,
        *,
        stage: str,
        level: str = "info",
        company_id: str | None = None,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append({
            "run_id": run_id,
            "stage": stage,
            "level": level,
            "company_id": company_id,
            "message": message,
            "details": details or {},
        })

    def upsert_company_analysis_readiness(
        self,
        rows: list[dict[str, Any]],
        *,
        client: Any = None,
    ) -> int:
        self.readiness_snapshots.extend(rows)
        return len(rows)

    def events_by_name(self, event_name: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["details"].get("event") == event_name]


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

_RUN_ID = "run-test-001"
_FACTOR_DATE = "2025-01-01"
_COMPANY_ID = "co-test-001"


def _company(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": _COMPANY_ID,
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "country": "US",
        "currency": "USD",
        "company_type": "non_financial",
        "metadata": {},
    }
    base.update(overrides)
    return base


def _price_row(provider: str = "fmp") -> dict[str, Any]:
    return {"provider": provider, "price_date": "2025-01-01", "close": 150.0}


def _statement_row(year: int, *, source: str = "fmp") -> dict[str, Any]:
    return {
        "fiscal_year": year,
        "fiscal_period": "annual",
        "period_end_date": f"{year}-09-30",
        "source": source,
        "diluted_shares": 1_000.0,
        "free_cash_flow": 200.0,
        "cfo": 250.0,
        "capex": -50.0,
    }


def _metrics() -> dict[str, int]:
    return {
        "readiness_classified": 0,
        "readiness_skipped_valuation": 0,
        "readiness_skipped_signal": 0,
        "readiness_errors": 0,
    }


# ---------------------------------------------------------------------------
# 1. analysis_ready — emits event, runs valuation and signal
# ---------------------------------------------------------------------------


def test_analysis_ready_emits_readiness_classified() -> None:
    repo = _FakeRepo(
        price_rows=[_price_row()],
        statement_rows=[_statement_row(2024), _statement_row(2023)],
    )
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert result is not None
    assert result["readiness_status"] == "analysis_ready"
    assert metrics["readiness_classified"] == 1
    events = repo.events_by_name("readiness_classified")
    assert len(events) == 1
    assert events[0]["details"]["readiness_status"] == "analysis_ready"


def test_analysis_ready_does_not_skip_valuation_or_signal() -> None:
    repo = _FakeRepo(
        price_rows=[_price_row()],
        statement_rows=[_statement_row(2024), _statement_row(2023)],
    )
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert not should_skip_valuation(result)
    assert not should_skip_signal(result)


# ---------------------------------------------------------------------------
# 2. partial_analysis — emits event, does not gate compute
# ---------------------------------------------------------------------------


def test_partial_analysis_emits_readiness_classified() -> None:
    # Missing price → partial_analysis (fundamentals present)
    repo = _FakeRepo(
        price_rows=[],
        statement_rows=[_statement_row(2024), _statement_row(2023)],
    )
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert result is not None
    assert result["readiness_status"] == "partial_analysis"
    assert len(repo.events_by_name("readiness_classified")) == 1


def test_partial_analysis_does_not_skip_valuation_or_signal() -> None:
    repo = _FakeRepo(
        price_rows=[],
        statement_rows=[_statement_row(2024), _statement_row(2023)],
    )
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert not should_skip_valuation(result)
    assert not should_skip_signal(result)


# ---------------------------------------------------------------------------
# 3. tracking_only — skip valuation and signal
# ---------------------------------------------------------------------------


def test_tracking_only_skips_valuation_and_signal() -> None:
    # Non-US company, no CIK, no statements → tracking_only
    repo = _FakeRepo(
        price_rows=[_price_row()],
        statement_rows=[],
    )
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(ticker="ASML", country="NL", cik=""), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert result is not None
    assert result["readiness_status"] == "tracking_only"
    assert should_skip_valuation(result)
    assert should_skip_signal(result)


# ---------------------------------------------------------------------------
# 4. provider_limited — skip valuation and signal
# ---------------------------------------------------------------------------


def test_provider_limited_skips_valuation_and_signal() -> None:
    # No price, no fundamentals, no cik, not US → provider_limited
    repo = _FakeRepo(price_rows=[], statement_rows=[])
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(country="DE", cik=""), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert result is not None
    assert result["readiness_status"] == "provider_limited"
    assert should_skip_valuation(result)
    assert should_skip_signal(result)


# ---------------------------------------------------------------------------
# 5. unsupported_for_analysis — skip both
# ---------------------------------------------------------------------------


def test_unsupported_skips_valuation_and_signal() -> None:
    repo = _FakeRepo(
        price_rows=[_price_row()],
        statement_rows=[_statement_row(2024), _statement_row(2023)],
    )
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(metadata={"instrument_type": "etf"}), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert result is not None
    assert result["readiness_status"] == "unsupported_for_analysis"
    assert should_skip_valuation(result)
    assert should_skip_signal(result)


# ---------------------------------------------------------------------------
# 6. Classifier repo error — does not crash, no gating applied
# ---------------------------------------------------------------------------


class _BrokenRepo(_FakeRepo):
    def get_prices_for_company(self, *_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        raise RuntimeError("simulated connection error")


def test_classifier_error_does_not_crash_pipeline() -> None:
    repo = _BrokenRepo()
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert result is None
    assert metrics["readiness_errors"] == 1
    # Fail-open: None means no gating
    assert not should_skip_valuation(result)
    assert not should_skip_signal(result)


def test_classifier_error_emits_safe_diagnostic_event() -> None:
    repo = _BrokenRepo()
    metrics = _metrics()
    classify_company_for_pipeline(
        _company(), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    error_events = repo.events_by_name("readiness_classification_error")
    assert len(error_events) == 1
    assert error_events[0]["details"]["error_type"] == "RuntimeError"
    # Must not leak raw exception message
    assert "simulated connection error" not in str(error_events[0]["details"])


# ---------------------------------------------------------------------------
# 7. No secrets / raw payloads in any emitted event
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = (
    "apikey",
    "api_key",
    "bearer",
    "eyj",
    "service_role",
    "supabase.co",
    "financialmodelingprep",
    "twelvedata",
)


def test_no_secrets_in_emitted_events() -> None:
    repo = _FakeRepo(
        price_rows=[_price_row()],
        statement_rows=[_statement_row(2024), _statement_row(2023)],
    )
    metrics = _metrics()
    classify_company_for_pipeline(
        _company(), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    for event in repo.events:
        combined = (str(event["details"]) + str(event["message"])).lower()
        for pattern in _SECRET_PATTERNS:
            assert pattern not in combined, (
                f"Secret pattern '{pattern}' found in pipeline event"
            )


# ---------------------------------------------------------------------------
# 8. Schema-valid company_type values (financial, spac, commodity)
#    must not be classified as unsupported_for_analysis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("company_type", ["financial", "spac", "commodity"])
def test_schema_valid_company_type_is_not_unsupported(company_type: str) -> None:
    repo = _FakeRepo(
        price_rows=[_price_row()],
        statement_rows=[_statement_row(2024), _statement_row(2023)],
    )
    metrics = _metrics()
    result = classify_company_for_pipeline(
        _company(company_type=company_type), _COMPANY_ID,
        repo_module=repo, run_id=_RUN_ID, factor_date=_FACTOR_DATE, metrics=metrics,
    )

    assert result is not None, f"Classifier returned None for company_type={company_type}"
    assert result["readiness_status"] != "unsupported_for_analysis", (
        f"company_type='{company_type}' was incorrectly classified as unsupported"
    )
    assert not should_skip_valuation(result), (
        f"company_type='{company_type}' should not gate valuation"
    )


# ---------------------------------------------------------------------------
# Phase 10C.3: build_readiness_snapshot_row
# ---------------------------------------------------------------------------


def _minimal_result(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "readiness_status": "analysis_ready",
        "provider_mix": "fmp_full",
        "reason_codes": [],
        "can_run_valuation": True,
        "can_run_signal": True,
        "limiting_domain": None,
    }
    base.update(overrides)
    return base


def test_build_readiness_snapshot_row_maps_required_fields() -> None:
    result = _minimal_result()
    row = build_readiness_snapshot_row(result, _COMPANY_ID)

    assert row["company_id"] == _COMPANY_ID
    assert row["readiness_status"] == "analysis_ready"
    assert row["provider_mix"] == "fmp_full"
    assert row["can_run_valuation"] is True
    assert row["can_run_signal"] is True
    assert row["limiting_domain"] is None
    assert row["readiness_reason_codes"] == []
    assert "readiness_updated_at" in row


def test_build_readiness_snapshot_row_maps_reason_codes_to_correct_key() -> None:
    result = _minimal_result(reason_codes=["missing_price", "stale_fundamentals"])
    row = build_readiness_snapshot_row(result, _COMPANY_ID)

    # The DB column is readiness_reason_codes, not reason_codes.
    assert "reason_codes" not in row
    assert row["readiness_reason_codes"] == ["missing_price", "stale_fundamentals"]


def test_build_readiness_snapshot_row_reason_codes_defaults_to_empty_list() -> None:
    result = _minimal_result()
    result.pop("reason_codes", None)
    row = build_readiness_snapshot_row(result, _COMPANY_ID)
    assert row["readiness_reason_codes"] == []


def test_build_readiness_snapshot_row_readiness_updated_at_is_iso_timestamp() -> None:
    from datetime import datetime, timezone

    row = build_readiness_snapshot_row(_minimal_result(), _COMPANY_ID)
    ts = row["readiness_updated_at"]
    # Must be parseable as a UTC-aware datetime.
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None


def test_build_readiness_snapshot_row_is_pure_no_side_effects() -> None:
    """Calling twice produces independent dicts; source result is not mutated."""
    result = _minimal_result()
    original_keys = set(result.keys())
    row1 = build_readiness_snapshot_row(result, _COMPANY_ID)
    row2 = build_readiness_snapshot_row(result, "other-company-id")

    assert set(result.keys()) == original_keys, "source result was mutated"
    assert row1["company_id"] == _COMPANY_ID
    assert row2["company_id"] == "other-company-id"
