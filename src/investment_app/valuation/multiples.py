"""Trading-multiples valuation — Phase 4.

Estimates intrinsic value using four comparable multiples:

  - P/E   (price-to-earnings)
  - EV/EBITDA
  - P/S   (price-to-sales)
  - P/B   (price-to-book)

Because this MVP has no live peer set, the historical median of the company's
own ratios is used as the target multiple.  A per-share intrinsic value is
derived by applying the target multiple to the current-year fundamental.

All public functions return ``None`` rather than raising on bad inputs.
"""
from __future__ import annotations

import statistics
from typing import Any


def _get(row: dict[str, Any], key: str) -> float | None:
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _median_excluding_outliers(
    values: list[float],
    *,
    lo_pct: float = 0.1,
    hi_pct: float = 0.9,
) -> float | None:
    """Return the median of *values* after trimming extreme percentiles."""
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    lo_idx = int(n * lo_pct)
    hi_idx = max(lo_idx + 1, int(n * hi_pct))
    trimmed = sorted_vals[lo_idx:hi_idx]
    if not trimmed:
        return None
    return statistics.median(trimmed)


# ---------------------------------------------------------------------------
# P/E multiple
# ---------------------------------------------------------------------------


def value_by_pe(
    *,
    current_eps: float | None,
    ratio_rows: list[dict[str, Any]],
) -> float | None:
    """Estimate intrinsic value per share via historical median P/E × current EPS.

    Parameters
    ----------
    current_eps:
        Trailing twelve-month EPS.  Must be positive.
    ratio_rows:
        Historical ``ratios_factors`` rows from which ``pe_ratio`` values are
        extracted.

    Returns
    -------
    float or None
        Estimated intrinsic value per share, or None when the P/E multiple or
        EPS is unavailable / non-positive.
    """
    if current_eps is None or current_eps <= 0.0:
        return None
    pe_values = [
        v for row in ratio_rows if (v := _get(row, "pe_ratio")) is not None and v > 0.0
    ]
    median_pe = _median_excluding_outliers(pe_values)
    if median_pe is None or median_pe <= 0.0:
        return None
    return current_eps * median_pe


# ---------------------------------------------------------------------------
# EV/EBITDA multiple
# ---------------------------------------------------------------------------


def value_by_ev_ebitda(
    *,
    current_ebitda: float | None,
    net_debt: float | None,
    diluted_shares: float | None,
    ratio_rows: list[dict[str, Any]],
) -> float | None:
    """Estimate intrinsic value per share via EV/EBITDA × current EBITDA.

    EV = median_multiple × EBITDA
    Equity value = EV − net_debt
    Per share = equity_value / diluted_shares
    """
    if current_ebitda is None or current_ebitda <= 0.0:
        return None
    if diluted_shares is None or diluted_shares <= 0.0:
        return None
    ev_mult_values = [
        v
        for row in ratio_rows
        if (v := _get(row, "ev_to_ebitda")) is not None and v > 0.0
    ]
    median_mult = _median_excluding_outliers(ev_mult_values)
    if median_mult is None or median_mult <= 0.0:
        return None
    ev = median_mult * current_ebitda
    equity_value = ev - (net_debt or 0.0)
    if equity_value <= 0.0:
        return None
    return equity_value / diluted_shares


# ---------------------------------------------------------------------------
# P/S multiple
# ---------------------------------------------------------------------------


def value_by_ps(
    *,
    current_revenue_per_share: float | None,
    ratio_rows: list[dict[str, Any]],
) -> float | None:
    """Estimate intrinsic value per share via historical median P/S × revenue per share."""
    if current_revenue_per_share is None or current_revenue_per_share <= 0.0:
        return None
    ps_values = [
        v
        for row in ratio_rows
        if (v := _get(row, "price_to_sales")) is not None and v > 0.0
    ]
    median_ps = _median_excluding_outliers(ps_values)
    if median_ps is None or median_ps <= 0.0:
        return None
    return current_revenue_per_share * median_ps


# ---------------------------------------------------------------------------
# P/B multiple
# ---------------------------------------------------------------------------


def value_by_pb(
    *,
    current_book_value_per_share: float | None,
    ratio_rows: list[dict[str, Any]],
) -> float | None:
    """Estimate intrinsic value per share via historical median P/B × BVPS."""
    if current_book_value_per_share is None or current_book_value_per_share <= 0.0:
        return None
    pb_values = [
        v
        for row in ratio_rows
        if (v := _get(row, "price_to_book")) is not None and v > 0.0
    ]
    median_pb = _median_excluding_outliers(pb_values)
    if median_pb is None or median_pb <= 0.0:
        return None
    return current_book_value_per_share * median_pb


# ---------------------------------------------------------------------------
# Combined multiples estimate
# ---------------------------------------------------------------------------


def compute_multiples_value(
    *,
    statement: dict[str, Any] | None,
    net_debt: float | None,
    diluted_shares: float | None,
    ratio_rows: list[dict[str, Any]],
) -> dict[str, float | None]:
    """Aggregate all four multiple-based estimates and return a weighted average.

    When any method produces a value, it contributes equally to the blended
    estimate (equal-weight average of available methods).

    Returns a dict:
    - ``pe_value``        P/E estimate
    - ``ev_ebitda_value`` EV/EBITDA estimate
    - ``ps_value``        P/S estimate
    - ``pb_value``        P/B estimate
    - ``blended_value``   simple mean of available estimates
    """
    result: dict[str, float | None] = {
        "pe_value": None,
        "ev_ebitda_value": None,
        "ps_value": None,
        "pb_value": None,
        "blended_value": None,
    }
    if statement is None or diluted_shares is None or diluted_shares <= 0.0:
        return result

    net_income = _get(statement, "net_income")
    revenue = _get(statement, "revenue")
    total_equity = _get(statement, "total_equity")
    ebit = _get(statement, "ebit")
    da = _get(statement, "depreciation_amortization")

    # EPS
    eps = (net_income / diluted_shares) if net_income is not None else None
    result["pe_value"] = value_by_pe(current_eps=eps, ratio_rows=ratio_rows)

    # EBITDA
    ebitda: float | None = None
    if ebit is not None:
        ebitda = ebit + (da or 0.0)
    result["ev_ebitda_value"] = value_by_ev_ebitda(
        current_ebitda=ebitda,
        net_debt=net_debt,
        diluted_shares=diluted_shares,
        ratio_rows=ratio_rows,
    )

    # Revenue per share
    rev_per_share = (revenue / diluted_shares) if revenue is not None else None
    result["ps_value"] = value_by_ps(
        current_revenue_per_share=rev_per_share,
        ratio_rows=ratio_rows,
    )

    # BVPS
    bvps = (total_equity / diluted_shares) if total_equity is not None else None
    result["pb_value"] = value_by_pb(
        current_book_value_per_share=bvps,
        ratio_rows=ratio_rows,
    )

    estimates = [
        v
        for v in (
            result["pe_value"],
            result["ev_ebitda_value"],
            result["ps_value"],
            result["pb_value"],
        )
        if v is not None
    ]
    if estimates:
        result["blended_value"] = sum(estimates) / len(estimates)

    return result

