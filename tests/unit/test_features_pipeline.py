"""Unit tests for Phase 3 feature-computation orchestration in the pipeline.

Tests that:
- compute_all_features returns correctly shaped rows;
- missing data does not crash the pipeline;
- the dry-run path never calls compute_features_fn;
- the live orchestration calls upsert_ratios_factors;
- ratio computation errors are caught and logged without aborting the pipeline.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from investment_app.features import compute_all_features


SCRIPT = str(Path(__file__).parent.parent.parent / "scripts" / "run_daily_pipeline.py")


# ---------------------------------------------------------------------------
# compute_all_features — unit tests (no Supabase)
# ---------------------------------------------------------------------------


class _FakeRepo:
    """Minimal fake repo for testing compute_all_features directly."""

    def __init__(
        self,
        statements: list[dict] | None = None,
        prices: list[dict] | None = None,
        news: list[dict] | None = None,
        filings: list[dict] | None = None,
    ) -> None:
        self._statements = statements or []
        self._prices = prices or []
        self._news = news or []
        self._filings = filings or []

    def get_statements_for_company(self, company_id: str, **kwargs) -> list[dict]:
        return list(self._statements)

    def get_prices_for_company(self, company_id: str, **kwargs) -> list[dict]:
        return list(self._prices)

    def get_news_for_company(self, company_id: str, **kwargs) -> list[dict]:
        return list(self._news)

    def get_filings_for_company(self, company_id: str, **kwargs) -> list[dict]:
        return list(self._filings)


class _FilteringFakeRepo:
    """Fake repo that applies as_of_date filtering, exactly like the real DB.

    Used to prove that future rows are excluded from the final computed factor,
    not just that as_of_date is forwarded (which _TrackingRepo proves separately).
    """

    def __init__(
        self,
        statements: list[dict] | None = None,
        prices: list[dict] | None = None,
        news: list[dict] | None = None,
        filings: list[dict] | None = None,
    ) -> None:
        self._statements = statements or []
        self._prices = prices or []
        self._news = news or []
        self._filings = filings or []

    def get_statements_for_company(
        self, company_id: str, *, as_of_date: str | None = None, **kwargs
    ) -> list[dict]:
        rows = self._statements
        if as_of_date:
            rows = [r for r in rows if (r.get("period_end_date") or "") <= as_of_date]
        return sorted(rows, key=lambda r: r.get("period_end_date") or "", reverse=True)

    def get_prices_for_company(
        self, company_id: str, *, as_of_date: str | None = None, **kwargs
    ) -> list[dict]:
        rows = self._prices
        if as_of_date:
            rows = [r for r in rows if (r.get("price_date") or "") <= as_of_date]
        return sorted(rows, key=lambda r: r.get("price_date") or "", reverse=True)

    def get_news_for_company(
        self, company_id: str, *, as_of_date: str | None = None, **kwargs
    ) -> list[dict]:
        rows = self._news
        if as_of_date:
            rows = [r for r in rows if (r.get("published_at") or "") <= as_of_date + "Z"]
        return sorted(rows, key=lambda r: r.get("published_at") or "", reverse=True)

    def get_filings_for_company(
        self, company_id: str, *, as_of_date: str | None = None, **kwargs
    ) -> list[dict]:
        rows = self._filings
        if as_of_date:
            rows = [r for r in rows if (r.get("filing_date") or "") <= as_of_date]
        return sorted(rows, key=lambda r: r.get("filing_date") or "", reverse=True)


_ANNUAL_STMT = {
    "fiscal_year": 2023,
    "fiscal_period": "FY",
    "period_end_date": "2023-12-31",
    "revenue": 1000.0,
    "gross_profit": 600.0,
    "operating_income": 200.0,
    "ebit": 200.0,
    "ebitda": 300.0,
    "net_income": 150.0,
    "free_cash_flow": 120.0,
    "total_equity": 800.0,
    "total_debt": 200.0,
    "cash_and_equivalents": 50.0,
    "diluted_shares": 100.0,
}

_PRICE_ROW = {
    "price_date": "2024-01-02",
    "close": 50.0,
    "market_cap": 5000.0,
}


def test_compute_all_features_returns_row_with_required_keys():
    repo = _FakeRepo(statements=[_ANNUAL_STMT], prices=[_PRICE_ROW])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    assert row["company_id"] == "company-1"
    assert row["factor_date"] == "2024-01-02"
    assert "gross_margin" in row
    assert "net_margin" in row
    assert "roe" in row
    assert "momentum_20d" in row
    assert "volatility_30d" in row
    assert "news_sentiment_7d" in row
    assert "news_volume_7d" in row
    assert "data_quality_score" in row


def test_compute_all_features_records_statement_and_price_vintage_metadata():
    stmt = {
        **_ANNUAL_STMT,
        "source": "sec_edgar",
        "created_at": "2026-06-23T19:40:00+00:00",
    }
    price = {**_PRICE_ROW, "provider": "twelve_data"}
    repo = _FakeRepo(statements=[stmt], prices=[price])

    row = compute_all_features("company-1", repo, "2026-06-24")

    assert row is not None
    assert row["metadata"]["statement_period_end_date"] == "2023-12-31"
    assert row["metadata"]["statement_fiscal_year"] == 2023
    assert row["metadata"]["statement_source"] == "sec_edgar"
    assert row["metadata"]["statement_created_at"] == "2026-06-23T19:40:00+00:00"
    assert row["metadata"]["price_date"] == "2024-01-02"
    assert row["metadata"]["price_provider"] == "twelve_data"
    assert row["metadata"]["generated_at"]


def test_compute_all_features_no_data_returns_none():
    repo = _FakeRepo(statements=[], prices=[], news=[])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is None


def test_compute_all_features_statements_only_returns_row():
    """When price data is absent, market ratios are None but row is returned."""
    repo = _FakeRepo(statements=[_ANNUAL_STMT], prices=[])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    assert row["gross_margin"] == pytest.approx(0.6)
    assert row["pe_ratio"] is None
    assert row["momentum_20d"] is None


def test_compute_all_features_prices_only_returns_row():
    """When statements are absent, financial ratios are None but row is returned."""
    prices = [{"price_date": f"2024-01-{i:02d}", "close": 50.0} for i in range(1, 32)]
    repo = _FakeRepo(statements=[], prices=prices)
    row = compute_all_features("company-1", repo, "2024-01-31")
    assert row is not None
    assert row["gross_margin"] is None
    assert row["roe"] is None


def test_compute_all_features_filters_annual_only():
    """Quarterly statements must not be used for annual ratio computation."""
    quarterly = {
        **_ANNUAL_STMT,
        "fiscal_period": "Q1",
        "revenue": 999_999.0,  # deliberately wrong; should be ignored
    }
    repo = _FakeRepo(statements=[_ANNUAL_STMT, quarterly], prices=[_PRICE_ROW])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    # gross_margin should be from _ANNUAL_STMT (revenue=1000), not quarterly
    assert row["gross_margin"] == pytest.approx(600.0 / 1000.0)


def test_compute_all_features_data_quality_score_partial():
    """With statements but no prices, quality score < 100."""
    repo = _FakeRepo(statements=[_ANNUAL_STMT], prices=[])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    assert row["data_quality_score"] < 100.0
    assert row["data_quality_score"] >= 0.0


def test_compute_all_features_data_quality_score_with_price_and_statements():
    """With both statements and prices, quality score should be higher."""
    repo_full = _FakeRepo(statements=[_ANNUAL_STMT], prices=[_PRICE_ROW])
    repo_stmt_only = _FakeRepo(statements=[_ANNUAL_STMT], prices=[])
    full_score = compute_all_features("c1", repo_full, "2024-01-02")["data_quality_score"]
    stmt_score = compute_all_features("c1", repo_stmt_only, "2024-01-02")["data_quality_score"]
    assert full_score > stmt_score


def test_compute_all_features_news_sentiment_included():
    news = [
        {"published_at": "2024-01-28T00:00:00Z", "sentiment_raw": 0.8},
        {"published_at": "2024-01-27T00:00:00Z", "sentiment_raw": 0.4},
    ]
    repo = _FakeRepo(statements=[_ANNUAL_STMT], prices=[_PRICE_ROW], news=news)
    row = compute_all_features("company-1", repo, "2024-01-31")
    assert row is not None
    assert row["news_volume_7d"] == 2
    assert row["news_sentiment_7d"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Pipeline orchestration — compute_features_fn integration
# ---------------------------------------------------------------------------


def _load_pipeline_module():
    spec = importlib.util.spec_from_file_location("pipeline_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _PipelineFakeRepo:
    """Extended fake repo for full pipeline mock tests."""

    def __init__(self) -> None:
        self.list_active_companies_calls = 0
        self.inserted_runs: list[dict] = []
        self.finished_runs: list[dict] = []
        self.logged_events: list[dict] = []
        self.upserted_ratios: list[dict] = []

    def list_watchlist_active_companies(self):
        return [{"id": "company-1", "ticker": "AAPL", "currency": "USD", "cik": ""}]

    def list_active_companies(self):
        self.list_active_companies_calls += 1
        return [{"id": "company-1", "ticker": "AAPL", "currency": "USD", "cik": ""}]

    def get_company_by_ticker(self, ticker):
        return {"id": "company-1", "ticker": ticker}

    def insert_pipeline_run(self, **kwargs):
        self.inserted_runs.append(kwargs)
        return {"id": "run-1"}

    def finish_pipeline_run(self, run_id, **kwargs):
        self.finished_runs.append({"run_id": run_id, **kwargs})
        return {"id": run_id, **kwargs}

    def log_pipeline_event(self, run_id, **kwargs):
        self.logged_events.append({"run_id": run_id, **kwargs})
        return {"id": "evt-1", **kwargs}

    def update_company_profile(self, company_id, fields):
        return {"id": company_id}

    def upsert_price_eod(self, rows):
        return len(rows)

    def upsert_statements_norm(self, rows):
        return len(rows)

    def upsert_filings_index(self, rows):
        return len(rows)

    def upsert_fx_rates(self, rows):
        return len(rows)

    def upsert_news_events(self, rows):
        return len(rows)

    def upsert_ratios_factors(self, rows):
        self.upserted_ratios.extend(rows)
        return len(rows)

    def get_statements_for_company(self, company_id, **kwargs):
        return []

    def get_prices_for_company(self, company_id, **kwargs):
        return []

    def get_news_for_company(self, company_id, **kwargs):
        return []

    def get_filings_for_company(self, company_id, **kwargs):
        return []


def _noop_fn(*args, **kwargs):
    return []


def _noop_store(response, company_id, **kwargs):
    return "raw-id"


def test_pipeline_calls_compute_features_fn():
    mod = _load_pipeline_module()
    repo = _PipelineFakeRepo()
    features_calls: list[tuple] = []

    def fake_compute(company_id, repo_module, factor_date, **kwargs):
        features_calls.append((company_id, factor_date))
        return {
            "company_id": company_id,
            "factor_date": factor_date,
            "gross_margin": 0.6,
            "data_quality_score": 60.0,
        }

    mod._run_live_pipeline(
        repo_module=repo,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=_noop_store,
        normalize_prices_fn=_noop_fn,
        normalize_statements_fn=_noop_fn,
        normalize_news_fn=_noop_fn,
        compute_features_fn=fake_compute,
    )

    assert len(features_calls) == 1
    assert features_calls[0][0] == "company-1"
    assert len(repo.upserted_ratios) == 1


def test_pipeline_without_compute_features_fn_skips_ratios():
    mod = _load_pipeline_module()
    repo = _PipelineFakeRepo()

    metrics = mod._run_live_pipeline(
        repo_module=repo,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=_noop_store,
        normalize_prices_fn=_noop_fn,
        normalize_statements_fn=_noop_fn,
        normalize_news_fn=_noop_fn,
        compute_features_fn=None,
    )

    assert metrics["ratios_upserted"] == 0
    assert repo.upserted_ratios == []


def test_pipeline_compute_features_error_does_not_abort():
    """A crash in compute_features_fn must be caught; pipeline must succeed."""
    mod = _load_pipeline_module()
    repo = _PipelineFakeRepo()

    def crashing_compute(company_id, repo_module, factor_date, **kwargs):
        raise RuntimeError("simulated crash")

    metrics = mod._run_live_pipeline(
        repo_module=repo,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=_noop_store,
        normalize_prices_fn=_noop_fn,
        normalize_statements_fn=_noop_fn,
        normalize_news_fn=_noop_fn,
        compute_features_fn=crashing_compute,
    )

    # Pipeline should still succeed.
    assert repo.finished_runs[0]["status"] == "success"
    # Error event should be logged.
    error_events = [e for e in repo.logged_events if e.get("level") == "error"]
    assert len(error_events) >= 1


def test_pipeline_compute_features_returns_none_skips_upsert():
    """When compute_features_fn returns None, upsert must not be called."""
    mod = _load_pipeline_module()
    repo = _PipelineFakeRepo()

    metrics = mod._run_live_pipeline(
        repo_module=repo,
        providers_config={"providers": {"gdelt": {"enabled": False}, "ecb": {"enabled": False}}},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=_noop_store,
        normalize_prices_fn=_noop_fn,
        normalize_statements_fn=_noop_fn,
        normalize_news_fn=_noop_fn,
        compute_features_fn=lambda *a, **kw: None,
    )

    assert metrics["ratios_upserted"] == 0
    assert repo.upserted_ratios == []


def test_dry_run_does_not_call_compute_features_fn():
    """compute_features_fn must never be called during dry-run."""
    from typer.testing import CliRunner

    mod = _load_pipeline_module()
    compute_calls: list[bool] = []

    def sentinel(*args, **kwargs):
        compute_calls.append(True)
        return {}

    mod._run_live_pipeline_original = mod._run_live_pipeline
    mod._run_live_pipeline = sentinel

    runner = CliRunner()
    result = runner.invoke(mod.app, ["--dry-run"])

    assert result.exit_code == 0
    assert compute_calls == [], "compute_features_fn must not run in dry-run mode"

    # Restore original to avoid cross-test contamination.
    mod._run_live_pipeline = mod._run_live_pipeline_original
    del mod._run_live_pipeline_original


# ---------------------------------------------------------------------------
# Point-in-time safety — as_of_date forwarding
# ---------------------------------------------------------------------------


def test_compute_all_features_passes_factor_date_as_as_of_date():
    """compute_all_features must forward factor_date to every repo read."""
    calls: dict[str, str | None] = {}

    class _TrackingRepo:
        def get_statements_for_company(self, company_id, **kwargs):
            calls["statements"] = kwargs.get("as_of_date")
            return []

        def get_prices_for_company(self, company_id, **kwargs):
            calls["prices"] = kwargs.get("as_of_date")
            return []

        def get_news_for_company(self, company_id, **kwargs):
            calls["news"] = kwargs.get("as_of_date")
            return []

        def get_filings_for_company(self, company_id, **kwargs):
            calls["filings"] = kwargs.get("as_of_date")
            return []

    compute_all_features("company-1", _TrackingRepo(), "2023-06-30")

    assert calls["statements"] == "2023-06-30"
    assert calls["prices"] == "2023-06-30"
    assert calls["news"] == "2023-06-30"
    assert calls["filings"] == "2023-06-30"


# ---------------------------------------------------------------------------
# Fiscal-year deduplication
# ---------------------------------------------------------------------------


def test_compute_all_features_deduplicates_duplicate_fiscal_year():
    """Two rows for the same fiscal_year must not both contribute to ratios.

    The row with the higher period_end_date (the first after the DESC sort
    performed by the repository) is kept.
    """
    stmt_a = {**_ANNUAL_STMT, "fiscal_year": 2023, "period_end_date": "2023-12-31", "revenue": 1000.0}
    stmt_b = {**_ANNUAL_STMT, "fiscal_year": 2023, "period_end_date": "2023-09-30", "revenue": 800.0}
    # Simulate the DB returning these ordered by period_end_date DESC.
    repo = _FakeRepo(statements=[stmt_a, stmt_b], prices=[_PRICE_ROW])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    # Revenue should come from stmt_a (revenue=1000), not stmt_b (revenue=800).
    assert row["gross_margin"] == pytest.approx(600.0 / 1000.0)


def test_compute_all_features_dedup_uses_correct_prior_for_growth():
    """After dedup, [0] is current year and [1] is genuine prior year."""
    current = {**_ANNUAL_STMT, "fiscal_year": 2023, "period_end_date": "2023-12-31", "revenue": 1000.0}
    # Same fiscal_year as current — must be removed by dedup.
    duplicate = {**_ANNUAL_STMT, "fiscal_year": 2023, "period_end_date": "2023-09-30", "revenue": 500.0}
    prior = {**_ANNUAL_STMT, "fiscal_year": 2022, "period_end_date": "2022-12-31", "revenue": 800.0}
    repo = _FakeRepo(statements=[current, duplicate, prior], prices=[_PRICE_ROW])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    # revenue_growth = (1000 - 800) / 800 = 0.25; must not use the duplicate row.
    assert row["revenue_growth_yoy"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Data-quality score derivation
# ---------------------------------------------------------------------------


def test_compute_all_features_usd_company_awards_fx_points():
    """USD company: no FX conversion needed → has_fx_if_needed=True → full score."""
    repo = _FakeRepo(statements=[_ANNUAL_STMT], prices=[_PRICE_ROW])
    row_usd = compute_all_features("c1", repo, "2024-01-02", company_currency="USD")
    row_eur = compute_all_features("c1", repo, "2024-01-02", company_currency="EUR")
    assert row_usd is not None
    assert row_eur is not None
    # USD gets the FX point; EUR does not (conservative).
    assert row_usd["data_quality_score"] > row_eur["data_quality_score"]


def test_compute_all_features_filings_present_awards_points():
    """When filing rows are returned, has_filings=True increases quality score."""
    repo_no_filings = _FakeRepo(statements=[_ANNUAL_STMT], prices=[_PRICE_ROW], filings=[])
    repo_has_filings = _FakeRepo(
        statements=[_ANNUAL_STMT],
        prices=[_PRICE_ROW],
        filings=[{"id": "f1", "filing_date": "2024-01-10"}],
    )
    score_no = compute_all_features("c1", repo_no_filings, "2024-01-02")["data_quality_score"]
    score_yes = compute_all_features("c1", repo_has_filings, "2024-01-02")["data_quality_score"]
    assert score_yes > score_no


def test_compute_all_features_news_present_no_explicit_quality_flag():
    """News rows only affect quality via has_news (not yet in quality score).

    This test simply confirms that having news rows does not crash the pipeline
    and that news_volume_7d is populated.
    """
    news = [{"published_at": "2024-01-28T00:00:00Z", "sentiment_raw": 0.6}]
    repo = _FakeRepo(statements=[_ANNUAL_STMT], prices=[_PRICE_ROW], news=news)
    row = compute_all_features("c1", repo, "2024-01-31")
    assert row is not None
    assert row["news_volume_7d"] == 1


# ---------------------------------------------------------------------------
# Future-row exclusion — end-to-end behavior
# ---------------------------------------------------------------------------


def test_compute_all_features_excludes_future_statements():
    """Statements with period_end_date > factor_date must not affect the result."""
    past_stmt = {**_ANNUAL_STMT, "fiscal_year": 2023, "period_end_date": "2023-12-31", "revenue": 1000.0}
    future_stmt = {**_ANNUAL_STMT, "fiscal_year": 2025, "period_end_date": "2025-12-31", "revenue": 9_999.0}
    repo = _FilteringFakeRepo(statements=[past_stmt, future_stmt], prices=[_PRICE_ROW])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    # gross_margin must be derived from the past statement only (revenue=1000).
    assert row["gross_margin"] == pytest.approx(600.0 / 1000.0)


def test_compute_all_features_excludes_future_prices():
    """Price rows with price_date > factor_date must not affect the result."""
    past_price = {"price_date": "2024-01-02", "close": 50.0, "market_cap": 5000.0}
    future_price = {"price_date": "2025-06-01", "close": 9_999.0, "market_cap": 999_999.0}
    repo = _FilteringFakeRepo(statements=[_ANNUAL_STMT], prices=[past_price, future_price])
    row = compute_all_features("company-1", repo, "2024-01-02")
    assert row is not None
    # pe_ratio must be based on the past price row (market_cap=5000).
    assert row["pe_ratio"] == pytest.approx(5000.0 / 150.0)


# ---------------------------------------------------------------------------
# Restatement-aware selection
# ---------------------------------------------------------------------------


def test_compute_all_features_prefers_restated_row_when_same_period_end():
    """When two FY rows share period_end_date, restated_flag=True must be chosen."""
    original = {
        **_ANNUAL_STMT,
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "period_end_date": "2023-12-31",
        "revenue": 1000.0,
        "restated_flag": False,
        "created_at": "2024-01-15T00:00:00Z",
        "id": "aaaa-0001",
    }
    restated = {
        **_ANNUAL_STMT,
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "period_end_date": "2023-12-31",
        "revenue": 1100.0,  # distinct value so we can detect which row was chosen
        "restated_flag": True,
        "created_at": "2024-02-01T00:00:00Z",
        "id": "bbbb-0002",
    }
    repo = _FakeRepo(statements=[original, restated], prices=[_PRICE_ROW])
    row = compute_all_features("company-1", repo, "2024-03-01")
    assert row is not None
    # restated row (revenue=1100) must be selected.
    assert row["net_margin"] == pytest.approx(150.0 / 1100.0)


def test_compute_all_features_prefers_newer_ingestion_when_flags_equal():
    """When restated_flag is equal, the more recently ingested row must be chosen."""
    older = {
        **_ANNUAL_STMT,
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "period_end_date": "2023-12-31",
        "revenue": 1000.0,
        "restated_flag": False,
        "created_at": "2024-01-10T00:00:00Z",
        "id": "aaaa-0001",
    }
    newer = {
        **_ANNUAL_STMT,
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "period_end_date": "2023-12-31",
        "revenue": 1050.0,  # distinct value
        "restated_flag": False,
        "created_at": "2024-01-20T00:00:00Z",
        "id": "bbbb-0002",
    }
    repo = _FakeRepo(statements=[older, newer], prices=[_PRICE_ROW])
    row = compute_all_features("company-1", repo, "2024-03-01")
    assert row is not None
    # Newer ingestion (revenue=1050) must be selected.
    assert row["net_margin"] == pytest.approx(150.0 / 1050.0)
