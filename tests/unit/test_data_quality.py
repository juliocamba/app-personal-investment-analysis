from __future__ import annotations

from investment_app.data_quality import (
    FUNDAMENTALS_COMPARISON_CRITICAL,
    FUNDAMENTALS_COMPARISON_NOT_COMPARABLE,
    FUNDAMENTALS_COMPARISON_OK,
    FUNDAMENTALS_COMPARISON_WARNING,
    FUNDAMENTALS_DISCREPANCY_CRITICAL_THRESHOLD,
    FUNDAMENTALS_DISCREPANCY_WARNING_THRESHOLD,
    WARNING_CODE_FUNDAMENTALS_PROVIDER_DISCREPANCY,
    WARNING_CODE_FUNDAMENTALS_PROVIDER_OVERLAP_MISSING,
    WARNING_CODE_INCOMPLETE_STATEMENT_SET,
    WARNING_CODE_INSUFFICIENT_PERIOD_COVERAGE,
    WARNING_CODE_MISSING_KEY_FIELDS,
    WARNING_CODE_NO_STATEMENTS_AVAILABLE,
    PRICE_DIVERGENCE_CRITICAL_THRESHOLD,
    PRICE_DIVERGENCE_WARNING_THRESHOLD,
    PRICE_VALIDATION_CRITICAL,
    PRICE_VALIDATION_NOT_COMPARABLE,
    PRICE_VALIDATION_OK,
    PRICE_VALIDATION_WARNING,
    WARNING_CODE_PRICE_DIVERGENCE_CRITICAL,
    WARNING_CODE_PRICE_DIVERGENCE_WARNING,
    WARNING_CODE_PRICE_NOT_COMPARABLE,
    build_data_quality_snapshot_row,
    build_price_validation_payload,
    build_price_validation_warning_codes,
    calculate_price_divergence_pct,
    calculate_fundamentals_relative_difference_pct,
    classify_price_divergence,
    classify_fundamentals_relative_difference,
    compare_latest_overlapping_provider_prices,
    compare_provider_prices,
    evaluate_fundamentals_provider_overlap,
    evaluate_statement_completeness,
    extract_price_value,
    find_latest_overlapping_provider_prices,
)


def test_extract_price_value_prefers_close_then_adjusted_close() -> None:
    assert extract_price_value({"close": 101.25}) == 101.25
    assert extract_price_value({"close": None, "adjusted_close": 99.5}) == 99.5


def test_extract_price_value_rejects_zero_negative_and_invalid() -> None:
    assert extract_price_value({"close": 0}) is None
    assert extract_price_value({"close": -1}) is None
    assert extract_price_value({"close": "bad"}) is None
    assert extract_price_value(None) is None


def test_calculate_price_divergence_pct_uses_reference_price() -> None:
    assert calculate_price_divergence_pct(100, 101) == 0.01
    assert calculate_price_divergence_pct(100, 95) == 0.05


def test_calculate_price_divergence_pct_returns_none_for_missing_or_invalid() -> None:
    assert calculate_price_divergence_pct(None, 100) is None
    assert calculate_price_divergence_pct(100, None) is None
    assert calculate_price_divergence_pct(0, 100) is None
    assert calculate_price_divergence_pct(100, 0) is None
    assert calculate_price_divergence_pct("x", 100) is None


def test_classify_price_divergence_thresholds_are_conservative() -> None:
    assert classify_price_divergence(None) == PRICE_VALIDATION_NOT_COMPARABLE
    assert classify_price_divergence(PRICE_DIVERGENCE_WARNING_THRESHOLD) == PRICE_VALIDATION_OK
    assert classify_price_divergence(PRICE_DIVERGENCE_WARNING_THRESHOLD + 0.0001) == PRICE_VALIDATION_WARNING
    assert classify_price_divergence(PRICE_DIVERGENCE_CRITICAL_THRESHOLD) == PRICE_VALIDATION_WARNING
    assert classify_price_divergence(PRICE_DIVERGENCE_CRITICAL_THRESHOLD + 0.0001) == PRICE_VALIDATION_CRITICAL


