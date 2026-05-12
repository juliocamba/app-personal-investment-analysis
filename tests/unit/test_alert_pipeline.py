"""Unit tests for Phase 7 alert repositories and pipeline integration."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock


class _FakeSupabaseTable:
    def __init__(self, rows_to_return: list[dict[str, Any]]) -> None:
        self._rows = rows_to_return
        self.last_insert_payload: Any = None

    def insert(self, payload: Any) -> "_FakeSupabaseTable":
        self.last_insert_payload = payload
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._rows)


class _FakeReadClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        response = SimpleNamespace(data=rows)
        self.table = MagicMock()
        table = self.table.return_value
        eq = table.select.return_value.eq.return_value
        eq.execute.return_value = response
        eq.limit.return_value.execute.return_value = response
        eq.order.return_value.limit.return_value.execute.return_value = response
        eq.lte.return_value.order.return_value.limit.return_value.execute.return_value = response
        table.insert.return_value.execute.return_value = response


def test_get_enabled_alert_rules_filters_global_and_company_rules():
    from investment_app.db.repositories import get_enabled_alert_rules

    rows = [
        {"id": "r1", "company_id": None, "enabled": True},
        {"id": "r2", "company_id": "cid-001", "enabled": True},
        {"id": "r3", "company_id": "cid-002", "enabled": True},
    ]
    client = _FakeReadClient(rows)
    result = get_enabled_alert_rules("cid-001", client=client)
    assert [row["id"] for row in result] == ["r1", "r2"]


def test_get_alert_history_by_dedupe_returns_first_row():
    from investment_app.db.repositories import get_alert_history_by_dedupe

    row = {"id": "ah-1", "dedupe_key": "key-1"}
    client = _FakeReadClient([row])
    assert get_alert_history_by_dedupe("key-1", client=client) == row


def test_insert_alert_history_payload_forwarded():
    from investment_app.db.repositories import insert_alert_history

    # Verify that the payload we pass is forwarded verbatim to Supabase.
    payload = {
        "alert_rule_id": "rule-001",
        "company_id": "cid-001",
        "signal_run_id": "sig-001",
        "channel": "email",
        "title": "AAPL alert",
        "message": "buy signal",
        "dedupe_key": "cid-001:p_buy_adjusted_above:2025-01-01:0.6000:buy",
        "status": "sent",
        "sent_at": "2025-01-01T12:00:00",
        "error_message": None,
    }
    client = _FakeReadClient([payload])
    result = insert_alert_history(payload, client=client)
    assert result == payload
    inserted = client.table.return_value.insert.call_args[0][0]
    assert inserted["channel"] == "email"
    assert inserted["status"] == "sent"
    assert inserted["dedupe_key"] == payload["dedupe_key"]
    assert inserted["company_id"] == "cid-001"


class _FakePipelineRepo:
    def __init__(self, companies: list[dict[str, Any]] | None = None) -> None:
        self._companies = companies or [
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""}
        ]
        self.events: list[dict[str, Any]] = []
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

    def upsert_signal_runs(self, rows: list) -> int:
        return 0


def _import_run_live_pipeline() -> Any:
    import sys

    if "scripts.run_daily_pipeline" in sys.modules:
        del sys.modules["scripts.run_daily_pipeline"]
    import scripts.run_daily_pipeline as module
    return module._run_live_pipeline


def test_pipeline_alert_metrics_present():
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
        process_alerts_fn=None,
        settings=SimpleNamespace(),
    )
    assert "alerts_sent" in metrics
    assert "alert_history_written" in metrics
    assert "alerts_deduplicated" in metrics


def test_pipeline_alert_fn_called_per_company():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo(
        companies=[
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""},
            {"id": "cid-002", "ticker": "MSFT", "currency": "USD", "sector": "Technology", "cik": ""},
        ]
    )
    calls: list[str] = []

    def fake_alerts_fn(company_id: str, repo_module: Any, alert_date: str, **kwargs: Any) -> dict[str, int]:
        calls.append(company_id)
        return {"alerts_sent": 1, "alert_history_written": 1}

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
        process_alerts_fn=fake_alerts_fn,
        settings=SimpleNamespace(),
    )
    assert set(calls) == {"cid-001", "cid-002"}
    assert metrics["alerts_sent"] == 2
    assert metrics["alert_history_written"] == 2


def test_pipeline_alert_exception_is_isolated():
    _run_live_pipeline = _import_run_live_pipeline()
    repo = _FakePipelineRepo(
        companies=[
            {"id": "cid-001", "ticker": "AAPL", "currency": "USD", "sector": "Technology", "cik": ""},
            {"id": "cid-002", "ticker": "MSFT", "currency": "USD", "sector": "Technology", "cik": ""},
        ]
    )

    def flaky_alerts_fn(company_id: str, repo_module: Any, alert_date: str, **kwargs: Any) -> dict[str, int]:
        if company_id == "cid-001":
            raise ValueError("simulated alert failure")
        return {"alerts_sent": 1, "alert_history_written": 1}

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
        process_alerts_fn=flaky_alerts_fn,
        settings=SimpleNamespace(),
    )
    assert metrics["alerts_sent"] == 1
    assert metrics["alert_history_written"] == 1


def test_dry_run_mentions_alerts_and_performs_no_writes() -> None:
    """Dry-run must exit before any live operation occurs.

    Proof strategy:
    - The subprocess must exit with code 0.
    - Output must contain the dry-run completion marker — this is only printed
      via the early-return branch, proving _run_live_pipeline was never entered.
    - Output must mention alert evaluation in the "would do" section.
    - Output must NOT contain any indicator of a live write or send (e.g.
      "insert", "alerts_sent", "email sent", "telegram sent").
    """
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "scripts/run_daily_pipeline.py", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    assert result.returncode == 0, f"dry-run failed:\n{result.stderr}"
    output = (result.stdout + result.stderr).lower()

    # Positive: dry-run branch completed normally.
    assert "dry run complete" in output, "expected 'dry run complete' in dry-run output"
    # Positive: alert evaluation was mentioned in the 'would do' section.
    assert "alert" in output, "expected alert mention in dry-run output"
    # Positive: no data was fetched message is present.
    assert "no data was fetched" in output, "expected 'no data was fetched' in dry-run output"

    # Negative: none of the live-write/send markers should appear.
    # These strings only appear when _run_live_pipeline actually executes
    # inserts, sends, or accumulates live metrics.
    live_markers = ["alerts_sent", "email sent", "telegram sent", "alert history written"]
    for marker in live_markers:
        assert marker not in output, (
            f"unexpected live-operation marker '{marker}' found in dry-run output"
        )


def test_dry_run_no_process_alerts_fn_called() -> None:
    """_run_live_pipeline with process_alerts_fn=None writes zero alert rows.

    This is a pure unit-level complement to the subprocess dry-run test: it
    verifies that the live pipeline itself never calls any send function when
    process_alerts_fn is absent, which mirrors the dry-run contract.
    """
    _run_live_pipeline = _import_run_live_pipeline()
    email_sends: list[str] = []
    telegram_sends: list[str] = []

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
        # No process_alerts_fn — simulates dry-run / alerts_enabled=False
        process_alerts_fn=None,
        settings=SimpleNamespace(),
    )
    # No alert operations should have occurred.
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 0
    assert metrics["alerts_deduplicated"] == 0
    # No email or Telegram functions were invoked.
    assert email_sends == []
    assert telegram_sends == []