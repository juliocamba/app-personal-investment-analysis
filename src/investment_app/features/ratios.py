"""Financial ratio calculations — Phase 3.

All public functions accept plain ``dict`` objects sourced from
``statements_norm`` and ``price_eod``.  Missing or zero denominators always
produce ``None`` rather than raising an exception.
"""
from __future__ import annotations

from typing import Any

# Effective tax rate used when estimating NOPAT for ROIC.
_DEFAULT_TAX_RATE = 0.25


def safe_div(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    """Return ``numerator / denominator``, or ``None`` when division is unsafe.

    Returns ``None`` when either operand is ``None`` or the denominator is
    zero.  Never raises.
    """
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _get(row: dict[str, Any], key: str) -> float | None:
    """Extract a float-compatible value from *row*, returning ``None`` on failure."""
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_financial_ratios(
    annual_statements: list[dict[str, Any]],
    *,
    latest_price_row: dict[str, Any] | None = None,
    tax_rate_fallback: float = _DEFAULT_TAX_RATE,
) -> dict[str, float | None]:
    """Compute financial ratios from normalised annual statements.

    Parameters
    ----------
    annual_statements:
        Rows from ``statements_norm`` where ``fiscal_period = 'FY'``, sorted
        by ``fiscal_year`` **descending** (most-recent first).  At least one
        row is required; two rows enable revenue growth YoY.
    latest_price_row:
        Most-recent row from ``price_eod`` for the same company.  Required
        only for market-based ratios (P/E, P/S, EV/EBITDA, FCF yield).
    tax_rate_fallback:
        Assumed effective tax rate for NOPAT estimation in ROIC.

    Returns
    -------
    dict
        Keys match columns in ``ratios_factors``.  Any ratio that cannot be
        computed safely is ``None``.
    """
    result: dict[str, float | None] = {
        "revenue_growth_yoy": None,
        "gross_margin": None,
        "operating_margin": None,
        "net_margin": None,
        "fcf_margin": None,
        "roe": None,
        "roic": None,
        "net_debt_to_ebitda": None,
        # interest_coverage requires interest expense, which is not in
        # statements_norm; always None until schema is extended.
        "interest_coverage": None,
        "pe_ratio": None,
        "ev_to_ebitda": None,
        "price_to_sales": None,
        "price_to_book": None,
        "fcf_yield": None,
    }

    if not annual_statements:
        return result

    current = annual_statements[0]

    revenue = _get(current, "revenue")
    gross_profit = _get(current, "gross_profit")
    operating_income = _get(current, "operating_income")
    ebit = _get(current, "ebit")
    ebitda = _get(current, "ebitda")
    net_income = _get(current, "net_income")
    free_cash_flow = _get(current, "free_cash_flow")
    total_equity = _get(current, "total_equity")
    total_debt = _get(current, "total_debt")
    cash = _get(current, "cash_and_equivalents")
    diluted_shares = _get(current, "diluted_shares")

    # ── Margin ratios ────────────────────────────────────────────────────────
    result["gross_margin"] = safe_div(gross_profit, revenue)
    result["operating_margin"] = safe_div(operating_income, revenue)
    result["net_margin"] = safe_div(net_income, revenue)
    result["fcf_margin"] = safe_div(free_cash_flow, revenue)

    # ── Return ratios ────────────────────────────────────────────────────────
    # ROE = net_income / average_total_equity.
    # Use average of current and prior year when prior data is available;
    # fall back to ending equity when the series has only one year.
    prior_equity = (
        _get(annual_statements[1], "total_equity")
        if len(annual_statements) >= 2
        else None
    )
    if prior_equity is not None and total_equity is not None:
        avg_equity: float | None = (total_equity + prior_equity) / 2.0
    else:
        avg_equity = total_equity  # single-year fallback
    result["roe"] = safe_div(net_income, avg_equity)

    # ROIC = NOPAT / Invested Capital
    # NOPAT  = EBIT × (1 − tax_rate)
    # Invested Capital = total_equity + total_debt − cash
    if ebit is not None:
        nopat = ebit * (1.0 - tax_rate_fallback)
        if total_equity is not None and total_debt is not None and cash is not None:
            invested_capital = total_equity + total_debt - cash
            result["roic"] = safe_div(nopat, invested_capital)

    # ── Leverage ratios ──────────────────────────────────────────────────────
    if total_debt is not None and cash is not None:
        net_debt = total_debt - cash
        result["net_debt_to_ebitda"] = safe_div(net_debt, ebitda)

    # ── Revenue growth YoY ───────────────────────────────────────────────────
    if len(annual_statements) >= 2:
        prior_revenue = _get(annual_statements[1], "revenue")
        if revenue is not None and prior_revenue is not None:
            result["revenue_growth_yoy"] = safe_div(
                revenue - prior_revenue, prior_revenue
            )

    # ── Market-based ratios (require price data) ─────────────────────────────
    if latest_price_row is not None:
        market_cap = _get(latest_price_row, "market_cap")
        price = _get(latest_price_row, "close")

        # Derive market cap from price × diluted shares when not stored directly.
        if market_cap is None and price is not None and diluted_shares is not None:
            market_cap = price * diluted_shares

        # Enterprise Value = market_cap + total_debt − cash
        ev: float | None = None
        if market_cap is not None and total_debt is not None and cash is not None:
            ev = market_cap + total_debt - cash

        result["pe_ratio"] = safe_div(market_cap, net_income)
        result["price_to_sales"] = safe_div(market_cap, revenue)
        result["price_to_book"] = safe_div(market_cap, total_equity)
        result["ev_to_ebitda"] = safe_div(ev, ebitda)
        result["fcf_yield"] = safe_div(free_cash_flow, market_cap)

    return result
