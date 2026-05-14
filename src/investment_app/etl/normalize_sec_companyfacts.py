"""SEC EDGAR companyfacts normaliser — Phase 10A.

Converts a SEC EDGAR ``/api/xbrl/companyfacts/CIK{cik}.json`` payload into
canonical ``statements_norm`` rows (annual/FY, 10-K only).

Design constraints
------------------
* Only ``us-gaap`` taxonomy is processed.
* Only ``fp = FY`` facts are considered (annual mode).
* Prefer ``form = 10-K``; fall back to other annual-looking forms only if no
  10-K fact is available for the same concept/year.
* Prefer ``USD`` for monetary concepts; ``shares`` for diluted share counts.
* When multiple facts exist for the same concept and fiscal year, select
  deterministically by: latest ``filed`` date → form preference (10-K first) →
  latest ``end`` date → accession number (lexicographic tiebreak).
* ``free_cash_flow`` is always derived as ``cfo - abs(capex)`` when both are
  available; the SEC concept for FCF is not trusted directly.
* ``ebit`` is set conservatively as ``operating_income`` when no better value
  exists.
* ``ebitda`` is derived only when both ``ebit`` and
  ``depreciation_amortization`` are known.
* No live API calls anywhere in this module.
* No secrets, raw URLs, or raw exception text exposed.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Taxonomy / unit constants ─────────────────────────────────────────────────

_TAXONOMY = "us-gaap"
_ANNUAL_FP = "FY"
_PREFERRED_FORM = "10-K"
_MONETARY_UNIT = "USD"
_SHARES_UNIT = "shares"

# ── Concept priority lists ────────────────────────────────────────────────────
# Each list is tried in order; the first concept that yields a value wins.

_REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
]
_GROSS_PROFIT_CONCEPTS = ["GrossProfit"]
_OPERATING_INCOME_CONCEPTS = ["OperatingIncomeLoss"]
_NET_INCOME_CONCEPTS = ["NetIncomeLoss"]
_CFO_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
_CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "CapitalExpendituresIncurredButNotYetPaid",
]
_CASH_CONCEPTS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
]
_DEBT_CONCEPTS = [
    "DebtLongtermAndShorttermCombinedAmount",
    "LongTermDebtAndFinanceLeaseObligationsCurrent",
    "LongTermDebtCurrent",
    "ShortTermBorrowings",
    "LongTermDebtNoncurrent",
]
_ASSETS_CONCEPTS = ["Assets"]
_LIABILITIES_CONCEPTS = ["Liabilities"]
_EQUITY_CONCEPTS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]
_DILUTED_SHARES_CONCEPTS = [
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingDiluted",
]
_DILUTED_SHARES_WEAK_CONCEPTS = ["EntityCommonStockSharesOutstanding"]
_DA_CONCEPTS = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _safe_float(value: Any) -> float | None:
    """Return a float or None without raising."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_annual_fact(fact: dict[str, Any]) -> bool:
    """Return True when the fact represents an annual (FY) period."""
    return fact.get("fp") == _ANNUAL_FP


def _is_preferred_form(fact: dict[str, Any]) -> bool:
    """Return True when the fact was filed on a 10-K."""
    return fact.get("form") == _PREFERRED_FORM


def _fact_rank_key(fact: dict[str, Any]) -> tuple:
    """Ranking key for comparing facts within the same form subset.

    Higher is better — sort descending.

    Priority:
    1. latest ``filed`` date (ISO string, lexicographic sort works)
    2. latest ``end`` date
    3. accession number (stable final tiebreak)

    Note: form preference is handled before ranking in
    ``_select_best_fact_for_year`` — this function is called on a
    single-form working set only.
    """
    return (
        fact.get("filed") or "",
        fact.get("end") or "",
        fact.get("accn") or "",
    )


def _get_unit_facts(
    concept_payload: dict[str, Any],
    preferred_unit: str,
) -> list[dict[str, Any]]:
    """Return all facts with the preferred unit from a concept payload.

    Falls back to any available unit group if the preferred unit is absent.
    Always returns an empty list when the concept payload is missing.
    """
    units: dict[str, list[dict[str, Any]]] = concept_payload.get("units", {})
    if preferred_unit in units:
        return units[preferred_unit]
    # If preferred unit not present, return empty — do not silently use wrong unit.
    return []