def test_find_latest_overlapping_provider_prices_returns_latest_overlap() -> None:
    rows = [
        {"price_date": "2024-01-03", "provider": "fmp", "close": 101.0},
        {"price_date": "2024-01-02", "provider": "fmp", "close": 100.0},
        {"price_date": "2024-01-02", "provider": "twelve_data", "close": 99.5},
        {"price_date": "2024-01-01", "provider": "fmp", "close": 98.0},
        {"price_date": "2024-01-01", "provider": "twelve_data", "close": 98.1},
    ]
    fmp_row, twelve_row = find_latest_overlapping_provider_prices(rows)
    assert fmp_row is not None
    assert twelve_row is not None
    assert fmp_row["price_date"] == "2024-01-02"
    assert twelve_row["price_date"] == "2024-01-02"


def test_find_latest_overlapping_provider_prices_returns_none_without_both_sources() -> None:
    rows = [
        {"price_date": "2024-01-03", "provider": "fmp", "close": 101.0},
        {"price_date": "2024-01-02", "provider": "fmp", "close": 100.0},
    ]
    assert find_latest_overlapping_provider_prices(rows) == (None, None)


def test_compare_provider_prices_ok_warning_critical_and_not_comparable() -> None:
    ok = compare_provider_prices(
        {"price_date": "2024-01-02", "close": 100.0},
        {"price_date": "2024-01-02", "close": 100.5},
    )
    assert ok["status"] == PRICE_VALIDATION_OK

    warning = compare_provider_prices(
        {"price_date": "2024-01-02", "close": 100.0},
        {"price_date": "2024-01-02", "close": 101.5},
    )
    assert warning["status"] == PRICE_VALIDATION_WARNING

    critical = compare_provider_prices(
        {"price_date": "2024-01-02", "close": 100.0},
        {"price_date": "2024-01-02", "close": 106.0},
    )
    assert critical["status"] == PRICE_VALIDATION_CRITICAL

    missing = compare_provider_prices(
        {"price_date": "2024-01-02", "close": 100.0},
        None,
    )
    assert missing["status"] == PRICE_VALIDATION_NOT_COMPARABLE


def test_compare_latest_overlapping_provider_prices_skips_non_overlapping_latest_rows() -> None:
    rows = [
        {"price_date": "2024-01-03", "provider": "fmp", "close": 102.0},
        {"price_date": "2024-01-02", "provider": "fmp", "close": 100.0},
        {"price_date": "2024-01-02", "provider": "twelve_data", "close": 101.2},
    ]
    result = compare_latest_overlapping_provider_prices(rows)
    assert result["comparison_date"] == "2024-01-02"
    assert result["status"] == PRICE_VALIDATION_WARNING


def test_build_price_validation_payload_is_safe_and_compact() -> None:
    result = {
        "status": PRICE_VALIDATION_WARNING,
        "comparison_date": "2024-01-02",
        "reference_provider": "fmp",
        "comparison_provider": "twelve_data",
        "reference_price": 100.0,
        "comparison_price": 101.25,
        "divergence_pct": 0.0125,
    }
    payload = build_price_validation_payload(ticker="AAPL", result=result)

    assert payload["ticker"] == "AAPL"
    assert payload["event"] == "price_cross_provider_validation"
    assert payload["status"] == PRICE_VALIDATION_WARNING
    assert payload["divergence_pct"] == 0.0125
    assert "reference_price" not in payload
    assert "comparison_price" not in payload
    lowered = str(payload).lower()
    for forbidden in ("apikey", "api_key", "bearer", "supabase", "financialmodelingprep", "https://"):
        assert forbidden not in lowered


