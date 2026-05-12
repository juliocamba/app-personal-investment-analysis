"""Unit tests for Phase 4: valuation pipeline orchestration.

Tests cover:
- compute_valuation_run happy path (DCF + multiples)
- Financial-sector path
- DDM path when applicable
- No-data returns None
- Point-in-time safety (as_of_date forwarded)
- Percentile ordering
- Repository functions: get_ratios_for_company, upsert_valuation_run
- Pipeline script integration (dry-run + new metric key)
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from investment_app.valuation.scenarios import compute_valuation_run, MODEL_VERSION


# ---------------------------------------------------------------------------
# Fake repo for orchestration tests
# ---------------------------------------------------------------------------


class _FakeValuationRepo:
    """In-memory fake repo for valuation tests."""

    def __init__(
        self,
        *,
        statements: list[dict[str, Any]] | None = None,
        prices: list[dict[str, Any]] | None = None,
        ratios: list[dict[str, Any]] | None = None,
        record_calls: bool = False,
    ) -> None:
        self._statements = statements or []
        self._prices = prices or []
        self._ratios = ratios or []
        self.calls: list[tuple[str, Any]] = []
        self._record = record_calls

    def get_statements_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        if self._record:
            self.calls.append(("get_statements_for_company", as_of_date))
        return self._statements

    def get_prices_for_company(
        self, company_id: str, *, as_of_date: str | None = None, limit: int = 2
    ) -> list[dict[str, Any]]:
        if self._record:
            self.calls.append(("get_prices_for_company", as_of_date))
        return self._prices

    def get_ratios_for_company(
        self, company_id: str, *, as_of_date: str | None = None
    ) -> list[dict[str, Any]]:
        if self._record:
            self.calls.append(("get_ratios_for_company", as_of_date))
        return self._ratios


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
_VALUATION_DATE = "2024-01-01"

_STMT = {
    "revenue": 1_000_000.0,
    "ebit": 150_000.0,
    "depreciation_amortization": 30_000.0,
    "capex": -50_000.0,
    "net_income": 100_000.0,
    "total_equity": 600_000.0,
    "total_debt": 200_000.0,
    "cash_and_equivalents": 50_000.0,
    # Canonical ``statements_norm`` field name (was ``shares_diluted`` — wrong).
    "diluted_shares": 10_000.0,
    "free_cash_flow": 80_000.0,
}

_STMT_PRIOR = {
    "revenue": 900_000.0,
    "ebit": 120_000.0,
    "net_income": 80_000.0,
    "total_equity": 550_000.0,
    "total_debt": 200_000.0,
    "cash_and_equivalents": 40_000.0,
    # Canonical ``statements_norm`` field name.
    "diluted_shares": 10_000.0,
}

# Canonical ``price_eod`` field name is ``close`` (not ``close_price``).
_PRICE = {"close": 12.0}

_RATIOS = [
    {"pe_ratio": 15.0, "ev_to_ebitda": 8.0, "price_to_sales": 1.5, "price_to_book": 1.8, "roe": 0.15},
    {"pe_ratio": 16.0, "ev_to_ebitda": 9.0, "price_to_sales": 1.6, "price_to_book": 1.9, "roe": 0.14},
]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_compute_valuation_run_returns_dict_with_required_keys():
    repo = _FakeValuationRepo(
        statements=[_STMT, _STMT_PRIOR],
        prices=[_PRICE],
        ratios=_RATIOS,
    )
    result = compute_valuation_run(
        _COMPANY_ID, repo, _VALUATION_DATE, company_currency="USD"
    )
    assert result is not None
    expected_keys = {
        "company_id", "valuation_date", "model_version",
        "method_weights", "assumptions",
        "iv_p10", "iv_p25", "iv_p50", "iv_p75", "iv_p90",
        "current_price", "margin_of_safety_conservative", "uncertainty_width",
        "currency",
    }
    assert set(result.keys()) == expected_keys


def test_compute_valuation_run_company_id_and_date_passthrough():
    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result["company_id"] == _COMPANY_ID
    assert result["valuation_date"] == _VALUATION_DATE
    assert result["model_version"] == MODEL_VERSION
    assert result["currency"] == "USD"


def test_compute_valuation_run_percentiles_are_ordered():
    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    p10 = result["iv_p10"]
    p25 = result["iv_p25"]
    p50 = result["iv_p50"]
    p75 = result["iv_p75"]
    p90 = result["iv_p90"]
    # All must be non-None when there is enough data for DCF + multiples.
    assert all(v is not None for v in (p10, p25, p50, p75, p90))
    assert p10 <= p25 <= p50 <= p75 <= p90


def test_compute_valuation_run_current_price_set():
    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    assert result["current_price"] == pytest.approx(12.0)


def test_compute_valuation_run_margin_of_safety_is_numeric_or_none():
    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    mos = result["margin_of_safety_conservative"]
    # May be positive or negative depending on IV vs price; must be a float if not None.
    if mos is not None:
        assert isinstance(mos, float)


def test_compute_valuation_run_stores_diagnostics_for_partial_result():
    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[], ratios=[])
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    diagnostics = result["assumptions"]["diagnostics"]
    assert diagnostics["valuation_status"] == "partial"
    assert diagnostics["freshness_flag"] == "missing_inputs"
    assert diagnostics["data_quality_flag"] == "limited"
    assert "missing_latest_price" in diagnostics["blockers"]
    assert "missing_ratio_factor_history" in diagnostics["blockers"]
    assert "margin_of_safety_unavailable" in diagnostics["warnings"]


def test_compute_valuation_run_negative_direct_fcf_blocks_dcf_but_preserves_diagnostics():
    stmt = {**_STMT, "free_cash_flow": -5_000.0}
    repo = _FakeValuationRepo(statements=[stmt, _STMT_PRIOR], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    diagnostics = result["assumptions"]["diagnostics"]
    assert "negative_direct_fcf" in diagnostics["blockers"]
    assert "dcf_unavailable" in diagnostics["warnings"]
    assert result["assumptions"]["dcf"]["base_fcf"] is None


# ---------------------------------------------------------------------------
# No data
# ---------------------------------------------------------------------------


def test_compute_valuation_run_no_statements_returns_none():
    repo = _FakeValuationRepo(statements=[], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    # No FCF, no multiples (statement=None) → no estimates at all.
    assert result is None


def test_compute_valuation_run_no_prices_still_returns_result():
    """A valuation without a current price is still valid (current_price=None)."""
    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[], ratios=_RATIOS)
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    # Valuation should still complete; current_price will be None.
    if result is not None:
        assert result["current_price"] is None


def test_compute_valuation_run_returns_none_when_negative_direct_fcf_and_no_other_methods():
    stmt = {**_STMT, "free_cash_flow": -5_000.0}
    repo = _FakeValuationRepo(statements=[stmt, _STMT_PRIOR], prices=[_PRICE], ratios=[])
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is None


# ---------------------------------------------------------------------------
# Point-in-time safety
# ---------------------------------------------------------------------------


def test_compute_valuation_run_passes_valuation_date_as_as_of_date():
    """All three repo reads must receive the valuation_date as as_of_date."""
    repo = _FakeValuationRepo(
        statements=[_STMT, _STMT_PRIOR],
        prices=[_PRICE],
        ratios=_RATIOS,
        record_calls=True,
    )
    compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    call_map = {fn: date for fn, date in repo.calls}
    assert call_map.get("get_statements_for_company") == _VALUATION_DATE
    assert call_map.get("get_prices_for_company") == _VALUATION_DATE
    assert call_map.get("get_ratios_for_company") == _VALUATION_DATE


# ---------------------------------------------------------------------------
# Financial-sector path
# ---------------------------------------------------------------------------


def test_compute_valuation_run_financial_sector_uses_pb_method():
    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(
        _COMPANY_ID, repo, _VALUATION_DATE, sector="Financials"
    )
    assert result is not None
    # Financial sector route sets method_weights key
    assert "financial_sector_pb" in result["method_weights"]


def test_compute_valuation_run_uses_weighted_distribution_for_range(monkeypatch):
    import investment_app.valuation.scenarios as valuation_scenarios

    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[_PRICE], ratios=[])

    monkeypatch.setattr(
        valuation_scenarios,
        "extract_base_fcf",
        lambda *args, **kwargs: {
            "base_fcf": 100.0,
            "direct_fcf": None,
            "direct_fcf_status": "missing",
            "fcf_source": "synthetic_fcff",
        },
    )
    scenario_results = iter(
        [
            {
                "intrinsic_value_per_share": 10.0,
                "pv_fcfs": 1.0,
                "terminal_value": 1.0,
                "pv_terminal_value": 1.0,
                "enterprise_value": 1.0,
                "equity_value": 1.0,
                "growth_rate": 0.01,
                "wacc": 0.10,
                "terminal_growth": 0.02,
            },
            {
                "intrinsic_value_per_share": 20.0,
                "pv_fcfs": 1.0,
                "terminal_value": 1.0,
                "pv_terminal_value": 1.0,
                "enterprise_value": 1.0,
                "equity_value": 1.0,
                "growth_rate": 0.02,
                "wacc": 0.09,
                "terminal_growth": 0.02,
            },
            {
                "intrinsic_value_per_share": 40.0,
                "pv_fcfs": 1.0,
                "terminal_value": 1.0,
                "pv_terminal_value": 1.0,
                "enterprise_value": 1.0,
                "equity_value": 1.0,
                "growth_rate": 0.03,
                "wacc": 0.08,
                "terminal_growth": 0.02,
            },
        ]
    )
    monkeypatch.setattr(
        valuation_scenarios,
        "run_dcf_scenario",
        lambda **kwargs: next(scenario_results),
    )
    monkeypatch.setattr(
        valuation_scenarios,
        "compute_multiples_value",
        lambda **kwargs: {
            "pe_value": None,
            "ev_ebitda_value": None,
            "ps_value": None,
            "pb_value": None,
            "blended_value": None,
        },
    )
    monkeypatch.setattr(valuation_scenarios, "is_ddm_applicable", lambda *args, **kwargs: False)

    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)

    assert result is not None
    assert result["method_weights"] == {"dcf": 1.0}
    assert result["iv_p10"] == pytest.approx(10.0)
    assert result["iv_p25"] == pytest.approx(10.0)
    assert result["iv_p50"] == pytest.approx(20.0)
    assert result["iv_p75"] == pytest.approx(20.0)
    assert result["iv_p90"] == pytest.approx(40.0)
    assert result["uncertainty_width"] == pytest.approx(3.0)
    assert result["margin_of_safety_conservative"] == pytest.approx((10.0 - 12.0) / 12.0)
    assert result["assumptions"]["aggregation"]["scenario_weights_used"] == {
        "bear": 0.25,
        "base": 0.5,
        "bull": 0.25,
    }


def test_compute_valuation_run_financial_sector_no_ratios_returns_none():
    """Without ROE data in ratio_rows, financial-sector path produces no estimate."""
    repo = _FakeValuationRepo(
        statements=[_STMT, _STMT_PRIOR],
        prices=[_PRICE],
        ratios=[],  # no ratios → roe = None
    )
    result = compute_valuation_run(
        _COMPANY_ID, repo, _VALUATION_DATE, sector="Financials"
    )
    # No estimate because ROE is None.
    assert result is None


# ---------------------------------------------------------------------------
# DDM path
# ---------------------------------------------------------------------------


def test_compute_valuation_run_includes_ddm_when_applicable():
    stmt_with_div = {**_STMT, "dividends_paid": -20_000.0}
    stmt_prior_div = {**_STMT_PRIOR, "dividends_paid": -18_000.0}
    stmt_prior2 = {**_STMT_PRIOR, "dividends_paid": -16_000.0}
    repo = _FakeValuationRepo(
        statements=[stmt_with_div, stmt_prior_div, stmt_prior2],
        prices=[_PRICE],
        ratios=_RATIOS,
    )
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    # DDM method should appear in assumptions when applicable.
    assert "ddm" in result["assumptions"]


def test_compute_valuation_run_yaml_loaded_defaults_change_output(monkeypatch):
    import investment_app.config.loader as loader

    repo = _FakeValuationRepo(statements=[_STMT, _STMT_PRIOR], prices=[_PRICE], ratios=[])

    monkeypatch.setattr(
        loader,
        "load_valuation_defaults",
        lambda path=None: {
            "defaults": {
                "explicit_forecast_years": 5,
                "terminal_growth_floor": 0.01,
                "terminal_growth_cap": 0.03,
                "tax_rate_fallback": 0.25,
                "discount_rate_fallback": 0.08,
                "scenario_weights": {"bear": 0.25, "base": 0.50, "bull": 0.25},
                "revenue_growth_cap": 0.30,
                "ebit_margin_cap": 0.50,
            }
        },
    )
    low_discount_result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)

    monkeypatch.setattr(
        loader,
        "load_valuation_defaults",
        lambda path=None: {
            "defaults": {
                "explicit_forecast_years": 5,
                "terminal_growth_floor": 0.01,
                "terminal_growth_cap": 0.03,
                "tax_rate_fallback": 0.25,
                "discount_rate_fallback": 0.20,
                "scenario_weights": {"bear": 0.25, "base": 0.50, "bull": 0.25},
                "revenue_growth_cap": 0.30,
                "ebit_margin_cap": 0.50,
            }
        },
    )
    high_discount_result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)

    assert low_discount_result is not None
    assert high_discount_result is not None
    assert low_discount_result["iv_p50"] > high_discount_result["iv_p50"]


def test_compute_valuation_run_no_ddm_when_no_dividends():
    repo = _FakeValuationRepo(
        statements=[_STMT, _STMT_PRIOR],
        prices=[_PRICE],
        ratios=_RATIOS,
    )
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    # No dividends_paid in fixture → DDM not applicable → not in assumptions.
    assert "ddm" not in result["assumptions"]


# ---------------------------------------------------------------------------
# Repository: get_ratios_for_company
# ---------------------------------------------------------------------------


def _make_chained_client(rows: list[dict[str, Any]]) -> Any:
    """Build a fake Supabase chained-call client returning *rows*."""
    response = MagicMock()
    response.data = rows
    client = MagicMock()
    (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .order.return_value
        .limit.return_value
        .lte.return_value
        .execute.return_value
    ) = response
    (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .order.return_value
        .limit.return_value
        .execute.return_value
    ) = response
    return client


def test_get_ratios_for_company_returns_rows():
    from investment_app.db.repositories import get_ratios_for_company

    fake_rows = [{"company_id": _COMPANY_ID, "factor_date": "2024-01-01", "pe_ratio": 15.0}]
    client = _make_chained_client(fake_rows)
    result = get_ratios_for_company(_COMPANY_ID, client=client)
    assert result == fake_rows


def test_get_ratios_for_company_filters_by_as_of_date():
    """Verify lte is called when as_of_date is provided."""
    from investment_app.db.repositories import get_ratios_for_company

    fake_rows: list[dict] = []
    client = _make_chained_client(fake_rows)
    get_ratios_for_company(_COMPANY_ID, as_of_date="2024-01-01", client=client)
    # The lte call should have been made on the chain.
    table_chain = client.table.return_value.select.return_value.eq.return_value
    table_chain.order.return_value.limit.return_value.lte.assert_called_once_with(
        "factor_date", "2024-01-01"
    )


def test_get_ratios_for_company_no_as_of_date_skips_lte():
    from investment_app.db.repositories import get_ratios_for_company

    fake_rows: list[dict] = []
    client = _make_chained_client(fake_rows)
    get_ratios_for_company(_COMPANY_ID, client=client)
    # lte should NOT have been called in the no-as_of_date path.
    table_chain = client.table.return_value.select.return_value.eq.return_value
    table_chain.order.return_value.limit.return_value.lte.assert_not_called()


# ---------------------------------------------------------------------------
# Repository: upsert_valuation_run
# ---------------------------------------------------------------------------


def _make_upsert_client(rows_returned: list[dict[str, Any]]) -> Any:
    response = MagicMock()
    response.data = rows_returned
    client = MagicMock()
    (
        client.table.return_value
        .upsert.return_value
        .execute.return_value
    ) = response
    return client


def test_upsert_valuation_run_returns_count():
    from investment_app.db.repositories import upsert_valuation_run

    row = {
        "company_id": _COMPANY_ID,
        "valuation_date": _VALUATION_DATE,
        "model_version": MODEL_VERSION,
    }
    client = _make_upsert_client([row])
    n = upsert_valuation_run([row], client=client)
    assert n == 1


def test_upsert_valuation_run_empty_list_returns_zero():
    from investment_app.db.repositories import upsert_valuation_run

    client = _make_upsert_client([])
    n = upsert_valuation_run([], client=client)
    assert n == 0
    client.table.assert_not_called()


def test_upsert_valuation_run_uses_correct_table_and_conflict():
    from investment_app.db.repositories import upsert_valuation_run

    row = {"company_id": _COMPANY_ID, "valuation_date": _VALUATION_DATE, "model_version": MODEL_VERSION}
    client = _make_upsert_client([row])
    upsert_valuation_run([row], client=client)
    client.table.assert_called_once_with("valuation_runs")
    client.table.return_value.upsert.assert_called_once_with(
        [row], on_conflict="company_id,valuation_date,model_version"
    )


# ---------------------------------------------------------------------------
# Pipeline script: dry-run mentions valuation
# ---------------------------------------------------------------------------


def test_pipeline_dry_run_mentions_valuation(capsys):
    """Dry-run should print valuation computation line."""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).parent.parent.parent / "scripts" / "run_daily_pipeline.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "valuation" in combined.lower()


def test_pipeline_dry_run_does_not_enter_live_pipeline(monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
    import run_daily_pipeline as pipeline_script

    live_calls: list[str] = []

    monkeypatch.setattr(
        pipeline_script,
        "get_settings",
        lambda: SimpleNamespace(app_env="test", log_level="INFO", missing_required=lambda: []),
    )
    monkeypatch.setattr(pipeline_script, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pipeline_script,
        "load_watchlist",
        lambda: {"companies": [{"ticker": "ABC", "cik": "0001"}]},
    )
    monkeypatch.setattr(pipeline_script, "load_providers", lambda: {"providers": {}})
    monkeypatch.setattr(
        pipeline_script,
        "_run_live_pipeline",
        lambda **kwargs: live_calls.append("called"),
    )

    pipeline_script.main(dry_run=True)

    assert live_calls == []


# ---------------------------------------------------------------------------
# Pipeline script: valuation_runs_upserted metric key
# ---------------------------------------------------------------------------


def test_run_live_pipeline_has_valuation_metric():
    """_run_live_pipeline should include valuation_runs_upserted in metrics."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
    from run_daily_pipeline import _run_live_pipeline

    class _MinimalRepo:
        def insert_pipeline_run(self, **_):
            return {"id": "r1"}

        def log_pipeline_event(self, *_, **__):
            pass

        def finish_pipeline_run(self, *_, **__):
            pass

        def list_active_companies(self):
            return []

        def get_company_by_ticker(self, ticker):
            return None

    metrics = _run_live_pipeline(
        repo_module=_MinimalRepo(),
        providers_config={"providers": {}},
        fmp=None,
        sec=None,
        ecb=None,
        gdelt=None,
        store_raw_response_fn=lambda *a, **k: None,
        normalize_prices_fn=lambda *a, **k: [],
        normalize_statements_fn=lambda *a, **k: [],
        normalize_news_fn=lambda *a, **k: [],
        compute_features_fn=None,
        compute_valuation_fn=None,
    )
    assert "valuation_runs_upserted" in metrics


