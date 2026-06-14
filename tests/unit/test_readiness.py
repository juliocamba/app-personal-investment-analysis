"""Unit tests for Phase 10C.1 readiness/provider classification."""
from __future__ import annotations

from investment_app.readiness import classify_company_readiness, detect_provider_mix


def _company(**overrides):
    base = {
        "id": "cid-001",
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "country": "US",
        "currency": "USD",
        "company_type": "non_financial",
        "metadata": {},
    }
    base.update(overrides)
    return base


def _price(provider: str = "fmp", close: float = 100.0):
    return {
        "provider": provider,
        "price_date": "2025-01-01",
        "close": close,
    }


def _statement(year: int, *, source: str = "fmp", diluted_shares: float = 1000.0,
               free_cash_flow: float | None = 150.0, cfo: float | None = 200.0,
               capex: float | None = -50.0):
    return {
        "fiscal_year": year,
        "fiscal_period": "annual",
        "period_end_date": f"{year}-09-30",
        "source": source,
        "diluted_shares": diluted_shares,
        "free_cash_flow": free_cash_flow,
        "cfo": cfo,
        "capex": capex,
    }


def _valuation(status: str):
    return {
        "id": "val-001",
        "valuation_date": "2025-01-01",
        "assumptions": {
            "diagnostics": {
                "valuation_status": status,
            }
        },
    }


def _signal(signal_date: str = "2025-01-01"):
    return {
        "id": "sig-001",
        "signal_date": signal_date,
    }


def test_fmp_only_complete_company_is_analysis_ready() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[_statement(2024), _statement(2023)],
        filing_rows=[{"source": "sec_edgar", "filing_date": "2025-01-01"}],
        latest_valuation_row=_valuation("ok"),
        fx_provider="ecb",
    )

    assert result["readiness_status"] == "analysis_ready"
    assert result["provider_mix"] == "primary_only"
    assert result["can_run_valuation"] is True
    assert result["can_run_signal"] is True
    assert result["reason_codes"] == ["valuation_ready"]


def test_sec_fundamentals_and_twelve_price_can_be_analysis_ready() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("twelve_data"),
        statement_rows=[
            _statement(2024, source="sec_edgar"),
            _statement(2023, source="sec_edgar"),
        ],
        filing_rows=[{"source": "sec_edgar", "filing_date": "2025-01-01"}],
    )

    assert result["readiness_status"] == "analysis_ready"
    assert result["provider_map"]["price"] == "twelve_data"
    assert result["provider_map"]["fundamentals"] == "sec_edgar"


def test_asml_like_non_us_price_only_company_is_tracking_only() -> None:
    result = classify_company_readiness(
        _company(ticker="ASML", name="ASML Holding", country="NL", cik=""),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[],
        filing_rows=[],
    )

    assert result["readiness_status"] == "tracking_only"
    assert result["provider_mix"] == "price_only"
    assert result["reason_codes"] == [
        "missing_supported_fundamentals_path",
        "non_us_fundamentals_not_supported",
        "provider_limited",
    ]


def test_missing_price_with_fundamentals_is_partial_analysis() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=None,
        statement_rows=[_statement(2024), _statement(2023)],
        latest_valuation_row=_valuation("partial"),
    )

    assert result["readiness_status"] == "partial_analysis"
    assert result["limiting_domain"] == "price"
    assert result["reason_codes"] == ["missing_price", "valuation_partial"]


def test_unsupported_instrument_is_classified_explicitly() -> None:
    result = classify_company_readiness(
        _company(metadata={"instrument_type": "etf"}),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[_statement(2024), _statement(2023)],
    )

    assert result["readiness_status"] == "unsupported_for_analysis"
    assert result["reason_codes"] == ["unsupported_instrument"]
    assert result["can_run_valuation"] is False


def test_mixed_provider_detection_is_deterministic() -> None:
    provider_mix = detect_provider_mix(
        {
            "profile": "fmp",
            "price": "twelve_data",
            "fundamentals": "sec_edgar",
            "filings": "sec_edgar",
            "fx": "ecb",
        }
    )

    assert provider_mix == "mixed_sources"


def test_reason_code_order_is_deterministic() -> None:
    result = classify_company_readiness(
        _company(country="US", cik="0000320193"),
        profile_provider="fmp",
        latest_price_row=None,
        statement_rows=[
            _statement(2024, diluted_shares=0.0, free_cash_flow=None, cfo=None, capex=None),
        ],
        latest_valuation_row=_valuation("partial"),
    )

    assert result["reason_codes"] == [
        "missing_price",
        "missing_min_statement_history",
        "missing_diluted_shares",
        "missing_fcf_path",
        "valuation_partial",
    ]

    result_again = classify_company_readiness(
        _company(country="US", cik="0000320193"),
        profile_provider="fmp",
        latest_price_row=None,
        statement_rows=[
            _statement(2024, diluted_shares=0.0, free_cash_flow=None, cfo=None, capex=None),
        ],
        latest_valuation_row=_valuation("partial"),
    )
    assert result_again["reason_codes"] == result["reason_codes"]


# ---------------------------------------------------------------------------
# Issue 1: FCF viability and blocked valuation
# ---------------------------------------------------------------------------