def test_build_price_validation_warning_codes_match_status() -> None:
    assert build_price_validation_warning_codes(PRICE_VALIDATION_OK) == []
    assert build_price_validation_warning_codes(PRICE_VALIDATION_WARNING) == [
        WARNING_CODE_PRICE_DIVERGENCE_WARNING
    ]
    assert build_price_validation_warning_codes(PRICE_VALIDATION_CRITICAL) == [
        WARNING_CODE_PRICE_DIVERGENCE_CRITICAL
    ]
    assert build_price_validation_warning_codes(PRICE_VALIDATION_NOT_COMPARABLE) == [
        WARNING_CODE_PRICE_NOT_COMPARABLE
    ]


def test_build_data_quality_snapshot_row_is_sanitized() -> None:
    row = build_data_quality_snapshot_row(
        company_id="c1",
        snapshot_date="2024-01-02",
        result={
            "status": PRICE_VALIDATION_WARNING,
            "comparison_date": "2024-01-02",
            "reference_provider": "fmp",
            "comparison_provider": "twelve_data",
            "reference_price": 100.0,
            "comparison_price": 101.5,
            "divergence_pct": 0.015,
        },
    )

    assert row["company_id"] == "c1"
    assert row["snapshot_date"] == "2024-01-02"
    assert row["price_validation_status"] == PRICE_VALIDATION_WARNING
    assert row["warning_codes"] == [WARNING_CODE_PRICE_DIVERGENCE_WARNING]
    assert row["price_divergence_pct"] == 0.015
    assert row["details"]["price_validation"]["comparison_date"] == "2024-01-02"
    assert "reference_price" not in str(row["details"]).lower()
    assert "comparison_price" not in str(row["details"]).lower()


def test_evaluate_statement_completeness_no_statements_available() -> None:
    result = evaluate_statement_completeness([])

    assert result["warning_codes"] == [WARNING_CODE_NO_STATEMENTS_AVAILABLE]
    assert result["details"]["annual_periods_found"] == 0
    assert result["details"]["missing_statement_domains"] == ["income", "cashflow", "balance"]


def test_evaluate_statement_completeness_detects_partial_statement_set_and_missing_fields() -> None:
    result = evaluate_statement_completeness(
        [
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "fmp",
                "revenue": 100.0,
                "net_income": None,
                "cfo": None,
                "capex": None,
                "total_assets": None,
                "total_liabilities": None,
                "total_debt": None,
                "total_equity": None,
                "diluted_shares": None,
            }
        ]
    )

    assert result["details"]["status"] == "warning"
    assert WARNING_CODE_INCOMPLETE_STATEMENT_SET in result["warning_codes"]
    assert WARNING_CODE_MISSING_KEY_FIELDS in result["warning_codes"]
    assert WARNING_CODE_INSUFFICIENT_PERIOD_COVERAGE in result["warning_codes"]
    assert "cashflow" in result["details"]["missing_statement_domains"]
    assert "balance" in result["details"]["missing_statement_domains"]
    assert "net_income" in result["details"]["missing_fields"]
    assert "total_liabilities_or_debt" in result["details"]["missing_fields"]
    assert result["details"]["missing_optional_fields"] == ["diluted_shares"]


def test_evaluate_statement_completeness_ok_when_latest_annual_has_required_fields_and_coverage() -> None:
    result = evaluate_statement_completeness(
        [
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "fmp",
                "revenue": 100.0,
                "net_income": 10.0,
                "cfo": 20.0,
                "capex": -5.0,
                "total_assets": 200.0,
                "total_liabilities": 90.0,
                "total_equity": 110.0,
                "diluted_shares": None,
            },
            {
                "fiscal_year": 2023,
                "fiscal_period": "annual",
                "period_end_date": "2023-12-31",
                "source": "fmp",
                "revenue": 90.0,
                "net_income": 9.0,
                "cfo": 18.0,
                "capex": -4.0,
                "total_assets": 180.0,
                "total_liabilities": 80.0,
                "total_equity": 100.0,
            },
        ]
    )

    assert result["warning_codes"] == []
    assert result["details"]["status"] == "ok"
    assert result["details"]["annual_periods_found"] == 2
    assert result["details"]["missing_fields"] == []
    assert result["details"]["missing_statement_domains"] == []


