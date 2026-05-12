"""Valuation package — Phase 4.

Public surface:

    from investment_app.valuation import compute_valuation_run

``compute_valuation_run`` is the single entry-point for the daily pipeline.
"""
from __future__ import annotations

from investment_app.valuation.scenarios import compute_valuation_run

__all__ = ["compute_valuation_run"]

