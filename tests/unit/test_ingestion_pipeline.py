"""Unit tests for the ingestion pipeline (run_daily_pipeline.py)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from investment_app.connectors.base import ProviderResponse


SCRIPT = str(Path(__file__).parent.parent.parent / "scripts" / "run_daily_pipeline.py")


# ---------------------------------------------------------------------------
# Dry-run: must exit 0 with no network calls and no Supabase writes.
# ---------------------------------------------------------------------------


def test_dry_run_exits_zero(monkeypatch, tmp_path, configs_dir):
    """Dry run should complete without errors and exit 0."""
    result = subprocess.run(
        [sys.executable, SCRIPT, "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_dry_run_prints_companies(monkeypatch, configs_dir):
    """Dry run should print each watchlist ticker."""
    result = subprocess.run(
        [sys.executable, SCRIPT, "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout + result.stderr
    # At least AAPL should appear (from watchlist.example.yml)
    assert "AAPL" in output


def test_dry_run_no_network_calls(monkeypatch, configs_dir):
    """Dry run must never import or call any connector in live mode."""
    result = subprocess.run(
        [sys.executable, SCRIPT, "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # If connectors were called they would raise since no API keys are set.
    assert result.returncode == 0


def test_dry_run_does_not_call_live_pipeline():
    """Dry-run must never invoke _run_live_pipeline (mock-based, not subprocess)."""
    from typer.testing import CliRunner

    spec = importlib.util.spec_from_file_location("pipeline_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    live_pipeline_calls: list[bool] = []

    def _sentinel(**kwargs):
        live_pipeline_calls.append(True)
        return {}

    mod._run_live_pipeline = _sentinel

    runner = CliRunner()
    result = runner.invoke(mod.app, ["--dry-run"])

    assert result.exit_code == 0, f"output: {result.output}"
    assert live_pipeline_calls == [], "_run_live_pipeline must not be called in dry-run mode"


# ---------------------------------------------------------------------------
# Live mode abort on missing Supabase config
# ---------------------------------------------------------------------------


def test_live_mode_aborts_without_supabase_config(monkeypatch):
    """Live mode must exit non-zero when SUPABASE_URL is missing."""
    env = {
        "SUPABASE_URL": "",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "APP_ENV": "test",
    }
    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
        timeout=30,
        env={**__import__("os").environ, **env},
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Normalize helpers (pipeline-internal functions)
# ---------------------------------------------------------------------------


def test_extract_ecb_fx_rates_empty_payload():
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    # Import the private helper by loading the module directly.
    spec = importlib.util.spec_from_file_location("pipeline_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rows = mod._extract_ecb_fx_rates({}, "USD")
    assert rows == []


def test_extract_filings_index_filters_by_form():
    spec = importlib.util.spec_from_file_location("pipeline_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    payload = {
        "cik": "0000320193",
        "filings": {
            "recent": {
                "form": ["10-K", "8-K", "10-Q"],
                "accessionNumber": ["001", "002", "003"],
                "filingDate": ["2023-10-30", "2023-11-01", "2024-01-30"],
                "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
            }
        }
    }
    rows = mod._extract_filings_index(payload, "company-1", "AAPL")
    forms = [r["filing_type"] for r in rows]
    assert "10-K" in forms
    assert "10-Q" in forms
    assert "8-K" not in forms
    assert rows[0]["filing_date"] == "2023-10-30"
    assert rows[0]["document_url"].endswith("/doc1.htm")


def test_run_live_pipeline_creates_audit_records_and_uses_schema_fields():
    spec = importlib.util.spec_from_file_location("pipeline_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class FakeRepo:
        def __init__(self) -> None:
            self.list_active_companies_calls = 0
            self.inserted_runs: list[dict[str, str]] = []
            self.finished_runs: list[dict[str, object]] = []
            self.logged_events: list[dict[str, object]] = []
            self.filing_rows: list[dict[str, object]] = []

        def list_watchlist_active_companies(self):
            return [
                {
                    "id": "company-1",
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "currency": "USD",
                    "cik": "0000320193",
                }
            ]

        def list_active_companies(self):
            self.list_active_companies_calls += 1
            return [
                {
                    "id": "company-1",
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "currency": "USD",
                    "cik": "0000320193",
                }
            ]

        def get_company_by_ticker(self, ticker: str):
            return {"id": "company-1", "ticker": ticker}

        def insert_pipeline_run(self, **kwargs):
            self.inserted_runs.append(kwargs)
            return {"id": "run-1"}

        def finish_pipeline_run(self, run_id: str, **kwargs):
            self.finished_runs.append({"run_id": run_id, **kwargs})
            return {"id": run_id, **kwargs}

        def log_pipeline_event(self, run_id: str, **kwargs):
            self.logged_events.append({"run_id": run_id, **kwargs})
            return {"id": "evt-1", **kwargs}

        def update_company_profile(self, company_id: str, fields: dict[str, object]):
            return {"id": company_id, **fields}

        def upsert_price_eod(self, rows):
            return len(rows)

        def upsert_statements_norm(self, rows):
            return len(rows)

        def upsert_filings_index(self, rows):
            self.filing_rows.extend(rows)
            return len(rows)

        def upsert_fx_rates(self, rows):
            return len(rows)

        def upsert_news_events(self, rows):
            return len(rows)

    class FakeFMP:
        def get_profile(self, ticker: str):
            return ProviderResponse(
                provider="fmp",
                endpoint=f"profile/{ticker}",
                params={},
                status_code=200,
                success=True,
                payload=[
                    {
                        "companyName": "Apple Inc.",
                        "exchangeShortName": "NASDAQ",
                        "country": "US",
                        "currency": "USD",
                        "sector": "Technology",
                        "industry": "Consumer Electronics",
                        "cik": "0000320193",
                    }
                ],
                payload_text="profile",
            )

        def get_historical_prices(self, ticker: str):
            return ProviderResponse(
                provider="fmp",
                endpoint=f"historical-price-full/{ticker}",
                params={},
                status_code=200,
                success=True,
                payload={"historical": [{"date": "2024-01-02", "close": 1.5}]},
                payload_text="prices",
            )

        def get_income_statement(self, ticker: str, **kwargs):
            return ProviderResponse(
                provider="fmp",
                endpoint=f"income-statement/{ticker}",
                params=kwargs,
                status_code=200,
                success=True,
                payload=[{"calendarYear": "2023", "period": "FY", "date": "2023-09-30"}],
                payload_text="income",
            )

        def get_balance_sheet(self, ticker: str, **kwargs):
            return ProviderResponse(
                provider="fmp",
                endpoint=f"balance-sheet-statement/{ticker}",
                params=kwargs,
                status_code=200,
                success=True,
                payload=[{"calendarYear": "2023", "period": "FY", "date": "2023-09-30"}],
                payload_text="balance",
            )

        def get_cash_flow(self, ticker: str, **kwargs):
            return ProviderResponse(
                provider="fmp",
                endpoint=f"cash-flow-statement/{ticker}",
                params=kwargs,
                status_code=200,
                success=True,
                payload=[{"calendarYear": "2023", "period": "FY", "date": "2023-09-30"}],
                payload_text="cashflow",
            )

    class FakeSEC:
        def get_submissions(self, cik: str):
            return ProviderResponse(
                provider="sec_edgar",
                endpoint=f"submissions/{cik}",
                params={},
                status_code=200,
                success=True,
                payload={
                    "cik": cik,
                    "filings": {
                        "recent": {
                            "form": ["10-K"],
                            "accessionNumber": ["0000320193-24-000001"],
                            "filingDate": ["2024-01-30"],
                            "primaryDocument": ["a10-k.htm"],
                        }
                    },
                },
                payload_text="submissions",
            )

        def get_company_facts(self, cik: str):
            return ProviderResponse(
                provider="sec_edgar",
                endpoint=f"companyfacts/{cik}",
                params={},
                status_code=200,
                success=True,
                payload={"facts": {}},
                payload_text="facts",
            )

    class FakeECB:
        def get_fx_rate(self, currency: str, last_n: int = 5):
            return ProviderResponse(
                provider="ecb",
                endpoint=f"fx/{currency}",
                params={"last_n": last_n},
                status_code=200,
                success=True,
                payload={
                    "dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [1.09]}}}}],
                    "structure": {
                        "dimensions": {"observation": [{}, {"values": [{"id": "2024-01-02"}]}]}
                    },
                },
                payload_text="fx",
            )

    def fake_store_raw_response(response, company_id, **kwargs):
        return f"raw-{response.provider}"

    repo = FakeRepo()
    metrics = mod._run_live_pipeline(
        repo_module=repo,
        providers_config={
            "providers": {
                "gdelt": {"enabled": False},
                "ecb": {"enabled": True},
            }
        },
        fmp=FakeFMP(),
        sec=FakeSEC(),
        ecb=FakeECB(),
        gdelt=None,
        store_raw_response_fn=fake_store_raw_response,
        normalize_prices_fn=lambda *args, **kwargs: [{"company_id": "company-1"}],
        normalize_statements_fn=lambda *args, **kwargs: [{"company_id": "company-1"}],
        normalize_news_fn=lambda *args, **kwargs: [],
    )

    # Phase 9A: list_watchlist_active_companies is the sole authority;
    # list_active_companies must no longer be called by the pipeline.
    assert repo.list_active_companies_calls == 0
    assert repo.inserted_runs == [{"run_type": "daily"}]
    assert repo.finished_runs[0]["run_id"] == "run-1"
    assert repo.finished_runs[0]["status"] == "success"
    assert metrics["companies_processed"] == 1
    assert repo.filing_rows[0]["filing_type"] == "10-K"
    assert repo.filing_rows[0]["filing_date"] == "2024-01-30"
    assert repo.filing_rows[0]["document_url"].endswith("/a10-k.htm")
    assert repo.filing_rows[0]["raw_payload_id"] == "raw-sec_edgar"
    assert len(repo.logged_events) > 0, "expected at least one pipeline_run_events row to be emitted"
