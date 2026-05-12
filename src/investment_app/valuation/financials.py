"""Financial-sector valuation helper — Phase 4.

For banks and insurers the standard DCF is unreliable because capex and
working capital are not cleanly separable from financing operations.  This
module implements a simple placeholder using P/B adjusted for ROE vs. cost
of equity (the Damodaran justified P/B approach):

    Justified P/B = ROE / Ke
    Intrinsic Value = Justified_P/B × Book_Value_per_Share

This is a well-known first-pass heuristic, not a full dividend-discount DDM
for financial firms.  The ``method`` key in the output is set to
``financial_sector_placeholder_v0`` so downstream consumers can flag it.

All public functions return ``None`` rather than raising on bad inputs.
"""
from __future__ import annotations

from typing import Any

_FINANCIAL_SECTORS = frozenset(
    {
        "financials",
        "banking",
        "banks",
        "insurance",
        "financial services",
        "diversified financials",
        "real estate",
    }
)


def is_financial_sector(sector: str | None) -> bool:
    """Return True when the company's sector is a financial / RE sector."""
    if not sector:
        return False
    return sector.strip().lower() in _FINANCIAL_SECTORS


def _get(row: dict[str, Any], key: str) -> float | None:
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_financial_sector_value(
    *,
    roe: float | None,
    cost_of_equity: float,
    book_value_per_share: float | None,
) -> dict[str, Any]:
    """Justified P/B intrinsic value for financial-sector companies.

    Parameters
    ----------
    roe:
        Return on equity (decimal, e.g. 0.12).  Must be positive.
    cost_of_equity:
        Required return on equity (decimal).  Must be positive and non-zero.
    book_value_per_share:
        Book value per share.  Must be positive.

    Returns
    -------
    dict with keys:
    - ``intrinsic_value_per_share`` float or None
    - ``justified_pb``             float or None
    - ``method``                   ``"financial_sector_placeholder_v0"``
    """
    out: dict[str, Any] = {
        "intrinsic_value_per_share": None,
        "justified_pb": None,
        "method": "financial_sector_placeholder_v0",
    }
    if roe is None or roe <= 0.0:
        return out
    if cost_of_equity <= 0.0:
        return out
    if book_value_per_share is None or book_value_per_share <= 0.0:
        return out

    justified_pb = roe / cost_of_equity
    out["justified_pb"] = justified_pb
    out["intrinsic_value_per_share"] = justified_pb * book_value_per_share
    return out

