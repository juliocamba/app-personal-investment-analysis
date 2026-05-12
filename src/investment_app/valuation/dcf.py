"""Discounted cash flow valuation — Phase 4.

Implements a simplified FCFF-based DCF suitable for non-financial companies.

Model summary
-------------
1. Estimate base-year normalised free cash flow (from statements).
2. Project FCFs over an explicit forecast horizon (default 5 years) using a
   constant growth rate capped by scenario limits.
3. Compute a terminal value using the Gordon Growth formula at horizon year N.
4. Discount all cash flows back to present using WACC.
5. Convert enterprise value → equity value → intrinsic value per share.

All public functions return ``None`` rather than raising when required inputs
are missing or produce unsafe arithmetic.
"""
from __future__ import annotations

from typing import Any


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Return numerator / denominator, or None when unsafe."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0.0:
        return None
    return numerator / denominator


def _get(row: dict[str, Any], key: str) -> float | None:
    """Extract a float from a dict row; return None on failure."""
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Terminal value
# ---------------------------------------------------------------------------


def compute_terminal_value(
    fcf_terminal_year: float,
    wacc: float,
    terminal_growth: float,
) -> float | None:
    """Gordon-growth terminal value: TV = FCF_{n+1} / (WACC - g).

    Parameters
    ----------
    fcf_terminal_year:
        FCF in the last explicit forecast year.
    wacc:
        Weighted average cost of capital (decimal, e.g. 0.09).
    terminal_growth:
        Perpetuity growth rate (decimal).  Must be strictly less than WACC.

    Returns
    -------
    float or None
        Present value of all FCFs beyond the forecast horizon, *undiscounted*
        (caller discounts it back by the horizon factor).  Returns None when
        WACC ≤ terminal_growth (would produce negative or infinite result).
    """
    spread = wacc - terminal_growth
    if spread <= 0.0:
        return None
    # TV is FCF growing by g one more period, then divided by the spread.
    return (fcf_terminal_year * (1.0 + terminal_growth)) / spread


# ---------------------------------------------------------------------------
# Explicit-period PV
# ---------------------------------------------------------------------------


def compute_present_value_fcfs(
    base_fcf: float,
    growth_rate: float,
    wacc: float,
    years: int,
) -> tuple[list[float], float]:
    """Project FCFs and return (year_fcfs, pv_sum).

    Parameters
    ----------
    base_fcf:
        Free cash flow in year 0 (most recent reported).
    growth_rate:
        Annual FCF growth rate applied uniformly over all forecast years.
    wacc:
        Discount rate.
    years:
        Number of explicit forecast years.

    Returns
    -------
    year_fcfs:
        List of projected FCF values (year 1 … year N).
    pv_sum:
        Sum of discounted FCFs over the explicit period.
    """
    year_fcfs: list[float] = []
    pv_sum = 0.0
    fcf = base_fcf
    for t in range(1, years + 1):
        fcf = fcf * (1.0 + growth_rate)
        year_fcfs.append(fcf)
        pv_sum += fcf / ((1.0 + wacc) ** t)
    return year_fcfs, pv_sum


# ---------------------------------------------------------------------------
# Equity bridge
# ---------------------------------------------------------------------------


def enterprise_to_equity_value(
    enterprise_value: float,
    *,
    net_debt: float | None,
    minority_interest: float | None,
    preferred_equity: float | None,
) -> float | None:
    """Convert enterprise value to equity value.

    Equity Value = EV − net_debt − minority_interest − preferred_equity

    Missing components default to 0 so that a partial bridge is still
    computed rather than returning None.
    """
    equity = enterprise_value
    equity -= net_debt or 0.0
    equity -= minority_interest or 0.0
    equity -= preferred_equity or 0.0
    return equity


# ---------------------------------------------------------------------------
# Full single-scenario DCF
# ---------------------------------------------------------------------------


