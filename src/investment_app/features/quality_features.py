"""Data-quality score computation — Phase 3.

Produces a score from 0 to 100 that reflects how complete the available data
is for a given company on a given day.  The score is stored in
``ratios_factors.data_quality_score``.
"""
from __future__ import annotations


# Point weights — must sum to 100.
_WEIGHTS: dict[str, int] = {
    "has_price": 20,           # latest price available
    "has_annual_statement": 30, # latest annual financial statements
    "has_shares": 10,           # diluted share count present
    "has_market_cap": 10,       # market cap computable
    "has_fx_if_needed": 10,     # FX rate available when non-USD company
    "has_filings": 10,          # at least one filing indexed
    "has_required_fields": 10,  # no major required field gaps
}

assert sum(_WEIGHTS.values()) == 100, "Quality score weights must sum to 100."


def compute_data_quality_score(
    *,
    has_price: bool,
    has_annual_statement: bool,
    has_shares: bool,
    has_market_cap: bool,
    has_fx_if_needed: bool,
    has_filings: bool,
    has_required_fields: bool,
) -> float:
    """Return a data-quality score between 0 and 100.

    Each boolean flag maps to a fixed point value; the score is the sum of
    points for all flags that are ``True``.
    """
    flags = {
        "has_price": has_price,
        "has_annual_statement": has_annual_statement,
        "has_shares": has_shares,
        "has_market_cap": has_market_cap,
        "has_fx_if_needed": has_fx_if_needed,
        "has_filings": has_filings,
        "has_required_fields": has_required_fields,
    }
    return float(sum(_WEIGHTS[k] for k, v in flags.items() if v))
