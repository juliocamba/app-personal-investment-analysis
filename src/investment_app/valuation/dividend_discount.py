"""Dividend Discount Model (Gordon Growth) — Phase 4.

Applicable only when:
- The company has paid dividends in each of the last N years (``years_stable``
  defaults to 3).
- Dividend per share (DPS) is positive and non-zero.
- Cost of equity (``ke``) strictly exceeds perpetuity growth (``g``).

Formula:  V₀ = D₁ / (Kₑ − g)   where D₁ = D₀ × (1 + g)

All public functions return ``None`` rather than raising on bad inputs.
"""
from __future__ import annotations

from typing import Any


def _get(row: dict[str, Any], key: str) -> float | None:
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def is_ddm_applicable(
    annual_statements: list[dict[str, Any]],
    *,
    years_stable: int = 3,
) -> bool:
    """Return True when DDM is appropriate for this company.

    Conditions:
    1. At least ``years_stable`` annual statements are available.
    2. ``dividends_paid`` is present and negative (cash outflow) in each of
       those years.
    """
    if len(annual_statements) < years_stable:
        return False
    recent = annual_statements[:years_stable]
    for stmt in recent:
        div = _get(stmt, "dividends_paid")
        if div is None or div >= 0.0:
            # dividends_paid is a cash outflow — negative in most reporting
            # conventions.  Zero or missing means no dividend.
            return False
    return True


def compute_ddm_value(
    *,
    dps: float | None,
    growth_rate: float,
    cost_of_equity: float,
) -> float | None:
    """Gordon Growth DDM: V₀ = D₁ / (Kₑ − g).

    Parameters
    ----------
    dps:
        Dividend per share (trailing, i.e. D₀).  Must be positive.
    growth_rate:
        Expected perpetuity dividend growth rate.
    cost_of_equity:
        Required return on equity.  Must be strictly greater than
        ``growth_rate``.

    Returns
    -------
    float or None
        Intrinsic value per share, or None when conditions are not met.
    """
    if dps is None or dps <= 0.0:
        return None
    spread = cost_of_equity - growth_rate
    if spread <= 0.0:
        return None
    d1 = dps * (1.0 + growth_rate)
    return d1 / spread