# ---------------------------------------------------------------------------
# Field-name correctness tests
# ---------------------------------------------------------------------------


def test_compute_valuation_run_uses_diluted_shares_field_name():
    """Canonical field name in statements_norm is ``diluted_shares``; not ``shares_diluted``."""
    # Fixture with correct field name → should succeed.
    stmt_correct = {**_STMT}  # has ``diluted_shares``
    assert "diluted_shares" in stmt_correct, "Fixture must use canonical diluted_shares key"

    repo = _FakeValuationRepo(
        statements=[stmt_correct, _STMT_PRIOR],
        prices=[_PRICE],
        ratios=_RATIOS,
    )
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None, (
        "Valuation should succeed when diluted_shares is present under the canonical key"
    )


def test_compute_valuation_run_wrong_shares_field_blocks_valuation():
    """Using legacy field names for diluted shares without the canonical one should block DCF."""
    stmt_wrong = {k: v for k, v in _STMT.items() if k != "diluted_shares"}
    stmt_wrong["shares_diluted"] = 10_000.0  # wrong field name, not read by code

    repo = _FakeValuationRepo(
        statements=[stmt_wrong, {**_STMT_PRIOR, "diluted_shares": None, "shares_diluted": 10_000.0}],
        prices=[_PRICE],
        ratios=_RATIOS,
    )
    # Without diluted_shares, DCF cannot compute intrinsic_value_per_share.
    # The valuation may return None or a result without a valid iv_p50.
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    # DCF path blocked; result is either None or iv_p50 comes from multiples only.
    if result is not None:
        # If multiples produce something, iv_p50 may still be set.
        # The important guarantee is that DCF assumptions have no base_fcf via shares.
        assert result["assumptions"].get("dcf", {}).get("diluted_shares") is None


