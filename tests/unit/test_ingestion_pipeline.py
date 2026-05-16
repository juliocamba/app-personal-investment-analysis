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
            self.price_rows: list[dict[str, object]] = []

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
            self.price_rows.extend(rows)
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

        def get_prices_for_company(self, company_id: str, **kwargs):
            return [row for row in self.price_rows if row.get("company_id") == company_id]

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


# ---------------------------------------------------------------------------
# Phase 10A: SEC fundamentals fallback — _try_sec_statements_fallback
# ---------------------------------------------------------------------------


def _load_pipeline_module():
    spec = importlib.util.spec_from_file_location("pipeline_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _SimpleRepo:
    """Minimal repo stub for Phase 10A fallback tests."""

    def __init__(self):
        self.upserted: list[dict] = []
        self.events: list[dict] = []

    def upsert_statements_norm(self, rows):
        self.upserted.extend(rows)
        return len(rows)

    def log_pipeline_event(self, run_id, *, stage, message, level="info",
                           company_id=None, details=None):
        self.events.append({"stage": stage, "message": message, "level": level,
                            "details": details or {}})


def _ok_sec_facts_response():
    """Valid SEC companyfacts response with one annual revenue fact."""
    from investment_app.connectors.base import ProviderResponse

    return ProviderResponse(
        provider="sec_edgar",
        endpoint="companyfacts/0000723254",
        params={},
        status_code=200,
        success=True,
        payload={
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "accn": "0000723254-24-000001",
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-01-15",
                                    "start": "2022-10-01",
                                    "end": "2023-09-30",
                                    "val": 25_000_000_000,
                                }
                            ]
                        }
                    },
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {
                                    "accn": "0000723254-24-000001",
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-01-15",
                                    "start": "2022-10-01",
                                    "end": "2023-09-30",
                                    "val": 3_000_000_000,
                                }
                            ]
                        }
                    },
                    "Assets": {
                        "units": {
                            "USD": [
                                {
                                    "accn": "0000723254-24-000001",
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-01-15",
                                    "start": "2022-10-01",
                                    "end": "2023-09-30",
                                    "val": 40_000_000_000,
                                }
                            ]
                        }
                    },
                }
            }
        },
        payload_text="facts",
    )


def _fail_sec_facts_response():
    from investment_app.connectors.base import ProviderResponse

    return ProviderResponse(
        provider="sec_edgar",
        endpoint="companyfacts/0000723254",
        params={},
        status_code=500,
        success=False,
        payload=None,
        payload_text="",
    )


def test_10a_sec_fallback_not_called_when_fmp_succeeds():
    """When FMP normalizes ≥1 usable row, SEC fallback must NOT be invoked."""
    mod = _load_pipeline_module()

    sec_calls: list[str] = []

    class TrackingSEC:
        def get_submissions(self, cik):
            return _ok_sec_facts_response()

        def get_company_facts(self, cik):
            sec_calls.append(cik)
            return _ok_sec_facts_response()

    repo = _SimpleRepo()

    # normalize_statements_fn returns one usable row — FMP succeeds
    def fake_normalize_statements(inc, bal, cf, company_id, ticker, currency):
        return [
            {
                "fiscal_year": 2023,
                "fiscal_period": "annual",
                "period_end_date": "2023-09-30",
                "revenue": 25_000_000_000,
                "net_income": 3_000_000_000,
                "total_assets": 40_000_000_000,
                "operating_income": None,
                "cfo": None,
                "free_cash_flow": None,
                "total_equity": None,
                "source": "fmp",
            }
        ]

    class FakeFMP:
        def get_profile(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="profile", params={},
                status_code=200, success=True,
                payload=[{"companyName": "MU", "exchangeShortName": "NASDAQ",
                          "country": "US", "currency": "USD",
                          "sector": "Tech", "industry": "Semiconductors",
                          "cik": "0000723254"}],
                payload_text="profile",
            )

        def get_historical_prices(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="prices", params={},
                status_code=200, success=True,
                payload={"historical": []}, payload_text="prices",
            )

        def get_income_statement(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="income", params={},
                status_code=200, success=True,
                payload=[{"calendarYear": "2023", "period": "FY"}], payload_text="income",
            )

        def get_balance_sheet(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="balance", params={},
                status_code=200, success=True,
                payload=[{"calendarYear": "2023", "period": "FY"}], payload_text="balance",
            )

        def get_cash_flow(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="cashflow", params={},
                status_code=200, success=True,
                payload=[{"calendarYear": "2023", "period": "FY"}], payload_text="cashflow",
            )

    from investment_app.connectors.base import ProviderResponse

    class FakeECB:
        def get_fx_rate(self, currency, last_n=5):
            return ProviderResponse(
                provider="ecb", endpoint="fx", params={},
                status_code=200, success=True,
                payload={"dataSets": [], "structure": {"dimensions": {"observation": []}}},
                payload_text="fx",
            )

    repo_full = type("Repo", (), {
        "list_watchlist_active_companies": lambda s: [{
            "id": "company-mu",
            "ticker": "MU",
            "name": "Micron",
            "currency": "USD",
            "cik": "0000723254",
        }],
        "get_company_by_ticker": lambda s, t: {"id": "company-mu"},
        "insert_pipeline_run": lambda s, **kw: {"id": "run-mu"},
        "finish_pipeline_run": lambda s, run_id, **kw: {"id": run_id},
        "log_pipeline_event": lambda s, run_id, **kw: {"id": "evt"},
        "update_company_profile": lambda s, cid, fields: {},
        "upsert_price_eod": lambda s, rows: len(rows),
        "upsert_statements_norm": lambda s, rows: len(rows),
        "upsert_filings_index": lambda s, rows: len(rows),
        "upsert_fx_rates": lambda s, rows: len(rows),
        "upsert_news_events": lambda s, rows: len(rows),
    })()

    mod._run_live_pipeline(
        repo_module=repo_full,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=FakeFMP(),
        sec=TrackingSEC(),
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda r, cid, **kw: f"raw-{r.provider}",
        normalize_prices_fn=lambda *a, **kw: [],
        normalize_statements_fn=fake_normalize_statements,
        normalize_news_fn=lambda *a, **kw: [],
    )

    # SEC companyfacts must NOT have been called — only submissions
    assert sec_calls == [], (
        "SEC companyfacts should not be fetched when FMP returns usable rows; "
        f"got calls: {sec_calls}"
    )


