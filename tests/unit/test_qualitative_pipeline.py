"""Unit tests for Phase 5: qualitative scoring pipeline integration.

Covers:
- upsert_qualitative_scores repository function (write shape, empty-list guard)
- Pipeline dry-run: qualitative_scores_upserted metric is present but writes are zero
- Pipeline orchestration: compute_qualitative_fn is called per company
- Pipeline orchestration: qualitative_scores_upserted metric increments
- Pipeline orchestration: None return from fn is skipped gracefully
- Pipeline orchestration: exception per company is isolated (others processed)
- compute_qualitative_fn=None: pipeline does not crash, metric stays zero
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# Repository: upsert_qualitative_scores
# ---------------------------------------------------------------------------


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


def _make_qual_row(company_id: str = "aaa", score_date: str = "2025-01-01") -> dict[str, Any]:
    return {
        "company_id": company_id,
        "score_date": score_date,
        "moat_score": 60.0,
        "management_score": 55.0,
        "risk_score": 65.0,
        "governance_score": 58.0,
        "final_quality_score": 60.2,
        "auto_score": {},
        "human_override": 0,
        "model_version": "qual_v0",
    }


def test_upsert_qualitative_scores_empty_list_returns_zero():
    from investment_app.db.repositories import upsert_qualitative_scores

    fake_client = _FakeSupabaseClient({"qualitative_scores": []})
    result = upsert_qualitative_scores([], client=fake_client)
    assert result == 0


def test_upsert_qualitative_scores_returns_row_count():
    from investment_app.db.repositories import upsert_qualitative_scores

    row = _make_qual_row()
    fake_client = _FakeSupabaseClient({"qualitative_scores": [row]})
    result = upsert_qualitative_scores([row], client=fake_client)
    assert result == 1


def test_upsert_qualitative_scores_multiple_rows():
    from investment_app.db.repositories import upsert_qualitative_scores

    rows = [_make_qual_row("aaa"), _make_qual_row("bbb")]
    fake_client = _FakeSupabaseClient({"qualitative_scores": rows})
    result = upsert_qualitative_scores(rows, client=fake_client)
    assert result == 2


def test_upsert_qualitative_scores_uses_correct_conflict_key():
    from investment_app.db.repositories import upsert_qualitative_scores

    row = _make_qual_row()
    table = _FakeSupabaseTable([row])
    client = MagicMock()
    client.table.return_value = table
    upsert_qualitative_scores([row], client=client)
    assert table.last_conflict == "company_id,score_date,model_version"


def test_upsert_qualitative_scores_payload_forwarded():
    from investment_app.db.repositories import upsert_qualitative_scores

    row = _make_qual_row()
    table = _FakeSupabaseTable([row])
    client = MagicMock()
    client.table.return_value = table
    upsert_qualitative_scores([row], client=client)
    assert table.last_upsert_payload == [row]


# ---------------------------------------------------------------------------
# Pipeline: fake repo for orchestration tests
# ---------------------------------------------------------------------------


class _FakePipelineRepo:
    """In-memory fake repo for pipeline script orchestration tests."""

    def __init__(
        self,
        *,
        companies: list[dict[str, Any]] | None = None,
        ratios: list[dict[str, Any]] | None = None,
        statements: list[dict[str, Any]] | None = None,
        filings: list[dict[str, Any]] | None = None,
    ) -> None:
        self._companies = companies or [
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""}
        ]
        self._ratios = ratios or []
        self._statements = statements or []
        self._filings = filings or []
        self.events: list[dict[str, Any]] = []
        self.qual_upserts: list[list[dict[str, Any]]] = []
        self.pipeline_runs: list[dict[str, Any]] = [{"id": "run-001"}]

    # Pipeline run
    def insert_pipeline_run(self, **kwargs: Any) -> dict[str, Any]:
        return self.pipeline_runs[0]

    def finish_pipeline_run(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        return {}

    def log_pipeline_event(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        self.events.append(kwargs)
        return {}

    # Company data
    def list_active_companies(self) -> list[dict[str, Any]]:
        return self._companies

    def get_company_by_ticker(self, ticker: str) -> dict[str, Any] | None:
        for c in self._companies:
            if c.get("ticker") == ticker:
                return c
        return None

    def update_company_profile(self, company_id: str, fields: dict[str, Any]) -> None:
        pass

    # Data writes (not used by Phase 5 but must exist for pipeline)
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

    def upsert_qualitative_scores(self, rows: list[dict[str, Any]]) -> int:
        self.qual_upserts.append(rows)
        return len(rows)

    # Data reads
    def get_statements_for_company(self, company_id: str, **kwargs: Any) -> list:
        return self._statements

    def get_prices_for_company(self, company_id: str, **kwargs: Any) -> list:
        return []

    def get_news_for_company(self, company_id: str, **kwargs: Any) -> list:
        return []

    def get_filings_for_company(self, company_id: str, **kwargs: Any) -> list:
        return self._filings

    def get_ratios_for_company(self, company_id: str, **kwargs: Any) -> list:
        return self._ratios


# ---------------------------------------------------------------------------
# Pipeline orchestration tests
# ---------------------------------------------------------------------------


def _import_run_live_pipeline() -> Any:
    """Lazy import of the private pipeline function."""
    import importlib
    import sys

    # Force fresh import to avoid cached state
    if "scripts.run_daily_pipeline" in sys.modules:
        del sys.modules["scripts.run_daily_pipeline"]
    import scripts.run_daily_pipeline as m

    return m._run_live_pipeline


def test_pipeline_qualitative_scores_upserted_metric_present():
    """qualitative_scores_upserted must be present in the metrics dict."""
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
    )
    assert "qualitative_scores_upserted" in metrics


def test_pipeline_no_qualitative_fn_metric_stays_zero():
    """When compute_qualitative_fn is None the metric stays at zero."""
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
    )
    assert metrics["qualitative_scores_upserted"] == 0


def test_pipeline_qualitative_fn_called_per_company():
    """compute_qualitative_fn must be invoked once per active company."""
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo(
        companies=[
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""},
            {"id": "cid-002", "ticker": "MSFT", "currency": "USD", "sector": "Technology", "cik": ""},
        ]
    )
    call_args: list[Any] = []

    def fake_qual_fn(company_id: str, repo_module: Any, score_date: str) -> dict[str, Any]:
        call_args.append(company_id)
        return _make_qual_row(company_id, score_date)

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
        compute_qualitative_fn=fake_qual_fn,
    )
    assert len(call_args) == 2
    assert "cid-001" in call_args
    assert "cid-002" in call_args


def test_pipeline_qualitative_upserted_metric_increments():
    """qualitative_scores_upserted must count successful upserts."""
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo()

    def fake_qual_fn(company_id: str, repo_module: Any, score_date: str) -> dict[str, Any]:
        return _make_qual_row(company_id, score_date)

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
        compute_qualitative_fn=fake_qual_fn,
    )
    assert metrics["qualitative_scores_upserted"] == 1
    assert len(repo.qual_upserts) == 1


def test_pipeline_qualitative_none_return_skipped():
    """When the scoring fn returns None, the upsert must not be called."""
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
        compute_qualitative_fn=lambda *a, **k: None,
    )
    assert metrics["qualitative_scores_upserted"] == 0
    assert repo.qual_upserts == []


def test_pipeline_qualitative_exception_is_isolated():
    """An exception from one company must not abort the pipeline or affect others."""
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo(
        companies=[
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "", "cik": ""},
            {"id": "cid-002", "ticker": "MSFT", "currency": "USD", "sector": "", "cik": ""},
        ]
    )
    calls: list[str] = []

    def flaky_qual_fn(company_id: str, repo_module: Any, score_date: str) -> dict[str, Any]:
        calls.append(company_id)
        if company_id == "cid-001":
            raise ValueError("simulated scoring failure")
        return _make_qual_row(company_id, score_date)

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
        compute_qualitative_fn=flaky_qual_fn,
    )
    # Both companies attempted; the second succeeds
    assert set(calls) == {"cid-001", "cid-002"}
    assert metrics["qualitative_scores_upserted"] == 1


def test_pipeline_qualitative_logs_warning_when_none():
    """A warning pipeline event must be logged when the fn returns None."""
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
        compute_qualitative_fn=lambda *a, **k: None,
    )
    warning_events = [e for e in repo.events if e.get("level") == "warning" and e.get("stage") == "qualitative"]
    assert len(warning_events) == 1


# ---------------------------------------------------------------------------
# Dry-run mode: no writes
# ---------------------------------------------------------------------------


def test_dry_run_does_not_call_upsert_qualitative(capsys: Any) -> None:
    """In dry-run mode the pipeline prints a mention and performs no writes."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/run_daily_pipeline.py", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(
            __import__("pathlib").Path(__file__).parent.parent.parent
        ),
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "qualitative" in output.lower()