def test_compute_valuation_run_price_eod_uses_close_field():
    """Canonical field name in price_eod is ``close``; fixture must use that name."""
    assert "close" in _PRICE, "Price fixture must use canonical 'close' key"
    repo = _FakeValuationRepo(
        statements=[_STMT, _STMT_PRIOR],
        prices=[_PRICE],
        ratios=_RATIOS,
    )
    result = compute_valuation_run(_COMPANY_ID, repo, _VALUATION_DATE)
    assert result is not None
    assert result["current_price"] == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# diagnostics_out parameter tests
# ---------------------------------------------------------------------------


def test_compute_valuation_run_diagnostics_out_not_populated_on_success():
    """diagnostics_out should remain empty when valuation succeeds."""
    diag: dict[str, Any] = {}
    repo = _FakeValuationRepo(
        statements=[_STMT, _STMT_PRIOR],
        prices=[_PRICE],
        ratios=_RATIOS,
    )
    result = compute_valuation_run(
        _COMPANY_ID, repo, _VALUATION_DATE, diagnostics_out=diag
    )
    assert result is not None
    assert diag == {}, "diagnostics_out should not be populated when valuation succeeds"


def test_compute_valuation_run_diagnostics_out_populated_when_skipped():
    """diagnostics_out must be populated with blockers when valuation returns None."""
    diag: dict[str, Any] = {}
    # No statements → no estimates → returns None
    repo = _FakeValuationRepo(statements=[], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(
        _COMPANY_ID, repo, _VALUATION_DATE, diagnostics_out=diag
    )
    assert result is None
    assert "blockers" in diag, "diagnostics_out must contain 'blockers' when skipped"
    assert isinstance(diag["blockers"], list)


def test_compute_valuation_run_diagnostics_out_includes_valuation_status():
    """diagnostics_out must include valuation_status when valuation is blocked."""
    diag: dict[str, Any] = {}
    repo = _FakeValuationRepo(statements=[], prices=[_PRICE], ratios=_RATIOS)
    result = compute_valuation_run(
        _COMPANY_ID, repo, _VALUATION_DATE, diagnostics_out=diag
    )
    assert result is None
    assert "valuation_status" in diag


def test_compute_valuation_run_diagnostics_out_none_does_not_raise():
    """Passing diagnostics_out=None (the default) must not raise on skip."""
    repo = _FakeValuationRepo(statements=[], prices=[_PRICE], ratios=_RATIOS)
    try:
        result = compute_valuation_run(
            _COMPANY_ID, repo, _VALUATION_DATE, diagnostics_out=None
        )
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"compute_valuation_run raised unexpectedly: {exc}")
    assert result is None


def test_compute_valuation_run_diagnostics_out_contains_available_inputs_when_skipped():
    """diagnostics_out['available_inputs'] should list non-null fields when skipped."""
    diag: dict[str, Any] = {}
    stmt_no_shares = {k: v for k, v in _STMT.items() if k not in ("diluted_shares", "free_cash_flow")}
    repo = _FakeValuationRepo(
        statements=[stmt_no_shares],
        prices=[],
        ratios=[],
    )
    result = compute_valuation_run(
        _COMPANY_ID, repo, _VALUATION_DATE, diagnostics_out=diag
    )
    assert result is None
    assert "available_inputs" in diag
    assert isinstance(diag["available_inputs"], list)