def test_build_data_quality_snapshot_row_merges_statement_completeness_safely() -> None:
    row = build_data_quality_snapshot_row(
        company_id="c1",
        snapshot_date="2024-01-02",
        result={
            "status": PRICE_VALIDATION_NOT_COMPARABLE,
            "comparison_date": None,
            "reference_provider": "fmp",
            "comparison_provider": "twelve_data",
            "divergence_pct": None,
            "reference_price": 100.0,
            "comparison_price": None,
        },
        statement_diagnostics={
            "warning_codes": [WARNING_CODE_NO_STATEMENTS_AVAILABLE],
            "details": {
                "status": "warning",
                "annual_periods_found": 0,
                "missing_fields": [],
                "missing_statement_domains": ["income", "cashflow", "balance"],
            },
        },
    )

    assert row["warning_codes"] == [
        WARNING_CODE_PRICE_NOT_COMPARABLE,
        WARNING_CODE_NO_STATEMENTS_AVAILABLE,
    ]
    assert row["details"]["statement_completeness"]["annual_periods_found"] == 0
    lowered = str(row["details"]).lower()
    for forbidden in ("reference_price", "comparison_price", "apikey", "api_key", "https://"):
        assert forbidden not in lowered


def test_calculate_fundamentals_relative_difference_pct_is_symmetric_and_handles_zero() -> None:
    assert calculate_fundamentals_relative_difference_pct(100, 100) == 0.0
    assert calculate_fundamentals_relative_difference_pct(100, 95) == 0.05
    assert calculate_fundamentals_relative_difference_pct(-100, -80) == 0.2
    assert calculate_fundamentals_relative_difference_pct(0, 0) == 0.0
    assert calculate_fundamentals_relative_difference_pct(None, 100) is None


def test_classify_fundamentals_relative_difference_uses_conservative_thresholds() -> None:
    assert classify_fundamentals_relative_difference(None) == FUNDAMENTALS_COMPARISON_NOT_COMPARABLE
    assert classify_fundamentals_relative_difference(
        FUNDAMENTALS_DISCREPANCY_WARNING_THRESHOLD
    ) == FUNDAMENTALS_COMPARISON_OK
    assert classify_fundamentals_relative_difference(
        FUNDAMENTALS_DISCREPANCY_WARNING_THRESHOLD + 0.0001
    ) == FUNDAMENTALS_COMPARISON_WARNING
    assert classify_fundamentals_relative_difference(
        FUNDAMENTALS_DISCREPANCY_CRITICAL_THRESHOLD
    ) == FUNDAMENTALS_COMPARISON_WARNING
    assert classify_fundamentals_relative_difference(
        FUNDAMENTALS_DISCREPANCY_CRITICAL_THRESHOLD + 0.0001
    ) == FUNDAMENTALS_COMPARISON_CRITICAL


def test_evaluate_fundamentals_provider_overlap_no_overlap() -> None:
    result = evaluate_fundamentals_provider_overlap(
        [
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "fmp",
                "revenue": 100.0,
            }
        ]
    )

    assert result["warning_codes"] == [WARNING_CODE_FUNDAMENTALS_PROVIDER_OVERLAP_MISSING]
    assert result["details"]["overlapping_period_count"] == 0
    assert result["details"]["discrepancy_level"] == FUNDAMENTALS_COMPARISON_NOT_COMPARABLE