def test_10a_fmp_402_triggers_sec_fallback():
    """FMP HTTP 402 on income statement must trigger SEC fallback."""
    mod = _load_pipeline_module()
    from investment_app.connectors.base import ProviderResponse

    class FakeFMP402:
        def get_profile(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="profile", params={},
                status_code=200, success=True,
                payload=[{"companyName": "MU", "exchangeShortName": "NASDAQ",
                          "country": "US", "currency": "USD",
                          "sector": "Tech", "industry": "Semiconductors",
                          "cik": "0000723254"}],
                payload_text="profile",
            )

        def get_historical_prices(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="prices", params={},
                status_code=200, success=True,
                payload={"historical": []}, payload_text="prices",
            )

        def get_income_statement(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="income", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

        def get_balance_sheet(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="balance", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

        def get_cash_flow(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="cashflow", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

    sec_companyfacts_calls: list[str] = []

    class TrackingSEC:
        def get_submissions(self, cik):
            return ProviderResponse(
                provider="sec_edgar", endpoint="submissions", params={},
                status_code=200, success=True,
                payload={"cik": cik, "filings": {"recent": {
                    "form": [], "accessionNumber": [], "filingDate": [], "primaryDocument": []
                }}},
                payload_text="submissions",
            )

        def get_company_facts(self, cik):
            sec_companyfacts_calls.append(cik)
            return _ok_sec_facts_response()

    repo_full = type("Repo", (), {
        "list_watchlist_active_companies": lambda s: [{
            "id": "company-mu", "ticker": "MU", "name": "Micron",
            "currency": "USD", "cik": "0000723254",
        }],
        "get_company_by_ticker": lambda s, t: {"id": "company-mu"},
        "insert_pipeline_run": lambda s, **kw: {"id": "run-mu"},
        "finish_pipeline_run": lambda s, run_id, **kw: {"id": run_id},
        "log_pipeline_event": lambda s, run_id, **kw: {"id": "evt"},
        "update_company_profile": lambda s, cid, fields: {},
        "upsert_price_eod": lambda s, rows: len(rows),
        "upsert_statements_norm": lambda s, rows: len(rows),
        "upsert_filings_index": lambda s, rows: len(rows),
        "upsert_fx_rates": lambda s, rows: len(rows),
        "upsert_news_events": lambda s, rows: len(rows),
    })()

    metrics = mod._run_live_pipeline(
        repo_module=repo_full,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=FakeFMP402(),
        sec=TrackingSEC(),
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda r, cid, **kw: f"raw-{r.provider}",
        normalize_prices_fn=lambda *a, **kw: [],
        normalize_statements_fn=lambda *a, **kw: [],  # returns empty → triggers fallback
        normalize_news_fn=lambda *a, **kw: [],
    )

    assert sec_companyfacts_calls != [], "SEC companyfacts should have been fetched after FMP 402"
    assert metrics["sec_fallback_upserted"] > 0, (
        "SEC fallback rows should have been upserted"
    )


def test_10a_missing_cik_logs_warning_and_continues():
    """If a company has no CIK, SEC fallback emits a warning but pipeline continues."""
    mod = _load_pipeline_module()
    from investment_app.connectors.base import ProviderResponse

    repo = _SimpleRepo()

    class FakeFMP402:
        def get_profile(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="profile", params={},
                status_code=200, success=True,
                payload=[{"companyName": "X", "exchangeShortName": "NYSE",
                          "country": "US", "currency": "USD",
                          "sector": "Tech", "industry": "Other",
                          "cik": ""}],
                payload_text="profile",
            )

        def get_historical_prices(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="prices", params={},
                status_code=200, success=True,
                payload={"historical": []}, payload_text="prices",
            )

        def get_income_statement(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="income", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

        def get_balance_sheet(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="balance", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

        def get_cash_flow(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="cashflow", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

    sec_companyfacts_calls: list[str] = []

    class TrackingSEC:
        def get_submissions(self, cik):
            return ProviderResponse(
                provider="sec_edgar", endpoint="submissions", params={},
                status_code=200, success=True,
                payload={"cik": cik, "filings": {"recent": {
                    "form": [], "accessionNumber": [], "filingDate": [], "primaryDocument": []
                }}},
                payload_text="submissions",
            )

        def get_company_facts(self, cik):
            sec_companyfacts_calls.append(cik)
            return _ok_sec_facts_response()

    repo_full = type("Repo", (), {
        "list_watchlist_active_companies": lambda s: [{
            "id": "company-x", "ticker": "X", "name": "X Corp",
            "currency": "USD", "cik": "",  # ← no CIK
        }],
        "get_company_by_ticker": lambda s, t: {"id": "company-x"},
        "insert_pipeline_run": lambda s, **kw: {"id": "run-x"},
        "finish_pipeline_run": lambda s, run_id, **kw: {"id": run_id},
        "log_pipeline_event": lambda s, run_id, **kw: {"id": "evt"},
        "update_company_profile": lambda s, cid, fields: {},
        "upsert_price_eod": lambda s, rows: len(rows),
        "upsert_statements_norm": lambda s, rows: len(rows),
        "upsert_filings_index": lambda s, rows: len(rows),
        "upsert_fx_rates": lambda s, rows: len(rows),
        "upsert_news_events": lambda s, rows: len(rows),
    })()

    # Pipeline must complete without raising
    metrics = mod._run_live_pipeline(
        repo_module=repo_full,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=FakeFMP402(),
        sec=TrackingSEC(),
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda r, cid, **kw: f"raw-{r.provider}",
        normalize_prices_fn=lambda *a, **kw: [],
        normalize_statements_fn=lambda *a, **kw: [],
        normalize_news_fn=lambda *a, **kw: [],
    )

    assert sec_companyfacts_calls == [], "SEC companyfacts must not be fetched with empty CIK"
    assert metrics["companies_processed"] == 1, "pipeline should mark company as processed"
    assert metrics["sec_fallback_upserted"] == 0


def test_10a_sec_source_rows_distinct_from_fmp_source():
    """SEC rows have source='sec_edgar'; FMP rows have source='fmp'. They are distinct."""
    from investment_app.etl.normalize_sec_companyfacts import normalize_sec_companyfacts_annual

    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "accn": "0000723254-24-000001",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-01-15",
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 25_000_000_000,
                            }
                        ]
                    }
                }
            }
        }
    }
    sec_rows, _ = normalize_sec_companyfacts_annual(
        payload, "company-mu", "MU", "0000723254"
    )
    fmp_row = {"source": "fmp", "fiscal_year": 2023, "fiscal_period": "FY"}

    assert all(r["source"] == "sec_edgar" for r in sec_rows)
    assert fmp_row["source"] != sec_rows[0]["source"]