def test_blocked_valuation_is_not_analysis_ready() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[_statement(2024), _statement(2023)],
        latest_valuation_row=_valuation("blocked"),
    )

    assert result["readiness_status"] != "analysis_ready"
    assert result["readiness_status"] == "partial_analysis"
    assert "valuation_blocked" in result["reason_codes"]


def test_zero_fcf_is_not_analysis_ready() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[
            _statement(2024, free_cash_flow=0.0, cfo=None, capex=None),
            _statement(2023, free_cash_flow=0.0, cfo=None, capex=None),
        ],
    )

    assert result["readiness_status"] != "analysis_ready"
    assert result["readiness_status"] == "partial_analysis"
    assert "non_viable_fcf" in result["reason_codes"]


def test_negative_fcf_is_not_analysis_ready() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[
            _statement(2024, free_cash_flow=-80.0, cfo=None, capex=None),
            _statement(2023, free_cash_flow=-20.0, cfo=None, capex=None),
        ],
    )

    assert result["readiness_status"] != "analysis_ready"
    assert result["readiness_status"] == "partial_analysis"
    assert "non_viable_fcf" in result["reason_codes"]


def test_positive_fcf_with_complete_inputs_is_analysis_ready() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[
            _statement(2024, free_cash_flow=200.0),
            _statement(2023, free_cash_flow=150.0),
        ],
    )

    assert result["readiness_status"] == "analysis_ready"
    assert "non_viable_fcf" not in result["reason_codes"]


# ---------------------------------------------------------------------------
# Issue 2: company_type must not override schema-valid values as unsupported
# ---------------------------------------------------------------------------

def test_reit_company_type_is_not_unsupported() -> None:
    result = classify_company_readiness(
        _company(company_type="reit"),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[_statement(2024), _statement(2023)],
    )

    assert result["readiness_status"] != "unsupported_for_analysis"
    assert "unsupported_instrument" not in result["reason_codes"]


def test_statement_age_days_at_or_below_540_does_not_trigger_stale_fundamentals() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[
            _statement(2024),
            _statement(2023),
        ],
        latest_valuation_row={"valuation_date": "2026-03-24", "assumptions": {}},
    )

    assert result["statement_age_days"] == 540
    assert "stale_fundamentals" not in result["reason_codes"]
    assert result["can_run_valuation"] is True
    assert result["can_run_signal"] is True


def test_statement_age_days_above_540_blocks_valuation_and_signal() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[
            _statement(2024),
            _statement(2023),
        ],
        latest_valuation_row={"valuation_date": "2026-03-25", "assumptions": {}},
        latest_signal_row=_signal("2026-03-25"),
    )

    assert result["statement_age_days"] == 541
    assert result["readiness_status"] == "tracking_only"
    assert result["can_run_valuation"] is False
    assert result["can_run_signal"] is False
    assert result["limiting_domain"] == "fundamentals"


def test_stale_fundamentals_still_block_with_recent_price_if_signal_is_stale() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row={
            "provider": "fmp",
            "price_date": "2025-01-01",
            "close": 101.0,
        },
        statement_rows=[
            _statement(2024),
            _statement(2023),
        ],
        latest_valuation_row={"valuation_date": "2026-03-25", "assumptions": {}},
        latest_signal_row=_signal("2026-03-25"),
    )

    assert result["statement_age_days"] == 541
    assert result["readiness_status"] == "tracking_only"
    assert "stale_fundamentals" in result["reason_codes"]
    assert result["can_run_valuation"] is False
    assert result["can_run_signal"] is False


def test_missing_anchor_dates_keeps_statement_age_none() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=None,
        statement_rows=[
            _statement(2024),
            _statement(2023),
        ],
        latest_valuation_row=None,
        latest_signal_row=None,
    )

    assert result["statement_age_days"] is None
    assert "stale_fundamentals" not in result["reason_codes"]


def test_missing_latest_statement_date_keeps_existing_no_statements_behavior() -> None:
    result = classify_company_readiness(
        _company(ticker="ASML", name="ASML Holding", country="NL", cik=""),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[],
        filing_rows=[],
    )

    assert result["statement_age_days"] is None
    assert "stale_fundamentals" not in result["reason_codes"]
    assert result["readiness_status"] == "tracking_only"


def test_stale_fundamentals_reason_code_present_when_triggered() -> None:
    result = classify_company_readiness(
        _company(),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[_statement(2024), _statement(2023)],
        latest_signal_row=_signal("2026-03-25"),
    )

    assert "stale_fundamentals" in result["reason_codes"]


def test_utility_company_type_is_not_unsupported() -> None:
    result = classify_company_readiness(
        _company(company_type="utility"),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[_statement(2024), _statement(2023)],
    )

    assert result["readiness_status"] != "unsupported_for_analysis"
    assert "unsupported_instrument" not in result["reason_codes"]


def test_security_type_bond_metadata_is_unsupported() -> None:
    result = classify_company_readiness(
        _company(metadata={"security_type": "bond"}),
        profile_provider="fmp",
        latest_price_row=_price("fmp"),
        statement_rows=[_statement(2024), _statement(2023)],
    )

    assert result["readiness_status"] == "unsupported_for_analysis"
    assert "unsupported_instrument" in result["reason_codes"]