def _select_best_fact_for_year(
    facts: list[dict[str, Any]],
    fiscal_year: int,
) -> dict[str, Any] | None:
    """Return the best (most authoritative) annual fact for *fiscal_year*.

    Selection strategy:
    1. Filter to ``fp = FY`` facts with ``fy = fiscal_year``.
    2. Narrow to 10-K facts if any exist — strict form preference.
       Only falls back to other FY forms when no 10-K is available
       for this concept and year.
    3. Within the chosen subset rank by ``_fact_rank_key``:
       filed desc → end desc → accn desc.

    Returns ``None`` when no qualifying fact exists.
    """
    candidates = [
        f for f in facts
        if _is_annual_fact(f) and f.get("fy") == fiscal_year
    ]
    if not candidates:
        return None
    # Strict form preference: use only 10-K facts when available.
    # Only fall back to other FY forms when no 10-K exists for this
    # concept/year.
    preferred = [f for f in candidates if _is_preferred_form(f)]
    working_set = preferred if preferred else candidates
    # Rank within the chosen subset: filed desc → end desc → accn desc.
    working_set.sort(key=_fact_rank_key, reverse=True)
    return working_set[0]


def _extract_concept_value(
    us_gaap_facts: dict[str, Any],
    concepts: list[str],
    preferred_unit: str,
    fiscal_year: int,
) -> tuple[float | None, str | None, dict[str, Any] | None]:
    """Try each concept in priority order; return (value, concept_name, fact).

    Returns ``(None, None, None)`` when no concept yields a value for the year.
    """
    for concept in concepts:
        concept_data = us_gaap_facts.get(concept)
        if not concept_data:
            continue
        unit_facts = _get_unit_facts(concept_data, preferred_unit)
        best = _select_best_fact_for_year(unit_facts, fiscal_year)
        if best is not None:
            value = _safe_float(best.get("val"))
            if value is not None:
                return value, concept, best
    return None, None, None


def _normalize_capex(raw_capex: float | None) -> float | None:
    """Return capex as a negative number (cash outflow convention).

    SEC may report capex as a positive payment amount.  Normalise to the
    project convention where capex is negative (consistent with FMP normaliser
    which uses ``capitalExpenditure`` which is already negative in FMP payloads).
    """
    if raw_capex is None:
        return None
    return -abs(raw_capex)


def _discover_fiscal_years(
    us_gaap_facts: dict[str, Any],
    probe_concepts: list[str] | None = None,
) -> list[int]:
    """Return sorted list of distinct annual fiscal years found in the payload.

    Probes a small set of common concepts to enumerate available years.
    Falls back to a broader scan if no probe hits.
    """
    if probe_concepts is None:
        probe_concepts = _REVENUE_CONCEPTS + _NET_INCOME_CONCEPTS + _ASSETS_CONCEPTS

    years: set[int] = set()
    for concept in probe_concepts:
        concept_data = us_gaap_facts.get(concept)
        if not concept_data:
            continue
        for facts in concept_data.get("units", {}).values():
            for f in facts:
                if _is_annual_fact(f) and isinstance(f.get("fy"), int):
                    years.add(f["fy"])
        if years:
            break  # enough — probe hit

    if not years:
        # Broader scan: iterate all concepts
        for concept_data in us_gaap_facts.values():
            if not isinstance(concept_data, dict):
                continue
            for facts in concept_data.get("units", {}).values():
                for f in facts:
                    if _is_annual_fact(f) and isinstance(f.get("fy"), int):
                        years.add(f["fy"])

    return sorted(years, reverse=True)


