"""Financial statement normalisation.

Converts FMP income-statement, balance-sheet, and cash-flow payloads into
canonical ``statements_norm`` rows.

Mapping strategy: extract the most common FMP field names and map them to the
canonical schema columns.  Unknown or missing fields are left as ``None``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fiscal_period(fmp_period: str | None) -> str:
    """Normalise FMP period strings to 'annual' or 'Q1'/'Q2'/'Q3'/'Q4'."""
    if not fmp_period:
        return "annual"
    upper = fmp_period.upper()
    if upper in {"FY", "ANNUAL"}:
        return "annual"
    if upper in {"Q1", "Q2", "Q3", "Q4"}:
        return upper
    return fmp_period


def normalize_fmp_statements(
    income_payload: dict[str, Any] | list[Any] | None,
    balance_payload: dict[str, Any] | list[Any] | None,
    cashflow_payload: dict[str, Any] | list[Any] | None,
    company_id: str,
    ticker: str,
    currency: str = "USD",
) -> list[dict[str, Any]]:
    """Merge FMP income / balance / cash-flow statements into ``statements_norm`` rows.

    Each FMP period present in the income statement is used as the key.
    Balance sheet and cash flow data are merged by matching fiscal year + period.
    Returns one row per (fiscal_year, fiscal_period).

    Compatible with both:
    - FMP *stable* API (uses ``fiscalYear`` field, ``calendarYear`` absent / empty)
    - FMP *legacy v3* API (uses ``calendarYear`` field)
    Year extraction falls back to ``date[:4]`` when neither field is present.
    """
    # Parse income statement periods as the primary source.
    income_list: list[dict[str, Any]] = (
        income_payload if isinstance(income_payload, list) else []
    )
    balance_map: dict[tuple[str, str], dict[str, Any]] = {}
    cashflow_map: dict[tuple[str, str], dict[str, Any]] = {}

    for item in (balance_payload if isinstance(balance_payload, list) else []):
        year_str = str(item.get("fiscalYear") or item.get("calendarYear") or item.get("date", "")[:4])
        key = (year_str, str(item.get("period", "")))
        balance_map[key] = item

    for item in (cashflow_payload if isinstance(cashflow_payload, list) else []):
        year_str = str(item.get("fiscalYear") or item.get("calendarYear") or item.get("date", "")[:4])
        key = (year_str, str(item.get("period", "")))
        cashflow_map[key] = item

    rows: list[dict[str, Any]] = []
    for inc in income_list:
        year_str = str(inc.get("fiscalYear") or inc.get("calendarYear") or inc.get("date", "")[:4])
        period_str = _fiscal_period(inc.get("period"))
        period_end = inc.get("date")
        if not year_str or not period_end:
            continue

        key = (year_str, inc.get("period", ""))
        bal = balance_map.get(key, {})
        cf = cashflow_map.get(key, {})

        try:
            fiscal_year = int(year_str)
        except ValueError:
            continue

        row: dict[str, Any] = {
            "company_id": company_id,
            "fiscal_year": fiscal_year,
            "fiscal_period": period_str,
            "period_end_date": period_end,
            "currency": currency,
            "source": "fmp",
            "restated_flag": False,
            # Income statement fields
            "revenue": _safe_float(inc.get("revenue")),
            "gross_profit": _safe_float(inc.get("grossProfit")),
            "operating_income": _safe_float(inc.get("operatingIncome")),
            "ebit": _safe_float(inc.get("ebit") or inc.get("operatingIncome")),
            "ebitda": _safe_float(inc.get("ebitda")),
            "net_income": _safe_float(inc.get("netIncome")),
            # Cash flow fields
            "cfo": _safe_float(cf.get("operatingCashFlow")),
            "capex": _safe_float(cf.get("capitalExpenditure")),
            "free_cash_flow": _safe_float(cf.get("freeCashFlow")),
            "depreciation_amortization": _safe_float(
                cf.get("depreciationAndAmortization")
            ),
            "stock_based_compensation": _safe_float(
                cf.get("stockBasedCompensation")
            ),
            # Balance sheet fields
            "cash_and_equivalents": _safe_float(
                bal.get("cashAndCashEquivalents")
            ),
            "total_debt": _safe_float(bal.get("totalDebt")),
            "lease_liabilities": _safe_float(
                bal.get("capitalLeaseObligations")
            ),
            "minority_interest": _safe_float(bal.get("minorityInterest")),
            "preferred_equity": _safe_float(bal.get("preferredStock")),
            "total_assets": _safe_float(bal.get("totalAssets")),
            "total_liabilities": _safe_float(bal.get("totalLiabilities")),
            "total_equity": _safe_float(bal.get("totalStockholdersEquity")),
            "receivables": _safe_float(bal.get("netReceivables")),
            "inventory": _safe_float(bal.get("inventory")),
            "payables": _safe_float(bal.get("accountPayables")),
            "diluted_shares": _safe_float(
                inc.get("weightedAverageShsOutDil")
            ),
        }
        rows.append(row)

    logger.debug("Normalised %d statement rows for %s", len(rows), ticker)
    return rows