def test_evaluate_fundamentals_provider_overlap_missing_field_overlap_is_not_comparable() -> None:
    result = evaluate_fundamentals_provider_overlap(
        [
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "fmp",
                "revenue": None,
                "net_income": None,
                "total_assets": None,
                "total_liabilities": None,
                "total_equity": None,
            },
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "sec_edgar",
                "revenue": None,
                "net_income": None,
                "total_assets": None,
                "total_liabilities": None,
                "total_equity": None,
            },
        ]
    )

    assert result["warning_codes"] == [WARNING_CODE_FUNDAMENTALS_PROVIDER_OVERLAP_MISSING]
    assert result["details"]["overlapping_period_count"] == 1
    assert result["details"]["compared_fields"] == []
    assert result["details"]["discrepancy_level"] == FUNDAMENTALS_COMPARISON_NOT_COMPARABLE


def test_evaluate_fundamentals_provider_overlap_ok_when_rows_match() -> None:
    result = evaluate_fundamentals_provider_overlap(
        [
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "fmp",
                "revenue": 100.0,
                "net_income": 20.0,
                "total_assets": 250.0,
                "total_liabilities": 120.0,
                "total_equity": 130.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "sec_edgar",
                "revenue": 100.0,
                "net_income": 20.0,
                "total_assets": 250.0,
                "total_liabilities": 120.0,
                "total_equity": 130.0,
            },
        ]
    )

    assert result["warning_codes"] == []
    assert result["details"]["overlapping_period_count"] == 1
    assert result["details"]["discrepancy_level"] == FUNDAMENTALS_COMPARISON_OK
    assert result["details"]["discrepant_fields"] == []


def test_evaluate_fundamentals_provider_overlap_detects_material_discrepancy() -> None:
    result = evaluate_fundamentals_provider_overlap(
        [
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "fmp",
                "revenue": 100.0,
                "net_income": 20.0,
                "total_assets": 250.0,
                "total_liabilities": 120.0,
                "total_equity": 130.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_period": "annual",
                "period_end_date": "2024-12-31",
                "source": "sec_edgar",
                "revenue": 118.0,
                "net_income": 20.0,
                "total_assets": 250.0,
                "total_liabilities": 120.0,
                "total_equity": 100.0,
            },
        ]
    )

    assert result["warning_codes"] == [WARNING_CODE_FUNDAMENTALS_PROVIDER_DISCREPANCY]
    assert result["details"]["overlapping_period_count"] == 1
    assert result["details"]["discrepancy_level"] == FUNDAMENTALS_COMPARISON_CRITICAL
    assert "revenue" in result["details"]["discrepant_fields"]
    assert "equity" in result["details"]["discrepant_fields"]
    assert result["details"]["max_relative_difference_pct"] == 0.230769


def test_build_data_quality_snapshot_row_merges_fundamentals_comparison_safely() -> None:
    row = build_data_quality_snapshot_row(
        company_id="c1",
        snapshot_date="2024-01-02",
        result={
            "status": PRICE_VALIDATION_OK,
            "comparison_date": "2024-01-02",
            "reference_provider": "fmp",
            "comparison_provider": "twelve_data",
            "divergence_pct": 0.0,
        },
        fundamentals_diagnostics={
            "warning_codes": [WARNING_CODE_FUNDAMENTALS_PROVIDER_DISCREPANCY],
            "details": {
                "overlapping_period_count": 1,
                "compared_fields": ["revenue"],
                "discrepant_fields": ["revenue"],
                "max_relative_difference_pct": 0.18,
                "discrepancy_level": FUNDAMENTALS_COMPARISON_CRITICAL,
            },
        },
    )

    assert row["warning_codes"] == [WARNING_CODE_FUNDAMENTALS_PROVIDER_DISCREPANCY]
    assert row["details"]["fundamentals_provider_comparison"]["discrepancy_level"] == (
        FUNDAMENTALS_COMPARISON_CRITICAL
    )
    lowered = str(row["details"]).lower()
    for forbidden in ("payload", "apikey", "api_key", "https://", "100.0"):
        assert forbidden not in lowered
