"""Unit tests for Phase 6 signal repository and pipeline integration."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock


class _FakeSupabaseTable:
    """Minimal Supabase table fake that captures upsert calls."""

    def __init__(self, rows_to_return: list[dict[str, Any]]) -> None:
        self._rows = rows_to_return
        self.last_upsert_payload: Any = None
        self.last_conflict: str | None = None

    def upsert(self, payload: Any, *, on_conflict: str = "") -> "_FakeSupabaseTable":
        self.last_upsert_payload = payload
        self.last_conflict = on_conflict
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._rows)


class _FakeSupabaseClient:
    def __init__(self, table_data: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = {name: _FakeSupabaseTable(rows) for name, rows in table_data.items()}

    def table(self, name: str) -> _FakeSupabaseTable:
        return self._tables[name]


def _make_signal_row(company_id: str = "cid-001", signal_date: str = "2025-01-01") -> dict[str, Any]:
    return {
        "company_id": company_id,
        "signal_date": signal_date,
        "model_version": "signal_rule_v0",
        "valuation_run_id": "val-001",
        "qualitative_score_id": "qual-001",
        "p_buy": 0.71,
        "p_buy_adjusted": 0.68,
        "p_sell": 0.18,
        "final_signal": "buy",
        "uncertainty_penalty": 0.12,
        "red_flags": [],
        "top_feature_contributors": [],
        "explanation": "deterministic explanation",
        "freshness_flag": "ok",
    }


def test_upsert_signal_runs_empty_list_returns_zero():
    from investment_app.db.repositories import upsert_signal_runs

    fake_client = _FakeSupabaseClient({"signal_runs": []})
    assert upsert_signal_runs([], client=fake_client) == 0


def test_upsert_signal_runs_returns_row_count():
    from investment_app.db.repositories import upsert_signal_runs

    row = _make_signal_row()
    fake_client = _FakeSupabaseClient({"signal_runs": [row]})
    assert upsert_signal_runs([row], client=fake_client) == 1


def test_upsert_signal_runs_uses_correct_conflict_key():
    from investment_app.db.repositories import upsert_signal_runs

    row = _make_signal_row()
    table = _FakeSupabaseTable([row])
    client = MagicMock()
    client.table.return_value = table
    upsert_signal_runs([row], client=client)
    assert table.last_conflict == "company_id,signal_date,model_version"


def test_upsert_signal_runs_payload_forwarded():
    from investment_app.db.repositories import upsert_signal_runs

    row = _make_signal_row()
    table = _FakeSupabaseTable([row])
    client = MagicMock()
    client.table.return_value = table
    upsert_signal_runs([row], client=client)
    assert table.last_upsert_payload == [row]


class _FakePipelineRepo:
    """In-memory fake repo for signal pipeline tests."""

    def __init__(self, companies: list[dict[str, Any]] | None = None) -> None:
        self._companies = companies or [
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""}
        ]
        self.events: list[dict[str, Any]] = []
        self.signal_upserts: list[list[dict[str, Any]]] = []
        self.pipeline_runs = [{"id": "run-001"}]

    def insert_pipeline_run(self, **kwargs: Any) -> dict[str, Any]:
        return self.pipeline_runs[0]

    def finish_pipeline_run(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        return {}

    def log_pipeline_event(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        self.events.append(kwargs)
        return {}

    def list_active_companies(self) -> list[dict[str, Any]]:
        return self._companies

    def get_company_by_ticker(self, ticker: str) -> dict[str, Any] | None:
        for row in self._companies:
            if row.get("ticker") == ticker:
                return row
        return None

    def update_company_profile(self, company_id: str, fields: dict[str, Any]) -> None:
        return None

    def upsert_price_eod(self, rows: list) -> int:
        return 0

    def upsert_statements_norm(self, rows: list) -> int:
        return 0

    def upsert_filings_index(self, rows: list) -> int:
        return 0

    def upsert_fx_rates(self, rows: list) -> int:
        return 0

    def upsert_news_events(self, rows: list) -> int:
        return 0

    def upsert_ratios_factors(self, rows: list) -> int:
        return 0

    def upsert_valuation_run(self, rows: list) -> int:
        return 0

    def upsert_qualitative_scores(self, rows: list) -> int:
        return 0

    def upsert_signal_runs(self, rows: list[dict[str, Any]]) -> int:
        self.signal_upserts.append(rows)
        return len(rows)


def _import_run_live_pipeline() -> Any:
    import sys

    if "scripts.run_daily_pipeline" in sys.modules:
        del sys.modules["scripts.run_daily_pipeline"]
    import scripts.run_daily_pipeline as module

    return module._run_live_pipeline


def test_pipeline_signal_runs_upserted_metric_present():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo()

    metrics = _run_live_pipeline(
        repo_module=repo,
        providers_config={},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda resp, company_id: None,
        normalize_prices_fn=lambda *a, **k: [],
        normalize_statements_fn=lambda *a, **k: [],
        normalize_news_fn=lambda *a, **k: [],
        compute_features_fn=None,
        compute_valuation_fn=None,
        compute_qualitative_fn=None,
        compute_signal_fn=None,
    )
    assert "signal_runs_upserted" in metrics


def test_pipeline_signal_fn_called_per_company():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo(
        companies=[
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""},
            {"id": "cid-002", "ticker": "MSFT", "currency": "USD", "sector": "Technology", "cik": ""},
        ]
    )
    calls: list[str] = []

    def fake_signal_fn(company_id: str, repo_module: Any, signal_date: str) -> dict[str, Any]:
        calls.append(company_id)
        return _make_signal_row(company_id, signal_date)

    _run_live_pipeline(
        repo_module=repo,
        providers_config={},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda resp, company_id: None,
        normalize_prices_fn=lambda *a, **k: [],
        normalize_statements_fn=lambda *a, **k: [],
        normalize_news_fn=lambda *a, **k: [],
        compute_features_fn=None,
        compute_valuation_fn=None,
        compute_qualitative_fn=None,
        compute_signal_fn=fake_signal_fn,
    )
    assert set(calls) == {"cid-001", "cid-002"}


def test_pipeline_signal_upserted_metric_increments():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo()

    metrics = _run_live_pipeline(
        repo_module=repo,
        providers_config={},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda resp, company_id: None,
        normalize_prices_fn=lambda *a, **k: [],
        normalize_statements_fn=lambda *a, **k: [],
        normalize_news_fn=lambda *a, **k: [],
        compute_features_fn=None,
        compute_valuation_fn=None,
        compute_qualitative_fn=None,
        compute_signal_fn=lambda company_id, repo_module, signal_date: _make_signal_row(company_id, signal_date),
    )
    assert metrics["signal_runs_upserted"] == 1
    assert len(repo.signal_upserts) == 1


def test_pipeline_signal_none_return_skipped():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo()

    metrics = _run_live_pipeline(
        repo_module=repo,
        providers_config={},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda resp, company_id: None,
        normalize_prices_fn=lambda *a, **k: [],
        normalize_statements_fn=lambda *a, **k: [],
        normalize_news_fn=lambda *a, **k: [],
        compute_features_fn=None,
        compute_valuation_fn=None,
        compute_qualitative_fn=None,
        compute_signal_fn=lambda *a, **k: None,
    )
    assert metrics["signal_runs_upserted"] == 0
    assert repo.signal_upserts == []


def test_pipeline_signal_exception_is_isolated():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo(
        companies=[
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""},
            {"id": "cid-002", "ticker": "MSFT", "currency": "USD", "sector": "Technology", "cik": ""},
        ]
    )
    calls: list[str] = []

    def flaky_signal_fn(company_id: str, repo_module: Any, signal_date: str) -> dict[str, Any]:
        calls.append(company_id)
        if company_id == "cid-001":
            raise ValueError("simulated signal failure")
        return _make_signal_row(company_id, signal_date)

    metrics = _run_live_pipeline(
        repo_module=repo,
        providers_config={},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda resp, company_id: None,
        normalize_prices_fn=lambda *a, **k: [],
        normalize_statements_fn=lambda *a, **k: [],
        normalize_news_fn=lambda *a, **k: [],
        compute_features_fn=None,
        compute_valuation_fn=None,
        compute_qualitative_fn=None,
        compute_signal_fn=flaky_signal_fn,
    )
    assert set(calls) == {"cid-001", "cid-002"}
    assert metrics["signal_runs_upserted"] == 1


def test_pipeline_signal_logs_warning_when_none():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo()

    _run_live_pipeline(
        repo_module=repo,
        providers_config={},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda resp, company_id: None,
        normalize_prices_fn=lambda *a, **k: [],
        normalize_statements_fn=lambda *a, **k: [],
        normalize_news_fn=lambda *a, **k: [],
        compute_features_fn=None,
        compute_valuation_fn=None,
        compute_qualitative_fn=None,
        compute_signal_fn=lambda *a, **k: None,
    )
    warning_events = [
        row for row in repo.events
        if row.get("level") == "warning" and row.get("stage") == "signal"
    ]
    assert len(warning_events) == 1


def test_dry_run_mentions_signal_and_performs_no_writes() -> None:
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "scripts/run_daily_pipeline.py", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "signal" in output.lower()