def _pick_period_end_date(
    us_gaap_facts: dict[str, Any],
    fiscal_year: int,
) -> str | None:
    """Return the most authoritative period end date for *fiscal_year*.

    Uses the best Revenue or NetIncomeLoss 10-K fact as the primary source,
    then widens the search to any annual fact.
    """
    for concept in _REVENUE_CONCEPTS + _NET_INCOME_CONCEPTS + _ASSETS_CONCEPTS:
        concept_data = us_gaap_facts.get(concept)
        if not concept_data:
            continue
        for unit_facts in concept_data.get("units", {}).values():
            best = _select_best_fact_for_year(unit_facts, fiscal_year)
            if best and best.get("end"):
                return best["end"]
    return None


# ── Public normaliser ─────────────────────────────────────────────────────────


def normalize_sec_companyfacts_annual(
    payload: dict[str, Any] | None,
    company_id: str,
    ticker: str,
    cik: str,
    *,
    currency: str = "USD",
    fallback_reason: str | None = None,
    raw_payload_id: str | None = None,
    max_years: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalise SEC EDGAR companyfacts into ``statements_norm`` annual rows.

    Parameters
    ----------
    payload:
        Raw SEC ``companyfacts`` JSON payload.
    company_id:
        Supabase UUID of the company.
    ticker:
        Ticker symbol (used in diagnostics only).
    cik:
        SEC CIK (used in diagnostics only).
    currency:
        Not used for monetary fact extraction in Phase 10A.  SEC EDGAR
        ``companyfacts`` monetary facts are always extracted using ``USD``
        regardless of this value.  Retained for API compatibility.
    fallback_reason:
        Compact code explaining why the fallback was invoked
        (e.g. ``"fmp_402"``).
    raw_payload_id:
        Optional FK to ``raw_provider_payloads`` row.
    max_years:
        Maximum number of fiscal years to return (most recent first).

    Returns
    -------
    rows:
        List of ``statements_norm``-shaped dicts, newest year first.
    diagnostics:
        Compact dict with ``rows_normalized``, ``missing_fields``,
        ``weak_fallbacks``, and ``fallback_reason``.
    """
    diagnostics: dict[str, Any] = {
        "ticker": ticker,
        "cik": cik,
        "provider": "sec_edgar",
        "source": "companyfacts",
        "fallback_reason": fallback_reason,
        "rows_normalized": 0,
        "missing_fields": [],
        "weak_fallbacks": [],
    }

    if not payload:
        logger.warning("SEC companyfacts: empty payload for %s (CIK %s)", ticker, cik)
        diagnostics["missing_fields"] = ["all"]
        return [], diagnostics

    us_gaap_facts: dict[str, Any] = (
        payload.get("facts", {}).get(_TAXONOMY, {})
    )
    if not us_gaap_facts:
        logger.warning(
            "SEC companyfacts: no us-gaap facts for %s (CIK %s)", ticker, cik
        )
        diagnostics["missing_fields"] = ["all"]
        return [], diagnostics

    fiscal_years = _discover_fiscal_years(us_gaap_facts)[:max_years]
    if not fiscal_years:
        logger.warning(
            "SEC companyfacts: no annual fiscal years found for %s", ticker
        )
        return [], diagnostics

    rows: list[dict[str, Any]] = []

    for fy in fiscal_years:
        period_end = _pick_period_end_date(us_gaap_facts, fy)
        if not period_end:
            logger.debug("SEC: skipping FY %d for %s — no period_end_date", fy, ticker)
            continue

        field_sources: dict[str, Any] = {}
        missing: list[str] = []
        weak: list[str] = []

        def _get(field: str, concepts: list[str], unit: str) -> float | None:
            val, concept, fact = _extract_concept_value(
                us_gaap_facts, concepts, unit, fy
            )
            if val is not None and concept and fact:
                field_sources[field] = {
                    "concept": concept,
                    "form": fact.get("form"),
                    "fy": fy,
                    "filed": fact.get("filed"),
                    "accn": fact.get("accn"),
                }
            else:
                missing.append(field)
            return val

        revenue = _get("revenue", _REVENUE_CONCEPTS, _MONETARY_UNIT)
        gross_profit = _get("gross_profit", _GROSS_PROFIT_CONCEPTS, _MONETARY_UNIT)
        operating_income = _get(
            "operating_income", _OPERATING_INCOME_CONCEPTS, _MONETARY_UNIT
        )
        net_income = _get("net_income", _NET_INCOME_CONCEPTS, _MONETARY_UNIT)
        cfo = _get("cfo", _CFO_CONCEPTS, _MONETARY_UNIT)

        raw_capex, capex_concept, capex_fact = _extract_concept_value(
            us_gaap_facts, _CAPEX_CONCEPTS, _MONETARY_UNIT, fy
        )
        capex = _normalize_capex(raw_capex)
        if capex is not None and capex_concept and capex_fact:
            field_sources["capex"] = {
                "concept": capex_concept,
                "form": capex_fact.get("form"),
                "fy": fy,
                "filed": capex_fact.get("filed"),
                "accn": capex_fact.get("accn"),
            }
        else:
            missing.append("capex")

        cash = _get("cash_and_equivalents", _CASH_CONCEPTS, _MONETARY_UNIT)
        total_debt = _get("total_debt", _DEBT_CONCEPTS, _MONETARY_UNIT)
        total_assets = _get("total_assets", _ASSETS_CONCEPTS, _MONETARY_UNIT)
        total_liabilities = _get("total_liabilities", _LIABILITIES_CONCEPTS, _MONETARY_UNIT)
        total_equity = _get("total_equity", _EQUITY_CONCEPTS, _MONETARY_UNIT)

        # Diluted shares — prefer strong concepts first, then weak fallback
        diluted_shares, shares_concept, shares_fact = _extract_concept_value(
            us_gaap_facts, _DILUTED_SHARES_CONCEPTS, _SHARES_UNIT, fy
        )
        if diluted_shares is None:
            # Weak fallback: entity common stock shares outstanding
            diluted_shares, shares_concept, shares_fact = _extract_concept_value(
                us_gaap_facts, _DILUTED_SHARES_WEAK_CONCEPTS, _SHARES_UNIT, fy
            )
            if diluted_shares is not None:
                weak.append("diluted_shares")
                field_sources["diluted_shares"] = {
                    "concept": shares_concept,
                    "form": shares_fact.get("form") if shares_fact else None,
                    "fy": fy,
                    "filed": shares_fact.get("filed") if shares_fact else None,
                    "accn": shares_fact.get("accn") if shares_fact else None,
                    "quality_note": "entity_common_stock_shares",
                }
            else:
                missing.append("diluted_shares")
        else:
            field_sources["diluted_shares"] = {
                "concept": shares_concept,
                "form": shares_fact.get("form") if shares_fact else None,
                "fy": fy,
                "filed": shares_fact.get("filed") if shares_fact else None,
                "accn": shares_fact.get("accn") if shares_fact else None,
            }

        # Depreciation & amortisation (optional)
        da, da_concept, da_fact = _extract_concept_value(
            us_gaap_facts, _DA_CONCEPTS, _MONETARY_UNIT, fy
        )
        if da is not None and da_concept and da_fact:
            field_sources["depreciation_amortization"] = {
                "concept": da_concept,
                "form": da_fact.get("form"),
                "fy": fy,
                "filed": da_fact.get("filed"),
                "accn": da_fact.get("accn"),
            }

        # Derived fields
        free_cash_flow: float | None = None
        if cfo is not None and capex is not None:
            free_cash_flow = cfo - abs(capex)
            field_sources["free_cash_flow"] = {"derivation": "cfo - abs(capex)"}
        else:
            missing.append("free_cash_flow")

        ebit: float | None = operating_income  # conservative fallback
        if ebit is not None and "operating_income" not in missing:
            field_sources.setdefault("ebit", {"derivation": "operating_income"})

        ebitda: float | None = None
        if ebit is not None and da is not None:
            ebitda = ebit + da
            field_sources["ebitda"] = {"derivation": "ebit + depreciation_amortization"}

        # Phase 10A: skip year if we have nothing meaningful
        if revenue is None and net_income is None and total_assets is None:
            logger.debug(
                "SEC: skipping FY %d for %s — no meaningful fields", fy, ticker
            )
            continue

        metadata: dict[str, Any] = {
            "source_provider": "sec_edgar",
            "source_endpoint": "companyfacts",
            "fallback_reason": fallback_reason,
            "field_sources": field_sources,
            "data_quality": {
                k: "weak_fallback" for k in weak
            },
        }
        if "free_cash_flow" in missing and "free_cash_flow" not in field_sources:
            metadata["data_quality"]["free_cash_flow"] = "unavailable"
        if "diluted_shares" in weak:
            metadata["data_quality"]["diluted_shares"] = "entity_common_stock_shares"
        if "ebitda" in field_sources:
            metadata["data_quality"]["ebitda"] = "derived"
        if "free_cash_flow" in field_sources:
            metadata["data_quality"]["free_cash_flow"] = "derived"

        row: dict[str, Any] = {
            "company_id": company_id,
            "fiscal_year": fy,
            "fiscal_period": "annual",
            "period_end_date": period_end,
            "currency": _MONETARY_UNIT,  # SEC companyfacts monetary facts are always USD
            "source": "sec_edgar",
            "restated_flag": False,
            "revenue": revenue,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "ebit": ebit,
            "ebitda": ebitda,
            "net_income": net_income,
            "cfo": cfo,
            "capex": capex,
            "free_cash_flow": free_cash_flow,
            "depreciation_amortization": da,
            "stock_based_compensation": None,  # not mapped in Phase 10A
            "cash_and_equivalents": cash,
            "total_debt": total_debt,
            "lease_liabilities": None,
            "minority_interest": None,
            "preferred_equity": None,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "receivables": None,
            "inventory": None,
            "payables": None,
            "diluted_shares": diluted_shares,
            "metadata": metadata,
        }
        if raw_payload_id:
            row["raw_payload_id"] = raw_payload_id

        rows.append(row)

        # Accumulate diagnostics across years
        for field in missing:
            if field not in diagnostics["missing_fields"]:
                diagnostics["missing_fields"].append(field)
        for field in weak:
            if field not in diagnostics["weak_fallbacks"]:
                diagnostics["weak_fallbacks"].append(field)

    diagnostics["rows_normalized"] = len(rows)
    logger.debug(
        "SEC companyfacts: normalised %d annual rows for %s", len(rows), ticker
    )
    return rows, diagnostics


# ── Fallback trigger helpers ──────────────────────────────────────────────────


def fmp_statements_need_fallback(
    inc_resp: Any,
    bal_resp: Any,
    cf_resp: Any,
    stmt_rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Return (True, reason_code) when SEC fallback should be attempted.

    Triggers when:
    - any FMP statement endpoint returns HTTP 402 or 403
    - all FMP statement payloads are empty/None
    - FMP normalisation produced zero usable annual rows

    "Usable annual row" means the row has fiscal_year and period_end_date and
    at least one meaningful financial field.
    """
    # 402 or 403 on any of the three FMP statement calls
    for resp in (inc_resp, bal_resp, cf_resp):
        if resp is not None and resp.status_code in (402, 403):
            return True, f"fmp_{resp.status_code}"

    # All three payloads empty or missing
    all_empty = all(
        not (getattr(r, "payload", None)) for r in (inc_resp, bal_resp, cf_resp)
        if r is not None
    )
    if all_empty:
        return True, "fmp_empty_payload"

    # Zero usable annual rows after normalisation
    usable = _count_usable_annual_rows(stmt_rows)
    if usable == 0:
        return True, "fmp_normalized_zero_rows"

    return False, ""


def _count_usable_annual_rows(rows: list[dict[str, Any]]) -> int:
    """Count rows that have fiscal_year, period_end_date, and one meaningful field."""
    _meaningful = {
        "revenue", "net_income", "cfo", "free_cash_flow",
        "total_assets", "total_equity", "operating_income",
    }
    count = 0
    for row in rows:
        if not row.get("fiscal_year") or not row.get("period_end_date"):
            continue
        if row.get("fiscal_period") not in ("annual", "FY"):
            continue
        if any(row.get(f) is not None for f in _meaningful):
            count += 1
    return count
