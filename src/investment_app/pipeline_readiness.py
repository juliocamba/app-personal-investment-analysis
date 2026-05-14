"""Phase 10C.2 pipeline-readiness integration helpers.

This module bridges the pure :mod:`investment_app.readiness` classifier with
the daily pipeline.  For each company it:

1. Loads the minimal already-persisted rows the classifier needs.
2. Calls :func:`classify_company_readiness`.
3. Emits a compact, safe ``readiness_classified`` pipeline event.
4. Exposes :func:`should_skip_valuation` and :func:`should_skip_signal` gates
   that the pipeline loops consult before calling compute functions.

Design constraints (PR 10C.2):
- No new provider calls.
- No SQL / schema changes.
- No frontend changes.
- Never raises; any error is caught, logged, and returns ``None`` so the
  existing compute path is unaffected (fail-open gate policy).
- Event details never contain raw payloads, API keys, URLs-with-keys,
  raw exception text, or secrets.
"""
from __future__ import annotations

import logging
from typing import Any

from investment_app.readiness import classify_company_readiness

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repo adapter — loads minimal rows needed by the classifier
# ---------------------------------------------------------------------------


def load_readiness_inputs(
    company_id: str,
    *,
    repo_module: Any,
    factor_date: str,
) -> dict[str, Any]:
    """Load minimal persisted rows for one company.

    Returns a dict with keys:
      ``latest_price_row``, ``statement_rows``, ``filing_rows``,
      ``latest_valuation_row``, ``latest_signal_row``.

    Raises on repo failure (caller is responsible for wrapping in try/except).
    """
    price_rows = repo_module.get_prices_for_company(
        company_id, as_of_date=factor_date, limit=1
    )
    statement_rows = repo_module.get_statements_for_company(
        company_id, as_of_date=factor_date, limit=10
    )
    filing_rows = repo_module.get_filings_for_company(
        company_id, as_of_date=factor_date, limit=5
    )
    latest_valuation_row = repo_module.get_latest_valuation_run(
        company_id, as_of_date=factor_date
    )
    signal_rows = repo_module.get_signal_runs_for_company(
        company_id, as_of_date=factor_date, limit=1
    )
    return {
        "latest_price_row": price_rows[0] if price_rows else None,
        "statement_rows": statement_rows,
        "filing_rows": filing_rows,
        "latest_valuation_row": latest_valuation_row,
        "latest_signal_row": signal_rows[0] if signal_rows else None,
    }


# ---------------------------------------------------------------------------
# Pipeline-aware classifier wrapper
# ---------------------------------------------------------------------------


def classify_company_for_pipeline(
    company: dict[str, Any],
    company_id: str,
    *,
    repo_module: Any,
    run_id: str,
    factor_date: str,
    metrics: dict[str, int],
) -> dict[str, Any] | None:
    """Load data, run the readiness classifier, emit pipeline event, update metrics.

    Returns the readiness result dict, or ``None`` if classification fails
    (repo error, unexpected exception).  The gate functions treat ``None`` as
    "do not gate" so the existing compute path is unaffected on failure.

    Never raises.
    """
    ticker = company.get("ticker", "")
    try:
        inputs = load_readiness_inputs(
            company_id, repo_module=repo_module, factor_date=factor_date
        )
        # fx_provider is optional metadata; derive from company if present.
        fx_provider = (company.get("metadata") or {}).get("fx_provider")

        result = classify_company_readiness(
            company,
            latest_price_row=inputs["latest_price_row"],
            statement_rows=inputs["statement_rows"],
            filing_rows=inputs["filing_rows"],
            latest_valuation_row=inputs["latest_valuation_row"],
            latest_signal_row=inputs["latest_signal_row"],
            fx_provider=fx_provider,
        )

        metrics["readiness_classified"] = metrics.get("readiness_classified", 0) + 1

        repo_module.log_pipeline_event(
            run_id,
            stage="readiness",
            company_id=company_id,
            message=f"Readiness classified for {ticker}: {result['readiness_status']}.",
            details={
                "ticker": ticker,
                "event": "readiness_classified",
                "readiness_status": result["readiness_status"],
                "provider_mix": result["provider_mix"],
                "reason_codes": result["reason_codes"],
                "can_run_valuation": result["can_run_valuation"],
                "can_run_signal": result["can_run_signal"],
                "limiting_domain": result.get("limiting_domain"),
            },
        )

        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Readiness classification failed for %s (%s) — continuing without gating.",
            ticker,
            type(exc).__name__,
        )
        metrics["readiness_errors"] = metrics.get("readiness_errors", 0) + 1
        try:
            repo_module.log_pipeline_event(
                run_id,
                stage="readiness",
                level="warning",
                company_id=company_id,
                message=(
                    f"Readiness classification failed for {ticker} "
                    "— continuing without gating."
                ),
                details={
                    "ticker": ticker,
                    "event": "readiness_classification_error",
                    "error_type": type(exc).__name__,
                },
            )
        except Exception:  # noqa: BLE001
            pass
        return None


# ---------------------------------------------------------------------------
# Gate helpers — consumed by the pipeline compute loops
# ---------------------------------------------------------------------------


def should_skip_valuation(readiness: dict[str, Any] | None) -> bool:
    """Return ``True`` when readiness says valuation must not run.

    Returns ``False`` (do not gate) when *readiness* is ``None`` so that a
    classification failure never silently suppresses compute work.
    """
    if readiness is None:
        return False
    return not readiness.get("can_run_valuation", True)


def should_skip_signal(readiness: dict[str, Any] | None) -> bool:
    """Return ``True`` when readiness says signal must not run.

    Returns ``False`` (do not gate) when *readiness* is ``None``.
    """
    if readiness is None:
        return False
    return not readiness.get("can_run_signal", True)