def run_dcf_scenario(
    *,
    base_fcf: float | None,
    growth_rate: float,
    wacc: float,
    terminal_growth: float,
    forecast_years: int,
    net_debt: float | None,
    minority_interest: float | None,
    preferred_equity: float | None,
    diluted_shares: float | None,
) -> dict[str, float | None]:
    """Run a single DCF scenario and return all intermediate outputs.

    Returns a dict with keys:
    - ``pv_fcfs``             PV of explicit forecast FCFs
    - ``terminal_value``      TV at horizon year (undiscounted)
    - ``pv_terminal_value``   PV of terminal value
    - ``enterprise_value``    EV = pv_fcfs + pv_terminal_value
    - ``equity_value``        EV bridge to equity
    - ``intrinsic_value_per_share``  equity_value / diluted_shares
    - ``growth_rate``         growth rate used
    - ``wacc``                WACC used
    - ``terminal_growth``     terminal growth rate used

    Any step that cannot be completed returns None for that key and all
    downstream keys.
    """
    result: dict[str, float | None] = {
        "pv_fcfs": None,
        "terminal_value": None,
        "pv_terminal_value": None,
        "enterprise_value": None,
        "equity_value": None,
        "intrinsic_value_per_share": None,
        "growth_rate": growth_rate,
        "wacc": wacc,
        "terminal_growth": terminal_growth,
    }

    # Guard: need a valid positive discount rate.
    if wacc <= 0.0:
        return result

    # Guard: terminal growth must be below WACC.
    if terminal_growth >= wacc:
        return result

    # Guard: need a base FCF.
    if base_fcf is None:
        return result

    # Project explicit FCFs.
    year_fcfs, pv_fcfs = compute_present_value_fcfs(
        base_fcf, growth_rate, wacc, forecast_years
    )
    result["pv_fcfs"] = pv_fcfs

    # Terminal value.
    terminal_year_fcf = year_fcfs[-1] if year_fcfs else base_fcf
    tv = compute_terminal_value(terminal_year_fcf, wacc, terminal_growth)
    if tv is None:
        return result
    result["terminal_value"] = tv

    # Discount TV back to present.
    pv_tv = tv / ((1.0 + wacc) ** forecast_years)
    result["pv_terminal_value"] = pv_tv

    # Enterprise value.
    ev = pv_fcfs + pv_tv
    result["enterprise_value"] = ev

    # Equity value.
    eq_val = enterprise_to_equity_value(
        ev,
        net_debt=net_debt,
        minority_interest=minority_interest,
        preferred_equity=preferred_equity,
    )
    result["equity_value"] = eq_val

    # Per share.
    if eq_val is None:
        return result
    if diluted_shares is not None and diluted_shares > 0.0:
        result["intrinsic_value_per_share"] = eq_val / diluted_shares

    return result


# ---------------------------------------------------------------------------
# FCF extraction helper
# ---------------------------------------------------------------------------


def extract_base_fcf(
    annual_statements: list[dict[str, Any]],
    *,
    ebit_margin_cap: float = 0.50,
    tax_rate_fallback: float = 0.25,
) -> dict[str, Any]:
    """Derive base-year FCF and its components from annual statements.

    Priority order:
    1. Use ``free_cash_flow`` if present and positive.
    2. Fall back to FCFF estimation:
       FCFF ≈ EBIT*(1-t) + D&A - capex
       (change_in_working_capital is excluded in MVP; treated conservatively
        as 0 — callers should pass a conservative margin if this is material).

    Returns a dict with keys: base_fcf, revenue, ebit, da, capex, tax_rate,
    direct_fcf, direct_fcf_status, fcf_source.
    All values may be None.
    """
    out: dict[str, Any] = {
        "base_fcf": None,
        "revenue": None,
        "ebit": None,
        "da": None,
        "capex": None,
        "tax_rate": tax_rate_fallback,
        "direct_fcf": None,
        "direct_fcf_status": "missing",
        "fcf_source": None,
    }
    if not annual_statements:
        return out

    current = annual_statements[0]
    revenue = _get(current, "revenue")
    ebit = _get(current, "ebit")
    da = _get(current, "depreciation_amortization")
    capex = _get(current, "capex")
    fcf_direct = _get(current, "free_cash_flow")

    out["revenue"] = revenue
    out["ebit"] = ebit
    out["da"] = da
    out["capex"] = capex
    out["direct_fcf"] = fcf_direct

    # Respect an explicitly reported direct FCF. For MVP, negative or zero
    # direct FCF is a hard conservative stop for DCF rather than a trigger to
    # synthesize a more optimistic FCFF fallback.
    if fcf_direct is not None:
        if fcf_direct > 0.0:
            out["direct_fcf_status"] = "positive"
            out["fcf_source"] = "direct"
            out["base_fcf"] = fcf_direct
            return out
        if fcf_direct < 0.0:
            out["direct_fcf_status"] = "negative"
            out["fcf_source"] = "direct_negative"
            return out
        out["direct_fcf_status"] = "zero"
        out["fcf_source"] = "direct_zero"
        return out

    # FCFF estimation fallback.
    if ebit is None:
        return out

    # Cap margin conservatively.
    if revenue and revenue > 0 and ebit / revenue > ebit_margin_cap:
        ebit = revenue * ebit_margin_cap

    nopat = ebit * (1.0 - tax_rate_fallback)
    da_val = da if da is not None else 0.0
    capex_val = capex if capex is not None else 0.0
    estimated_fcf = nopat + da_val - abs(capex_val)

    # Only use positive estimated FCF; negative means the business consumes
    # cash — leave base_fcf None so scenarios produce no valuation.
    if estimated_fcf > 0.0:
        out["base_fcf"] = estimated_fcf
        out["fcf_source"] = "synthetic_fcff"

    return out