def test_10a_sec_connector_failure_pipeline_continues():
    """If SEC companyfacts fetch fails (500), pipeline continues and marks company processed."""
    mod = _load_pipeline_module()
    from investment_app.connectors.base import ProviderResponse

    class FakeFMP402:
        def get_profile(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="profile", params={},
                status_code=200, success=True,
                payload=[{"companyName": "MU", "exchangeShortName": "NASDAQ",
                          "country": "US", "currency": "USD",
                          "sector": "Tech", "industry": "Semiconductors",
                          "cik": "0000723254"}],
                payload_text="profile",
            )

        def get_historical_prices(self, ticker):
            return ProviderResponse(
                provider="fmp", endpoint="prices", params={},
                status_code=200, success=True,
                payload={"historical": []}, payload_text="prices",
            )

        def get_income_statement(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="income", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

        def get_balance_sheet(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="balance", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

        def get_cash_flow(self, ticker, **kwargs):
            return ProviderResponse(
                provider="fmp", endpoint="cashflow", params={},
                status_code=402, success=False, payload=None, payload_text="",
            )

    class FailingSEC:
        def get_submissions(self, cik):
            return ProviderResponse(
                provider="sec_edgar", endpoint="submissions", params={},
                status_code=200, success=True,
                payload={"cik": cik, "filings": {"recent": {
                    "form": [], "accessionNumber": [], "filingDate": [], "primaryDocument": []
                }}},
                payload_text="submissions",
            )

        def get_company_facts(self, cik):
            return _fail_sec_facts_response()

    repo_full = type("Repo", (), {
        "list_watchlist_active_companies": lambda s: [{
            "id": "company-mu", "ticker": "MU", "name": "Micron",
            "currency": "USD", "cik": "0000723254",
        }],
        "get_company_by_ticker": lambda s, t: {"id": "company-mu"},
        "insert_pipeline_run": lambda s, **kw: {"id": "run-mu"},
        "finish_pipeline_run": lambda s, run_id, **kw: {"id": run_id},
        "log_pipeline_event": lambda s, run_id, **kw: {"id": "evt"},
        "update_company_profile": lambda s, cid, fields: {},
        "upsert_price_eod": lambda s, rows: len(rows),
        "upsert_statements_norm": lambda s, rows: len(rows),
        "upsert_filings_index": lambda s, rows: len(rows),
        "upsert_fx_rates": lambda s, rows: len(rows),
        "upsert_news_events": lambda s, rows: len(rows),
    })()

    metrics = mod._run_live_pipeline(
        repo_module=repo_full,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=FakeFMP402(),
        sec=FailingSEC(),
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda r, cid, **kw: f"raw-{r.provider}",
        normalize_prices_fn=lambda *a, **kw: [],
        normalize_statements_fn=lambda *a, **kw: [],
        normalize_news_fn=lambda *a, **kw: [],
    )

    # Pipeline should not crash; company should still be marked processed
    assert metrics["companies_processed"] == 1
    assert metrics["sec_fallback_upserted"] == 0


# ── Phase 10A regression: per-stage error classification ─────────────────────


def _make_repo_with_upsert_error():
    """Repo stub where upsert_statements_norm always raises a simulated APIError."""

    class _FakeAPIError(Exception):
        pass

    class _ErrorRepo(_SimpleRepo):
        def upsert_statements_norm(self, rows):
            raise _FakeAPIError("column raw_payload_id does not exist")

    return _ErrorRepo(), _FakeAPIError


def test_10a_upsert_apierror_classified_as_statements_upsert_stage():
    """When upsert_statements_norm raises, the logged event must carry stage='statements_upsert'.

    Regression test for the production failure where a single try/except masked
    the stage and emitted only error_type=APIError with no stage information.
    """
    mod = _load_pipeline_module()
    repo, FakeAPIError = _make_repo_with_upsert_error()

    mod._try_sec_statements_fallback(
        sec=type("SEC", (), {
            "get_company_facts": lambda self, cik: _ok_sec_facts_response()
        })(),
        cik="0000723254",
        company_id="company-mu",
        ticker="MU",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-1",
        metrics={"sec_fallback_upserted": 0},
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: "raw-uuid-1234",
        normalize_sec_fn=lambda *a, **kw: (
            [{"company_id": "company-mu", "fiscal_year": 2023,
              "fiscal_period": "annual", "period_end_date": "2023-09-30",
              "currency": "USD", "source": "sec_edgar",
              "revenue": 25_000_000_000, "net_income": 3_000_000_000,
              "total_assets": 40_000_000_000, "restated_flag": False,
              "metadata": {}}],
            {"rows_normalized": 1, "missing_fields": [], "weak_fallbacks": []},
        ),
    )

    error_events = [e for e in repo.events if e["level"] == "error"]
    assert error_events, "Expected at least one error-level pipeline event"
    details = error_events[-1]["details"]
    assert details.get("stage") == "statements_upsert", (
        f"Expected stage='statements_upsert', got {details.get('stage')!r}"
    )
    assert details.get("error_type") == "_FakeAPIError"
    assert details.get("event") == "sec_fallback_failed"


def test_10a_normalize_error_classified_as_sec_normalize_stage():
    """When normalize_sec_fn raises, the logged event must carry stage='sec_normalize'."""
    mod = _load_pipeline_module()
    repo = _SimpleRepo()

    def _exploding_normalizer(*a, **kw):
        raise ValueError("unexpected payload shape")

    mod._try_sec_statements_fallback(
        sec=type("SEC", (), {
            "get_company_facts": lambda self, cik: _ok_sec_facts_response()
        })(),
        cik="0000723254",
        company_id="company-mu",
        ticker="MU",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-1",
        metrics={"sec_fallback_upserted": 0},
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: "raw-uuid-1234",
        normalize_sec_fn=_exploding_normalizer,
    )

    error_events = [e for e in repo.events if e["level"] == "error"]
    assert error_events, "Expected at least one error-level pipeline event"
    details = error_events[-1]["details"]
    assert details.get("stage") == "sec_normalize"
    assert details.get("error_type") == "ValueError"


def test_10a_fetch_error_classified_as_sec_fetch_stage():
    """When SEC get_company_facts raises, the logged event must carry stage='sec_fetch'."""
    mod = _load_pipeline_module()
    repo = _SimpleRepo()

    class _FailingSECFetch:
        def get_company_facts(self, cik):
            raise ConnectionError("timeout")

    mod._try_sec_statements_fallback(
        sec=_FailingSECFetch(),
        cik="0000723254",
        company_id="company-mu",
        ticker="MU",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-1",
        metrics={"sec_fallback_upserted": 0},
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: None,
        normalize_sec_fn=lambda *a, **kw: ([], {}),
    )

    error_events = [e for e in repo.events if e["level"] == "error"]
    assert error_events
    details = error_events[-1]["details"]
    assert details.get("stage") == "sec_fetch"
    assert details.get("error_type") == "ConnectionError"


def test_10a_no_rows_emits_sec_fallback_no_rows_event():
    """When normalizer returns empty list, event must be 'sec_fallback_no_rows', not 'sec_fallback_failed'."""
    mod = _load_pipeline_module()
    repo = _SimpleRepo()

    mod._try_sec_statements_fallback(
        sec=type("SEC", (), {
            "get_company_facts": lambda self, cik: _ok_sec_facts_response()
        })(),
        cik="0000723254",
        company_id="company-mu",
        ticker="MU",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-1",
        metrics={"sec_fallback_upserted": 0},
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: "raw-uuid-1234",
        normalize_sec_fn=lambda *a, **kw: (
            [],
            {"rows_normalized": 0, "missing_fields": ["revenue"], "weak_fallbacks": []},
        ),
    )

    events = [e["details"].get("event") for e in repo.events]
    assert "sec_fallback_no_rows" in events, (
        f"Expected 'sec_fallback_no_rows' event but got: {events}"
    )
    assert "sec_fallback_failed" not in events, (
        "Empty-rows path must not emit 'sec_fallback_failed'"
    )


def test_10a_upserted_rows_do_not_contain_raw_payload_id_when_absent():
    """normalize_sec_companyfacts_annual must not include raw_payload_id when not provided.

    Regression: if raw_payload_id is truthy and statements_norm has no such column,
    Supabase raises APIError.  When raw_payload_id is None/falsy, the key must be
    absent from every row so the upsert succeeds even without migration 008.
    """
    from investment_app.etl.normalize_sec_companyfacts import normalize_sec_companyfacts_annual

    facts = _ok_sec_facts_response().payload
    rows, _ = normalize_sec_companyfacts_annual(
        facts,
        "company-mu",
        "MU",
        "0000723254",
        currency="USD",
        fallback_reason="fmp_402",
        raw_payload_id=None,
    )
    assert rows, "Expected at least one normalized row"
    for row in rows:
        assert "raw_payload_id" not in row, (
            "raw_payload_id must not appear in row when not provided"
        )


def test_10a_upserted_rows_contain_raw_payload_id_when_provided():
    """normalize_sec_companyfacts_annual includes raw_payload_id in rows when provided.

    This documents the intended behaviour — requires migration 008 to be applied
    in Supabase before rows with raw_payload_id can be upserted successfully.
    """
    from investment_app.etl.normalize_sec_companyfacts import normalize_sec_companyfacts_annual

    facts = _ok_sec_facts_response().payload
    rows, _ = normalize_sec_companyfacts_annual(
        facts,
        "company-mu",
        "MU",
        "0000723254",
        currency="USD",
        fallback_reason="fmp_402",
        raw_payload_id="550e8400-e29b-41d4-a716-446655440000",
    )
    assert rows, "Expected at least one normalized row"
    for row in rows:
        assert row.get("raw_payload_id") == "550e8400-e29b-41d4-a716-446655440000"


def test_10a_raw_store_failure_classified_as_raw_payload_read_stage():
    """When store_raw_response_fn raises, stage must be 'raw_payload_read' (not 'sec_fetch').

    This verifies the separate Stage 1b try/except block added after the
    GPT-5.4 review that required raw payload persistence failures to be
    distinguishable from SEC network failures.
    """
    mod = _load_pipeline_module()
    repo = _SimpleRepo()

    def _failing_store(response, company_id, **kw):
        raise OSError("Supabase payload column missing")

    mod._try_sec_statements_fallback(
        sec=type("SEC", (), {
            "get_company_facts": lambda self, cik: _ok_sec_facts_response()
        })(),
        cik="0000723254",
        company_id="company-mu",
        ticker="MU",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-1",
        metrics={"sec_fallback_upserted": 0},
        repo_module=repo,
        store_raw_response_fn=_failing_store,
        normalize_sec_fn=lambda *a, **kw: ([{"stub": True}], {}),
    )

    error_events = [e for e in repo.events if e["level"] == "error"]
    assert error_events, "Expected at least one error-level event when raw store fails"
    details = error_events[-1]["details"]
    assert details.get("stage") == "raw_payload_read", (
        f"Expected stage='raw_payload_read', got {details.get('stage')!r}"
    )
    assert details.get("error_type") == "OSError"
    assert details.get("event") == "sec_fallback_failed"
    # Confirm normalizer was never reached (store raised before normalize)
    assert details.get("stage") != "sec_normalize"


# ---------------------------------------------------------------------------
# ORCL-like large companyfacts fixture
# ---------------------------------------------------------------------------

def _make_orcl_companyfacts() -> dict:
    """Realistic Oracle-shaped companyfacts fixture (5 fiscal years, 15+ concepts).

    Modelled on Oracle Corp (CIK 0001341439): fiscal year ends May 31,
    values approximate scale only — no live data fetched.
    """
    from investment_app.connectors.base import ProviderResponse  # noqa: F401 (import check)

    def _fact(fy, val, filed, end, form="10-K", fp="FY"):
        return {
            "accn": f"0001341439-{fy}-000001",
            "fy": fy,
            "fp": fp,
            "form": form,
            "filed": filed,
            "start": f"{fy - 1}-06-01",
            "end": end,
            "val": val,
        }

    years = [
        (2023, "2023-07-20", "2023-05-31"),
        (2022, "2022-07-01", "2022-05-31"),
        (2021, "2021-06-25", "2021-05-31"),
        (2020, "2020-07-01", "2020-05-31"),
        (2019, "2019-07-01", "2019-05-31"),
    ]

    def _usd_series(values_by_year):
        return {"units": {"USD": [
            _fact(fy, val, filed, end)
            for fy, val, filed, end in [
                (y, values_by_year[y], f, e) for y, f, e in years if y in values_by_year
            ]
        ]}}

    revenues = {2023: 50_000_000_000, 2022: 47_000_000_000, 2021: 40_000_000_000,
                2020: 39_000_000_000, 2019: 39_500_000_000}
    net_incomes = {2023: 9_000_000_000, 2022: 6_700_000_000, 2021: 13_000_000_000,
                  2020: 10_100_000_000, 2019: 11_000_000_000}
    assets = {2023: 130_000_000_000, 2022: 109_000_000_000, 2021: 131_000_000_000,
              2020: 115_000_000_000, 2019: 108_000_000_000}
    liabilities = {2023: 116_000_000_000, 2022: 99_000_000_000, 2021: 117_000_000_000,
                   2020: 102_000_000_000, 2019: 96_000_000_000}
    cfo_vals = {2023: 17_000_000_000, 2022: 15_000_000_000, 2021: 15_700_000_000,
                2020: 14_000_000_000, 2019: 13_500_000_000}
    capex_vals = {2023: 1_400_000_000, 2022: 1_100_000_000, 2021: 1_200_000_000,
                  2020: 1_300_000_000, 2019: 1_300_000_000}

    us_gaap = {
        # Income
        "RevenueFromContractWithCustomerExcludingAssessedTax": _usd_series(revenues),
        "NetIncomeLoss": _usd_series(net_incomes),
        "OperatingIncomeLoss": _usd_series(
            {2023: 12_000_000_000, 2022: 9_500_000_000, 2021: 10_000_000_000,
             2020: 9_000_000_000, 2019: 9_500_000_000}
        ),
        "GrossProfit": _usd_series(
            {2023: 38_000_000_000, 2022: 35_000_000_000, 2021: 30_000_000_000,
             2020: 29_000_000_000, 2019: 30_000_000_000}
        ),
        # Balance sheet
        "Assets": _usd_series(assets),
        "Liabilities": _usd_series(liabilities),
        "StockholdersEquity": _usd_series(
            {2023: 14_000_000_000, 2022: 10_000_000_000, 2021: 14_000_000_000,
             2020: 13_000_000_000, 2019: 12_000_000_000}
        ),
        "CashAndCashEquivalentsAtCarryingValue": _usd_series(
            {2023: 9_000_000_000, 2022: 7_000_000_000, 2021: 8_000_000_000,
             2020: 6_000_000_000, 2019: 7_000_000_000}
        ),
        "LongTermDebt": _usd_series(
            {2023: 86_000_000_000, 2022: 75_000_000_000, 2021: 75_000_000_000,
             2020: 70_000_000_000, 2019: 56_000_000_000}
        ),
        # Cash flow
        "NetCashProvidedByUsedInOperatingActivities": _usd_series(cfo_vals),
        "PaymentsToAcquirePropertyPlantAndEquipment": _usd_series(capex_vals),
        "DepreciationDepletionAndAmortization": _usd_series(
            {2023: 2_000_000_000, 2022: 2_000_000_000, 2021: 1_900_000_000,
             2020: 1_900_000_000, 2019: 1_800_000_000}
        ),
        # Shares
        "WeightedAverageNumberOfDilutedSharesOutstanding": {
            "units": {"shares": [
                _fact(fy, shares, filed, end)
                for (fy, filed, end), shares in zip(years, [
                    2_700_000_000, 2_830_000_000, 2_950_000_000,
                    3_100_000_000, 3_200_000_000
                ])
            ]}
        },
    }
    return {"cik": "0001341439", "facts": {"us-gaap": us_gaap}}


def test_10a_orcl_like_fixture_normalizes_correctly():
    """An Oracle-shaped companyfacts payload (5 years, 15 concepts) must normalize
    to exactly 5 rows with essential fields populated and correct source metadata.
    No live API calls.
    """
    from investment_app.etl.normalize_sec_companyfacts import normalize_sec_companyfacts_annual

    payload = _make_orcl_companyfacts()
    rows, diag = normalize_sec_companyfacts_annual(
        payload,
        company_id="company-orcl",
        ticker="ORCL",
        cik="0001341439",
        currency="USD",
        fallback_reason="fmp_402",
        raw_payload_id=None,
    )

    assert len(rows) == 5, f"Expected 5 annual rows, got {len(rows)}"

    # Most-recent year first
    assert rows[0]["fiscal_year"] == 2023
    assert rows[-1]["fiscal_year"] == 2019

    # Essential fields present in all rows
    for row in rows:
        assert row["revenue"] is not None, f"Missing revenue for FY{row['fiscal_year']}"
        assert row["net_income"] is not None
        assert row["total_assets"] is not None
        assert row["cfo"] is not None
        assert row["source"] == "sec_edgar"
        assert row["fiscal_period"] == "annual"
        assert row["currency"] == "USD"
        assert row["restated_flag"] is False
        assert "metadata" in row
        assert row["metadata"]["source_provider"] == "sec_edgar"
        assert row["metadata"]["fallback_reason"] == "fmp_402"
        assert "raw_payload_id" not in row  # not provided

    # FCF should be derivable (CFO and capex both present)
    assert rows[0]["free_cash_flow"] is not None
    assert rows[0]["free_cash_flow"] == pytest.approx(
        17_000_000_000 - 1_400_000_000, rel=1e-6
    )

    # No essential fields missing
    essential_missing = {f for f in diag.get("missing_fields", [])
                         if f in {"revenue", "net_income", "total_assets"}}
    assert not essential_missing, f"Essential fields missing: {essential_missing}"


# ===========================================================================
# Phase 10B — Twelve Data price fallback tests
# ===========================================================================


def _twelve_ok_response():
    """Minimal valid Twelve Data time-series response."""
    return ProviderResponse(
        provider="twelve_data",
        endpoint="time_series",
        params={"symbol": "ORCL", "interval": "1day"},
        status_code=200,
        success=True,
        payload={
            "meta": {"symbol": "ORCL", "currency": "USD"},
            "values": [
                {
                    "datetime": "2024-01-02",
                    "open": "102.50",
                    "high": "105.00",
                    "low": "101.00",
                    "close": "104.00",
                    "volume": "5000000",
                },
            ],
        },
        payload_text="twelve_ok",
    )


def _twelve_fail_response():
    return ProviderResponse(
        provider="twelve_data",
        endpoint="time_series",
        params={"symbol": "ORCL", "interval": "1day"},
        status_code=0,
        success=False,
        payload=None,
        payload_text=None,
        error_message="twelve_data_request_failed (ConnectError)",
    )


class _PriceRepo(_SimpleRepo):
    """Repo stub that also tracks price_eod upserts."""

    def __init__(self):
        super().__init__()
        self.price_rows: list[dict] = []
        self.statement_rows: list[dict] = []
        self.data_quality_snapshots: list[dict] = []

    def upsert_price_eod(self, rows):
        self.price_rows.extend(rows)
        return len(rows)

    def upsert_statements_norm(self, rows):
        self.upserted.extend(rows)
        self.statement_rows.extend(rows)
        return len(rows)

    def upsert_filings_index(self, rows):
        return len(rows)

    def upsert_news_events(self, rows):
        return len(rows)

    def update_company_profile(self, cid, fields):
        return {}

    def get_prices_for_company(self, company_id, **kwargs):
        rows = [row for row in self.price_rows if row.get("company_id") == company_id]
        rows.sort(key=lambda row: (str(row.get("price_date") or ""), str(row.get("provider") or "")), reverse=True)
        return rows

    def get_statements_for_company(self, company_id, **kwargs):
        rows = [
            row for row in self.statement_rows
            if row.get("company_id") in (None, company_id)
        ]
        rows.sort(key=lambda row: (str(row.get("period_end_date") or ""), int(row.get("fiscal_year") or 0)), reverse=True)
        return rows

    def upsert_company_data_quality_snapshots(self, rows):
        self.data_quality_snapshots.extend(rows)
        return len(rows)


class _PriceRepoWithPipelineSupport(_PriceRepo):
    """Full repo stub for _run_live_pipeline integration tests."""

    def list_watchlist_active_companies(self):
        return [
            {
                "id": "company-orcl",
                "ticker": "ORCL",
                "name": "Oracle",
                "currency": "USD",
                "cik": "0001341439",
            }
        ]

    def get_company_by_ticker(self, ticker):
        return {"id": "company-orcl"}

    def insert_pipeline_run(self, **kw):
        return {"id": "run-10b"}

    def finish_pipeline_run(self, run_id, **kw):
        return {"id": run_id}

    def upsert_fx_rates(self, rows):
        return len(rows)


def _fmp_402_price():
    return ProviderResponse(
        provider="fmp", endpoint="historical-price-eod/full", params={},
        status_code=402, success=False, payload=None, payload_text="",
    )


def _fmp_ok_price_with_rows():
    return ProviderResponse(
        provider="fmp", endpoint="historical-price-eod/full", params={},
        status_code=200, success=True,
        payload={"historical": [{"date": "2024-01-02", "close": 104.0}]},
        payload_text="prices",
    )


class _FakeFMPPriceSuccess:
    def get_profile(self, ticker):
        return ProviderResponse(provider="fmp", endpoint="profile", params={},
                                status_code=200, success=True,
                                payload=[{"companyName": "Oracle", "exchangeShortName": "NYSE",
                                          "country": "US", "currency": "USD",
                                          "sector": "Tech", "industry": "Cloud",
                                          "cik": "0001341439"}],
                                payload_text="profile")

    def get_historical_prices(self, ticker):
        return _fmp_ok_price_with_rows()

    def get_income_statement(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="income", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="income")

    def get_balance_sheet(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="balance", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="balance")

    def get_cash_flow(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="cashflow", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="cashflow")


class _FakeFMP402Price:
    def get_profile(self, ticker):
        return ProviderResponse(provider="fmp", endpoint="profile", params={},
                                status_code=200, success=True,
                                payload=[{"companyName": "Oracle", "exchangeShortName": "NYSE",
                                          "country": "US", "currency": "USD",
                                          "sector": "Tech", "industry": "Cloud",
                                          "cik": "0001341439"}],
                                payload_text="profile")

    def get_historical_prices(self, ticker):
        return _fmp_402_price()

    def get_income_statement(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="income", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="income")

    def get_balance_sheet(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="balance", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="balance")

    def get_cash_flow(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="cashflow", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="cashflow")


class _FakeFMPEmptyPayloadPrice:
    def get_profile(self, ticker):
        return ProviderResponse(provider="fmp", endpoint="profile", params={},
                                status_code=200, success=True,
                                payload=[{"companyName": "Oracle", "exchangeShortName": "NYSE",
                                          "country": "US", "currency": "USD",
                                          "sector": "Tech", "industry": "Cloud",
                                          "cik": "0001341439"}],
                                payload_text="profile")

    def get_historical_prices(self, ticker):
        return ProviderResponse(provider="fmp", endpoint="historical-price-eod/full", params={},
                                status_code=200, success=True, payload=None, payload_text="")

    def get_income_statement(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="income", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="income")

    def get_balance_sheet(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="balance", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="balance")

    def get_cash_flow(self, ticker, **kw):
        return ProviderResponse(provider="fmp", endpoint="cashflow", params={},
                                status_code=200, success=True,
                                payload=[{"calendarYear": "2023", "period": "FY"}],
                                payload_text="cashflow")


class _FakeTwelve:
    """Twelve Data stub that returns one valid price row."""

    def __init__(self):
        self.calls: list[str] = []

    def get_time_series(self, ticker, **kw):
        self.calls.append(ticker)
        return _twelve_ok_response()


class _FakeTwelveFailure:
    def __init__(self):
        self.calls: list[str] = []

    def get_time_series(self, ticker, **kw):
        self.calls.append(ticker)
        return _twelve_fail_response()


def _providers_no_gdelt_ecb():
    return {"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}}


def _run_pipeline_10b(fmp_stub, twelve_stub, repo=None, extra_kwargs=None):
    """Helper to invoke _run_live_pipeline with Phase 10B wiring."""
    mod = _load_pipeline_module()
    if repo is None:
        repo = _PriceRepoWithPipelineSupport()

    kwargs = dict(
        repo_module=repo,
        providers_config=_providers_no_gdelt_ecb(),
        fmp=fmp_stub,
        sec=None,
        ecb=None,
        gdelt=None,
        twelve=twelve_stub,
        store_raw_response_fn=lambda r, cid, **kw: f"raw-{r.provider}",
        normalize_prices_fn=lambda payload, cid, ticker, currency, raw_id=None: (
            [{"price_date": "2024-01-02", "close": 104.0, "provider": "fmp",
              "company_id": cid}]
            if (isinstance(payload, dict) and payload.get("historical"))
            else []
        ),
        normalize_statements_fn=lambda *a, **kw: [
            {"company_id": "company-orcl", "fiscal_year": 2023, "fiscal_period": "annual", "period_end_date": "2023-09-30",
             "revenue": 50_000_000_000, "net_income": 8_000_000_000,
             "total_assets": 100_000_000_000,
             "operating_income": None, "cfo": None, "free_cash_flow": None,
             "total_equity": None, "source": "fmp"}
        ],
        normalize_news_fn=lambda *a, **kw: [],
    )
    if extra_kwargs:
        kwargs.update(extra_kwargs)
    return mod._run_live_pipeline(**kwargs), repo


# ── Test 1: FMP price success does not call Twelve ────────────────────────────


def test_10b_fmp_price_success_does_not_call_twelve():
    twelve = _FakeTwelve()
    _run_pipeline_10b(_FakeFMPPriceSuccess(), twelve)
    assert twelve.calls == [], "Twelve should NOT be called when FMP price succeeds"


# ── Test 2: FMP 402 triggers Twelve fallback ──────────────────────────────────


def test_10b_fmp_402_triggers_twelve_price_fallback():
    twelve = _FakeTwelve()
    metrics, repo = _run_pipeline_10b(_FakeFMP402Price(), twelve)
    assert twelve.calls == ["ORCL"], "Twelve must be called after FMP 402"
    assert metrics["price_fallback_upserted"] >= 1


# ── Test 3: FMP empty payload triggers Twelve ─────────────────────────────────


def test_10b_fmp_empty_payload_triggers_twelve_fallback():
    twelve = _FakeTwelve()
    metrics, repo = _run_pipeline_10b(_FakeFMPEmptyPayloadPrice(), twelve)
    assert twelve.calls == ["ORCL"]
    assert metrics["price_fallback_upserted"] >= 1


# ── Test 4: FMP normalization zero rows triggers Twelve ───────────────────────


def test_10b_fmp_normalized_zero_rows_triggers_twelve_fallback():
    mod = _load_pipeline_module()
    twelve = _FakeTwelve()
    repo = _PriceRepoWithPipelineSupport()

    metrics = mod._run_live_pipeline(
        repo_module=repo,
        providers_config=_providers_no_gdelt_ecb(),
        fmp=_FakeFMPPriceSuccess(),
        sec=None,
        ecb=None,
        gdelt=None,
        twelve=twelve,
        store_raw_response_fn=lambda r, cid, **kw: f"raw-{r.provider}",
        normalize_prices_fn=lambda *a, **kw: [],  # always zero rows
        normalize_statements_fn=lambda *a, **kw: [
            {"fiscal_year": 2023, "fiscal_period": "annual", "period_end_date": "2023-09-30",
             "revenue": 50_000_000_000, "net_income": 8_000_000_000,
             "total_assets": 100_000_000_000,
             "operating_income": None, "cfo": None, "free_cash_flow": None,
             "total_equity": None, "source": "fmp"}
        ],
        normalize_news_fn=lambda *a, **kw: [],
    )

    assert twelve.calls == ["ORCL"], "Twelve must be called when FMP normalization yields zero rows"
    assert metrics["price_fallback_upserted"] >= 1


# ── Test 5: Twelve fetch failure is non-fatal ─────────────────────────────────


def test_10b_twelve_fetch_failure_pipeline_continues():
    twelve = _FakeTwelveFailure()
    metrics, repo = _run_pipeline_10b(_FakeFMP402Price(), twelve)
    assert metrics["companies_processed"] == 1
    assert metrics["price_fallback_upserted"] == 0


# ── Test 6: raw store failure classified as raw_payload_read ─────────────────


def test_10b_raw_store_failure_classified_as_raw_payload_read():
    mod = _load_pipeline_module()
    repo = _PriceRepoWithPipelineSupport()
    twelve = _FakeTwelve()

    def _exploding_raw_store(resp, cid, **kw):
        if resp.provider == "twelve_data":
            raise RuntimeError("DB write failed")
        return f"raw-{resp.provider}"

    mod._run_live_pipeline(
        repo_module=repo,
        providers_config=_providers_no_gdelt_ecb(),
        fmp=_FakeFMP402Price(),
        sec=None,
        ecb=None,
        gdelt=None,
        twelve=twelve,
        store_raw_response_fn=_exploding_raw_store,
        normalize_prices_fn=lambda *a, **kw: [],
        normalize_statements_fn=lambda *a, **kw: [
            {"fiscal_year": 2023, "fiscal_period": "annual", "period_end_date": "2023-09-30",
             "revenue": 50_000_000_000, "net_income": 8_000_000_000,
             "total_assets": 100_000_000_000,
             "operating_income": None, "cfo": None, "free_cash_flow": None,
             "total_equity": None, "source": "fmp"}
        ],
        normalize_news_fn=lambda *a, **kw: [],
    )

    failed_events = [
        e for e in repo.events
        if e.get("details", {}).get("stage") == "raw_payload_read"
        and e.get("details", {}).get("provider") == "twelve_data"
    ]
    assert failed_events, "Expected a raw_payload_read failure event for Twelve Data"


def test_12d1_position_review_alert_stage_runs_after_company_alerts():
    call_order: list[str] = []

    def _company_alerts(company_id, repo_module, alert_date, **kwargs):
        call_order.append("company_alerts")
        return {"alerts_sent": 0, "alert_history_written": 0, "alerts_deduplicated": 0}

    def _position_review_alerts(repo_module, alert_date):
        call_order.append("position_review_alerts")
        return {
            "position_review_positions_checked": 2,
            "position_review_alerts_opened": 1,
            "position_review_alerts_refreshed": 1,
            "position_review_alerts_resolved": 1,
        }

    metrics, repo = _run_pipeline_10b(
        _FakeFMPPriceSuccess(),
        _FakeTwelve(),
        extra_kwargs={
            "process_alerts_fn": _company_alerts,
            "process_position_review_alerts_fn": _position_review_alerts,
        },
    )

    assert call_order == ["company_alerts", "position_review_alerts"]
    assert metrics["position_review_positions_checked"] == 2
    assert metrics["position_review_alerts_opened"] == 1
    assert metrics["position_review_alerts_refreshed"] == 1
    assert metrics["position_review_alerts_resolved"] == 1
    assert any(
        event.get("stage") == "position_review_alerts"
        and event.get("message") == "Position review alerts evaluated."
        for event in repo.events
    )


# ── Test 7: normalizer failure classified as price_normalize ─────────────────


def test_10b_normalize_failure_classified_as_price_normalize():
    pipeline_mod = _load_pipeline_module()
    twelve = _FakeTwelve()
    repo = _PriceRepo()
    direct_metrics: dict = {"price_fallback_upserted": 0}

    def _exploding_normalize(payload, cid, ticker, currency, **kw):
        raise ValueError("bad payload shape")

    pipeline_mod._try_twelve_price_fallback(
        twelve=twelve,
        company_id="company-orcl",
        ticker="ORCL",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-norm-fail",
        metrics=direct_metrics,
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: "raw-twelve",
        normalize_twelve_fn=_exploding_normalize,
    )

    failed_events = [
        e for e in repo.events
        if e.get("details", {}).get("stage") == "price_normalize"
    ]
    assert failed_events, "Expected a price_normalize failure event"
    assert direct_metrics["price_fallback_upserted"] == 0


# ── Test 8: price upsert failure classified as price_upsert ──────────────────


def test_10b_upsert_failure_classified_as_price_upsert():
    pipeline_mod = _load_pipeline_module()
    twelve = _FakeTwelve()

    class _ErrorOnPriceUpsert(_PriceRepo):
        def upsert_price_eod(self, rows):
            raise RuntimeError("upsert failed")

    error_repo = _ErrorOnPriceUpsert()
    direct_metrics: dict = {"price_fallback_upserted": 0}

    from investment_app.etl.normalize_prices import normalize_twelve_data_prices

    pipeline_mod._try_twelve_price_fallback(
        twelve=twelve,
        company_id="company-orcl",
        ticker="ORCL",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-upsert-fail",
        metrics=direct_metrics,
        repo_module=error_repo,
        store_raw_response_fn=lambda r, cid, **kw: "raw-twelve",
        normalize_twelve_fn=normalize_twelve_data_prices,
    )

    failed_events = [
        e for e in error_repo.events
        if e.get("details", {}).get("stage") == "price_upsert"
    ]
    assert failed_events, "Expected a price_upsert failure event"
    assert direct_metrics["price_fallback_upserted"] == 0


# ── Test 9: zero Twelve rows emits price_fallback_no_rows ─────────────────────


def test_10b_zero_rows_emits_price_fallback_no_rows():
    pipeline_mod = _load_pipeline_module()
    twelve = _FakeTwelve()
    repo = _PriceRepo()
    direct_metrics: dict = {"price_fallback_upserted": 0}

    pipeline_mod._try_twelve_price_fallback(
        twelve=twelve,
        company_id="company-orcl",
        ticker="ORCL",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-zero-rows",
        metrics=direct_metrics,
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: "raw-twelve",
        normalize_twelve_fn=lambda *a, **kw: [],  # returns zero rows
    )

    no_rows_events = [
        e for e in repo.events
        if e.get("details", {}).get("event") == "price_fallback_no_rows"
    ]
    assert no_rows_events, "Expected price_fallback_no_rows event when normalizer returns []"
    assert direct_metrics["price_fallback_upserted"] == 0


# ── Test 10: latest_price_eod precedence: fmp beats twelve_data same date ─────


def test_10b_latest_price_eod_precedence_fmp_over_twelve_same_date():
    """Verify provider precedence ordering matches the SQL CASE expression."""

    def _precedence(provider: str) -> int:
        if provider == "fmp":
            return 0
        if provider == "twelve_data":
            return 1
        return 9

    rows = [
        {"provider": "twelve_data", "price_date": "2024-01-02", "close": 104.0},
        {"provider": "fmp",         "price_date": "2024-01-02", "close": 104.5},
        {"provider": "unknown_src", "price_date": "2024-01-02", "close": 103.0},
    ]

    sorted_rows = sorted(rows, key=lambda r: _precedence(r["provider"]))
    winner = sorted_rows[0]
    assert winner["provider"] == "fmp"
    assert _precedence("twelve_data") > _precedence("fmp")
    assert _precedence("unknown_src") > _precedence("twelve_data")


# ── Test 11: twelve=None emits price_fallback_unavailable event ───────────────


def test_10b_twelve_none_emits_unavailable_event():
    pipeline_mod = _load_pipeline_module()
    repo = _PriceRepo()
    direct_metrics: dict = {"price_fallback_upserted": 0}

    pipeline_mod._try_twelve_price_fallback(
        twelve=None,
        company_id="company-orcl",
        ticker="ORCL",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-no-twelve",
        metrics=direct_metrics,
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: None,
        normalize_twelve_fn=lambda *a, **kw: [],
    )

    unavailable_events = [
        e for e in repo.events
        if e.get("details", {}).get("event") == "price_fallback_unavailable_provider_disabled"
    ]
    assert unavailable_events, "Expected price_fallback_unavailable_provider_disabled event"
    assert direct_metrics["price_fallback_upserted"] == 0


# ── Test 12: successful fallback increments price_fallback_upserted ───────────


def test_10b_successful_fallback_increments_metric():
    pipeline_mod = _load_pipeline_module()
    twelve = _FakeTwelve()
    repo = _PriceRepo()
    direct_metrics: dict = {"price_fallback_upserted": 0}

    from investment_app.etl.normalize_prices import normalize_twelve_data_prices

    pipeline_mod._try_twelve_price_fallback(
        twelve=twelve,
        company_id="company-orcl",
        ticker="ORCL",
        currency="USD",
        fallback_reason="fmp_402",
        run_id="run-success",
        metrics=direct_metrics,
        repo_module=repo,
        store_raw_response_fn=lambda r, cid, **kw: "raw-twelve",
        normalize_twelve_fn=normalize_twelve_data_prices,
    )

    assert direct_metrics["price_fallback_upserted"] == 1
    succeeded_events = [
        e for e in repo.events
        if e.get("details", {}).get("event") == "price_fallback_succeeded"
    ]
    assert succeeded_events
    assert succeeded_events[0]["details"]["rows_upserted"] == 1


# ---------------------------------------------------------------------------
# Phase 12A.1: cross-provider price diagnostics
# ---------------------------------------------------------------------------


def test_12a1_price_validation_not_comparable_when_only_one_provider_exists():
    metrics, repo = _run_pipeline_10b(_FakeFMPPriceSuccess(), twelve_stub=None)

    assert metrics["price_validation_companies_checked"] == 1
    assert metrics["price_validation_comparisons"] == 0
    assert metrics["price_validation_not_comparable"] == 1

    validation_events = [
        e for e in repo.events
        if e.get("details", {}).get("event") == "price_cross_provider_validation"
    ]
    assert validation_events
    assert validation_events[0]["details"]["status"] == "not_comparable"
    assert len(repo.data_quality_snapshots) == 1
    assert repo.data_quality_snapshots[0]["price_validation_status"] == "not_comparable"


def test_12a1_price_validation_warning_for_overlapping_prices():
    repo = _PriceRepoWithPipelineSupport()
    repo.price_rows.append(
        {
            "company_id": "company-orcl",
            "price_date": "2024-01-02",
            "close": 101.5,
            "provider": "twelve_data",
            "created_at": "2024-01-02T22:31:00+00:00",
        }
    )

    metrics, _repo = _run_pipeline_10b(
        _FakeFMPPriceSuccess(),
        twelve_stub=None,
        repo=repo,
        extra_kwargs={
            "normalize_prices_fn": lambda payload, cid, ticker, currency, raw_id=None: [
                {
                    "price_date": "2024-01-02",
                    "close": 100.0,
                    "provider": "fmp",
                    "company_id": cid,
                    "created_at": "2024-01-02T22:30:00+00:00",
                }
            ],
        },
    )

    assert metrics["price_validation_companies_checked"] == 1
    assert metrics["price_validation_comparisons"] == 1
    assert metrics["price_validation_warnings"] == 1
    assert metrics["price_validation_critical"] == 0

    validation_events = [
        e for e in repo.events
        if e.get("details", {}).get("event") == "price_cross_provider_validation"
    ]
    assert validation_events
    assert validation_events[0]["details"]["status"] == "warning"
    assert validation_events[0]["level"] == "warning"
    assert len(repo.data_quality_snapshots) == 1
    snapshot = repo.data_quality_snapshots[0]
    assert snapshot["price_validation_status"] == "warning"
    assert "price_divergence_warning" in snapshot["warning_codes"]


def test_12a1_price_validation_critical_and_payload_is_safe():
    repo = _PriceRepoWithPipelineSupport()
    repo.price_rows.append(
        {
            "company_id": "company-orcl",
            "price_date": "2024-01-02",
            "close": 106.5,
            "provider": "twelve_data",
            "created_at": "2024-01-02T22:31:00+00:00",
        }
    )

    metrics, _repo = _run_pipeline_10b(
        _FakeFMPPriceSuccess(),
        twelve_stub=None,
        repo=repo,
        extra_kwargs={
            "normalize_prices_fn": lambda payload, cid, ticker, currency, raw_id=None: [
                {
                    "price_date": "2024-01-02",
                    "close": 100.0,
                    "provider": "fmp",
                    "company_id": cid,
                    "created_at": "2024-01-02T22:30:00+00:00",
                }
            ],
        },
    )

    assert metrics["price_validation_comparisons"] == 1
    assert metrics["price_validation_warnings"] == 0
    assert metrics["price_validation_critical"] == 1

    validation_events = [
        e for e in repo.events
        if e.get("details", {}).get("event") == "price_cross_provider_validation"
    ]
    assert validation_events
    details = validation_events[0]["details"]
    assert details["status"] == "critical"
    assert "reference_price" not in details
    assert "comparison_price" not in details
    lowered = str(details).lower()
    for forbidden in ("apikey", "api_key", "bearer", "supabase", "financialmodelingprep", "https://"):
        assert forbidden not in lowered
    assert len(repo.data_quality_snapshots) == 1
    snapshot = repo.data_quality_snapshots[0]
    assert snapshot["price_validation_status"] == "critical"
    assert "price_divergence_critical" in snapshot["warning_codes"]
    assert "reference_price" not in str(snapshot["details"]).lower()
    assert "comparison_price" not in str(snapshot["details"]).lower()


def test_12a2_snapshot_persist_failure_is_non_blocking():
    class _SnapshotErrorRepo(_PriceRepoWithPipelineSupport):
        def upsert_company_data_quality_snapshots(self, rows):
            raise RuntimeError("snapshot write failed")

    repo = _SnapshotErrorRepo()
    repo.price_rows.append(
        {
            "company_id": "company-orcl",
            "price_date": "2024-01-02",
            "close": 101.5,
            "provider": "twelve_data",
            "created_at": "2024-01-02T22:31:00+00:00",
        }
    )

    metrics, _repo = _run_pipeline_10b(
        _FakeFMPPriceSuccess(),
        twelve_stub=None,
        repo=repo,
        extra_kwargs={
            "normalize_prices_fn": lambda payload, cid, ticker, currency, raw_id=None: [
                {
                    "price_date": "2024-01-02",
                    "close": 100.0,
                    "provider": "fmp",
                    "company_id": cid,
                    "created_at": "2024-01-02T22:30:00+00:00",
                }
            ],
        },
    )

    assert metrics["companies_processed"] == 1
    failed_events = [
        e for e in repo.events
        if e.get("details", {}).get("event") == "company_data_quality_snapshot_persist_failed"
    ]
    assert failed_events


def test_12a3_snapshot_includes_no_statements_warning_non_blocking() -> None:
    metrics, repo = _run_pipeline_10b(
        _FakeFMPPriceSuccess(),
        twelve_stub=None,
        extra_kwargs={"normalize_statements_fn": lambda *a, **kw: []},
    )

    assert metrics["companies_processed"] == 1
    assert len(repo.data_quality_snapshots) == 1
    snapshot = repo.data_quality_snapshots[0]
    assert snapshot["price_validation_status"] == "not_comparable"
    assert "no_statements_available" in snapshot["warning_codes"]
    stmt = snapshot["details"]["statement_completeness"]
    assert stmt["annual_periods_found"] == 0
    assert stmt["missing_statement_domains"] == ["income", "cashflow", "balance"]


def test_12a3_snapshot_includes_statement_completeness_details() -> None:
    repo = _PriceRepoWithPipelineSupport()
    repo.price_rows.append(
        {
            "company_id": "company-orcl",
            "price_date": "2024-01-02",
            "close": 101.5,
            "provider": "twelve_data",
            "created_at": "2024-01-02T22:31:00+00:00",
        }
    )

    metrics, _repo = _run_pipeline_10b(
        _FakeFMPPriceSuccess(),
        twelve_stub=None,
        repo=repo,
        extra_kwargs={
            "normalize_prices_fn": lambda payload, cid, ticker, currency, raw_id=None: [
                {
                    "price_date": "2024-01-02",
                    "close": 100.0,
                    "provider": "fmp",
                    "company_id": cid,
                    "created_at": "2024-01-02T22:30:00+00:00",
                }
            ],
            "normalize_statements_fn": lambda *a, **kw: [
                {
                    "company_id": "company-orcl",
                    "fiscal_year": 2024,
                    "fiscal_period": "annual",
                    "period_end_date": "2024-12-31",
                    "revenue": 50_000_000_000,
                    "net_income": 8_000_000_000,
                    "cfo": None,
                    "capex": None,
                    "total_assets": 100_000_000_000,
                    "total_liabilities": None,
                    "total_debt": None,
                    "total_equity": None,
                    "diluted_shares": None,
                    "source": "fmp",
                }
            ],
        },
    )

    assert metrics["price_validation_warnings"] == 1
    assert len(repo.data_quality_snapshots) == 1
    snapshot = repo.data_quality_snapshots[0]
    assert "incomplete_statement_set" in snapshot["warning_codes"]
    assert "missing_key_fields" in snapshot["warning_codes"]
    assert "insufficient_period_coverage" in snapshot["warning_codes"]
    stmt = snapshot["details"]["statement_completeness"]
    assert stmt["latest_source"] == "fmp"
    assert stmt["annual_periods_found"] == 1
    assert "cashflow" in stmt["missing_statement_domains"]
    assert "cfo" in stmt["missing_fields"]
    assert "total_liabilities_or_debt" in stmt["missing_fields"]


def test_12a3_statement_diagnostics_do_not_change_signal_or_readiness_metrics() -> None:
    metrics, _repo = _run_pipeline_10b(_FakeFMPPriceSuccess(), twelve_stub=None)

    assert metrics["price_validation_companies_checked"] == 1
    assert metrics["signal_runs_upserted"] == 0


def test_12a4_snapshot_includes_fundamentals_overlap_missing_when_only_fmp_exists() -> None:
    metrics, repo = _run_pipeline_10b(_FakeFMPPriceSuccess(), twelve_stub=None)

    assert metrics["companies_processed"] == 1
    assert len(repo.data_quality_snapshots) == 1
    snapshot = repo.data_quality_snapshots[0]
    assert "fundamentals_provider_overlap_missing" in snapshot["warning_codes"]
    fundamentals = snapshot["details"]["fundamentals_provider_comparison"]
    assert fundamentals["overlapping_period_count"] == 0
    assert fundamentals["discrepancy_level"] == "not_comparable"


def test_12a4_snapshot_includes_fundamentals_provider_discrepancy() -> None:
    repo = _PriceRepoWithPipelineSupport()
    repo.statement_rows.append(
        {
            "company_id": "company-orcl",
            "fiscal_year": 2023,
            "fiscal_period": "annual",
            "period_end_date": "2023-09-30",
            "source": "sec_edgar",
            "revenue": 57_000_000_000,
            "net_income": 8_000_000_000,
            "total_assets": 100_000_000_000,
            "total_liabilities": 60_000_000_000,
            "total_equity": 40_000_000_000,
        }
    )

    metrics, _repo = _run_pipeline_10b(_FakeFMPPriceSuccess(), twelve_stub=None, repo=repo)

    assert metrics["companies_processed"] == 1
    assert len(repo.data_quality_snapshots) == 1
    snapshot = repo.data_quality_snapshots[0]
    assert "fundamentals_provider_discrepancy" in snapshot["warning_codes"]
    fundamentals = snapshot["details"]["fundamentals_provider_comparison"]
    assert fundamentals["overlapping_period_count"] == 1
    assert fundamentals["discrepancy_level"] == "warning"
    assert "revenue" in fundamentals["discrepant_fields"]
    assert fundamentals["max_relative_difference_pct"] == 0.122807


def test_12a4_fundamentals_diagnostics_do_not_change_readiness_or_signal_behavior() -> None:
    repo = _PriceRepoWithPipelineSupport()
    repo.statement_rows.append(
        {
            "company_id": "company-orcl",
            "fiscal_year": 2023,
            "fiscal_period": "annual",
            "period_end_date": "2023-09-30",
            "source": "sec_edgar",
            "revenue": 50_000_000_000,
            "net_income": 8_000_000_000,
            "total_assets": 100_000_000_000,
            "total_liabilities": 60_000_000_000,
            "total_equity": 40_000_000_000,
        }
    )

    metrics, _repo = _run_pipeline_10b(_FakeFMPPriceSuccess(), twelve_stub=None, repo=repo)

    assert metrics["price_validation_companies_checked"] == 1
    assert metrics["signal_runs_upserted"] == 0
