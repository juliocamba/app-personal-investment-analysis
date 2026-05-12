"""Daily pipeline runner.

Usage:
    python scripts/run_daily_pipeline.py
    python scripts/run_daily_pipeline.py --dry-run
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Allow running as a top-level script before the package is installed.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import typer
from rich.console import Console

from investment_app.config.loader import load_providers, load_watchlist
from investment_app.config.settings import get_settings, _is_placeholder
from investment_app.utils.logging import configure_logging

app = typer.Typer(add_completion=False)
console = Console()
logger = logging.getLogger(__name__)

# Currencies to fetch from ECB in every run.
_ECB_CURRENCIES = ("USD", "GBP", "JPY", "CHF")


def _provider_enabled(providers_config: dict[str, Any], provider_name: str) -> bool:
    """Return True when the provider is enabled in providers.yml."""
    providers = providers_config.get("providers", {})
    provider_config = providers.get(provider_name, {})
    return bool(provider_config.get("enabled", False))


def _load_watchlist_companies() -> list[dict[str, Any]]:
    """Return the YAML watchlist companies list."""
    watchlist = load_watchlist()
    return watchlist.get("companies", [])


def _load_live_companies(repo_module: Any) -> tuple[list[dict[str, Any]], str]:
    """Load companies from Supabase watchlist, falling back to YAML on failure.

    Phase 9A authority model (two tiers only)
    -----------------------------------------
    1. ``list_watchlist_active_companies()`` — sole eligibility source.
       ``watchlist_companies.active = true`` is the authoritative state.

       * Success with a non-empty list → process those companies.
       * Success with an **empty** list → process zero companies.  This is an
         intentional "all removed" state; YAML is NOT consulted.

    2. YAML watchlist (``watchlist.yml``) — technical fallback only.
       Reached only when ``list_watchlist_active_companies()`` raises (e.g.
       Supabase unreachable, wrong credentials).  ``companies.active`` is
       never consulted as a fallback.
    """
    try:
        companies = repo_module.list_watchlist_active_companies()
        # Empty list is authoritative: all memberships were soft-removed.
        return companies, "supabase-watchlist"
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load companies via watchlist_companies: %s — "
            "falling back to YAML watchlist",
            exc,
        )
    return _load_watchlist_companies(), "watchlist-fallback"


def _resolve_company_id(company: dict[str, Any], repo_module: Any) -> str | None:
    """Resolve the company UUID from the row itself or by ticker lookup."""
    company_id = company.get("id")
    if company_id:
        return company_id
    ticker = company.get("ticker", "")
    if not ticker:
        return None
    match = repo_module.get_company_by_ticker(ticker)
    if not match:
        return None
    return match.get("id")


def _extract_company_profile_update(payload: Any) -> dict[str, Any] | None:
    """Map the first FMP profile entry into the ``companies`` table shape."""
    if isinstance(payload, list) and payload:
        profile = payload[0]
    elif isinstance(payload, dict):
        profile = payload
    else:
        return None

    if not isinstance(profile, dict):
        return None

    update: dict[str, Any] = {}
    mapping = {
        "companyName": "name",
        "country": "country",
        "currency": "currency",
        "sector": "sector",
        "industry": "industry",
        "cik": "cik",
    }
    for source_key, target_key in mapping.items():
        value = profile.get(source_key)
        if value:
            update[target_key] = value

    exchange = profile.get("exchangeShortName") or profile.get("exchange")
    if exchange:
        update["exchange"] = exchange

    return update or None


def _build_news_query(company: dict[str, Any]) -> str:
    """Build a simple GDELT query from company name and ticker."""
    ticker = company.get("ticker", "")
    name = company.get("name", "")
    if name and ticker:
        return f'"{name}" OR {ticker}'
    return name or ticker


def _build_sec_document_url(
    cik: str | int | None,
    accession_number: str | None,
    primary_document: str | None,
) -> str | None:
    """Build a full SEC archive document URL when the payload contains enough data."""
    if not cik or not accession_number or not primary_document:
        return None
    cik_str = str(cik).lstrip("0")
    accession_no_dashes = accession_number.replace("-", "")
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_str}/{accession_no_dashes}/{primary_document}"
    )


def _run_live_pipeline(
    *,
    repo_module: Any,
    providers_config: dict[str, Any],
    fmp: Any | None,
    sec: Any | None,
    ecb: Any | None,
    gdelt: Any | None,
    store_raw_response_fn: Any,
    normalize_prices_fn: Any,
    normalize_statements_fn: Any,
    normalize_news_fn: Any,
    compute_features_fn: Any | None = None,
    compute_valuation_fn: Any | None = None,
    compute_qualitative_fn: Any | None = None,
    compute_signal_fn: Any | None = None,
    process_alerts_fn: Any | None = None,
    settings: Any | None = None,
) -> dict[str, int]:
    """Run the live ingestion and Phases 3-7 pipeline flow."""
    pipeline_run = repo_module.insert_pipeline_run(run_type="daily")
    run_id = pipeline_run["id"]
    metrics: dict[str, int] = {
        "companies_processed": 0,
        "profiles_updated": 0,
        "prices_upserted": 0,
        "statements_upserted": 0,
        "filings_upserted": 0,
        "fx_rates_upserted": 0,
        "news_upserted": 0,
        "ratios_upserted": 0,
        "valuation_runs_upserted": 0,
        "qualitative_scores_upserted": 0,
        "signal_runs_upserted": 0,
        "alerts_sent": 0,
        "alert_history_written": 0,
        "alerts_deduplicated": 0,
    }

    try:
        companies, company_source = _load_live_companies(repo_module)
        console.print(f"Watchlist   : {len(companies)} companies")
        repo_module.log_pipeline_event(
            run_id,
            stage="startup",
            message=f"Loaded {len(companies)} active companies from {company_source}.",
        )

        if not companies:
            repo_module.finish_pipeline_run(
                run_id,
                status="success",
                message="No active companies found.",
                metrics=metrics,
            )
            return metrics

        gdelt_enabled = _provider_enabled(providers_config, "gdelt") and gdelt is not None
        if not gdelt_enabled:
            repo_module.log_pipeline_event(
                run_id,
                stage="news",
                message="News ingestion skipped because GDELT is disabled.",
            )

        for company in companies:
            ticker: str = company.get("ticker", "")
            cik: str = company.get("cik", "")
            currency: str = company.get("currency", "USD")
            company_id = _resolve_company_id(company, repo_module)

            if not company_id:
                repo_module.log_pipeline_event(
                    run_id,
                    stage="company",
                    level="warning",
                    message=f"Skipping {ticker or 'unknown'} because no company row was found.",
                )
                continue

            repo_module.log_pipeline_event(
                run_id,
                stage="company",
                message=f"Processing {ticker}.",
                company_id=company_id,
            )

            try:
                if fmp is not None:
                    profile_resp = fmp.get_profile(ticker)
                    profile_raw_id = store_raw_response_fn(profile_resp, company_id)
                    if profile_resp.success and profile_resp.payload:
                        profile_update = _extract_company_profile_update(profile_resp.payload)
                        if profile_update:
                            repo_module.update_company_profile(company_id, profile_update)
                            metrics["profiles_updated"] += 1

                    price_resp = fmp.get_historical_prices(ticker)
                    price_raw_id = store_raw_response_fn(price_resp, company_id)
                    if price_resp.success and price_resp.payload:
                        price_rows = normalize_prices_fn(
                            price_resp.payload,
                            company_id,
                            ticker,
                            currency,
                            price_raw_id,
                        )
                        metrics["prices_upserted"] += repo_module.upsert_price_eod(price_rows)

                    inc_resp = fmp.get_income_statement(ticker, period="annual", limit=5)
                    bal_resp = fmp.get_balance_sheet(ticker, period="annual", limit=5)
                    cf_resp = fmp.get_cash_flow(ticker, period="annual", limit=5)
                    for resp in (inc_resp, bal_resp, cf_resp):
                        store_raw_response_fn(resp, company_id)
                    stmt_rows = normalize_statements_fn(
                        inc_resp.payload,
                        bal_resp.payload,
                        cf_resp.payload,
                        company_id,
                        ticker,
                        currency,
                    )
                    metrics["statements_upserted"] += repo_module.upsert_statements_norm(
                        stmt_rows
                    )

                if sec is not None and cik:
                    sub_resp = sec.get_submissions(cik)
                    sub_raw_id = store_raw_response_fn(sub_resp, company_id)
                    if sub_resp.success and sub_resp.payload:
                        filing_rows = _extract_filings_index(
                            sub_resp.payload,
                            company_id,
                            ticker,
                            raw_payload_id=sub_raw_id,
                        )
                        metrics["filings_upserted"] += repo_module.upsert_filings_index(
                            filing_rows
                        )

                    facts_resp = sec.get_company_facts(cik)
                    store_raw_response_fn(facts_resp, company_id)

                if gdelt_enabled:
                    news_resp = gdelt.search_news(_build_news_query(company), max_records=10)
                    news_raw_id = store_raw_response_fn(news_resp, company_id)
                    if news_resp.success and news_resp.payload:
                        news_rows = normalize_news_fn(
                            news_resp.payload,
                            company_id,
                            ticker,
                            news_raw_id,
                        )
                        metrics["news_upserted"] += repo_module.upsert_news_events(news_rows)

                metrics["companies_processed"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("Error processing %s (%s)", ticker, type(exc).__name__)
                repo_module.log_pipeline_event(
                    run_id,
                    stage="company",
                    level="error",
                    company_id=company_id,
                    message=f"Error processing {ticker}.",
                    details={"error_type": type(exc).__name__},
                )
                console.print(f"  [red]Error for {ticker}: {type(exc).__name__}[/red]")

        if ecb is not None:
            repo_module.log_pipeline_event(
                run_id,
                stage="fx",
                message="Fetching ECB FX rates.",
            )
            for currency in _ECB_CURRENCIES:
                try:
                    fx_resp = ecb.get_fx_rate(currency, last_n=5)
                    store_raw_response_fn(fx_resp, company_id=None)
                    if fx_resp.success and fx_resp.payload:
                        fx_rows = _extract_ecb_fx_rates(fx_resp.payload, currency)
                        metrics["fx_rates_upserted"] += repo_module.upsert_fx_rates(fx_rows)
                except Exception as exc:  # noqa: BLE001
                    logger.error("ECB FX fetch failed for %s (%s)", currency, type(exc).__name__)
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="fx",
                        level="error",
                        message=f"FX fetch failed for {currency}.",
                        details={"error_type": type(exc).__name__, "currency": currency},
                    )

        # ── Phase 3: feature / ratio computation ─────────────────────────────────
        # factor_date is shared by Phases 3, 4, and 5; initialise it here so
        # later stanzas can use it even when earlier phases are skipped.
        from datetime import date as _date

        factor_date = _date.today().isoformat()

        if compute_features_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="features",
                message="Starting ratio and feature computation.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                currency: str = company.get("currency", "USD")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    ratio_row = compute_features_fn(
                        company_id, repo_module, factor_date,
                        company_currency=currency,
                    )
                    if ratio_row:
                        n = repo_module.upsert_ratios_factors([ratio_row])
                        metrics["ratios_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="features",
                            company_id=company_id,
                            message=f"Ratios computed for {ticker}.",
                            details={"factor_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="features",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped ratios for {ticker}: "
                                "insufficient data."
                            ),
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Feature computation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="features",
                        level="error",
                        company_id=company_id,
                        message=f"Ratio computation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 4: valuation ────────────────────────────────────────────────
        if compute_valuation_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="valuation",
                message="Starting valuation computation.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                currency: str = company.get("currency", "USD")
                sector: str = company.get("sector", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    skip_diag: dict[str, Any] = {}
                    valuation_row = compute_valuation_fn(
                        company_id,
                        repo_module,
                        factor_date,
                        sector=sector,
                        company_currency=currency,
                        diagnostics_out=skip_diag,
                    )
                    if valuation_row:
                        n = repo_module.upsert_valuation_run([valuation_row])
                        metrics["valuation_runs_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="valuation",
                            company_id=company_id,
                            message=f"Valuation computed for {ticker}.",
                            details={"valuation_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="valuation",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped valuation for {ticker}: "
                                "insufficient data."
                            ),
                            details={"ticker": ticker, **skip_diag},
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Valuation computation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="valuation",
                        level="error",
                        company_id=company_id,
                        message=f"Valuation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 5: qualitative scoring ──────────────────────────────────────
        if compute_qualitative_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="qualitative",
                message="Starting qualitative scoring.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    qual_row = compute_qualitative_fn(
                        company_id,
                        repo_module,
                        factor_date,
                    )
                    if qual_row:
                        n = repo_module.upsert_qualitative_scores([qual_row])
                        metrics["qualitative_scores_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="qualitative",
                            company_id=company_id,
                            message=f"Qualitative score computed for {ticker}.",
                            details={"score_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="qualitative",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped qualitative score for {ticker}: "
                                "insufficient data."
                            ),
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Qualitative scoring failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="qualitative",
                        level="error",
                        company_id=company_id,
                        message=f"Qualitative scoring failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 6: probabilistic signal ───────────────────────────────────
        if compute_signal_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="signal",
                message="Starting probabilistic signal scoring.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    signal_row = compute_signal_fn(
                        company_id,
                        repo_module,
                        factor_date,
                    )
                    if signal_row:
                        n = repo_module.upsert_signal_runs([signal_row])
                        metrics["signal_runs_upserted"] += n
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="signal",
                            company_id=company_id,
                            message=f"Signal computed for {ticker}.",
                            details={"signal_date": factor_date},
                        )
                    else:
                        repo_module.log_pipeline_event(
                            run_id,
                            stage="signal",
                            level="warning",
                            company_id=company_id,
                            message=(
                                f"Skipped signal for {ticker}: "
                                "insufficient data."
                            ),
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Signal computation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="signal",
                        level="error",
                        company_id=company_id,
                        message=f"Signal computation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        # ── Phase 7: alerts ─────────────────────────────────────────────────
        if process_alerts_fn is not None and companies:
            repo_module.log_pipeline_event(
                run_id,
                stage="alerts",
                message="Starting alert evaluation.",
            )
            for company in companies:
                ticker: str = company.get("ticker", "")
                company_id = _resolve_company_id(company, repo_module)
                if not company_id:
                    continue
                try:
                    alert_metrics = process_alerts_fn(
                        company_id,
                        repo_module,
                        factor_date,
                        company=company,
                        settings=settings,
                    )
                    metrics["alerts_sent"] += int(alert_metrics.get("alerts_sent", 0))
                    metrics["alert_history_written"] += int(
                        alert_metrics.get("alert_history_written", 0)
                    )
                    metrics["alerts_deduplicated"] += int(
                        alert_metrics.get("alerts_deduplicated", 0)
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="alerts",
                        company_id=company_id,
                        message=f"Alerts evaluated for {ticker}.",
                        details=alert_metrics,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Alert evaluation failed for %s (%s)",
                        ticker,
                        type(exc).__name__,
                    )
                    repo_module.log_pipeline_event(
                        run_id,
                        stage="alerts",
                        level="error",
                        company_id=company_id,
                        message=f"Alert evaluation failed for {ticker}.",
                        details={"error_type": type(exc).__name__},
                    )

        repo_module.finish_pipeline_run(
            run_id,
            status="success",
            message="Pipeline complete.",
            metrics=metrics,
        )
        return metrics
    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline failed (%s)", type(exc).__name__)
        repo_module.log_pipeline_event(
            run_id,
            stage="pipeline",
            level="error",
            message="Pipeline failed.",
            details={"error_type": type(exc).__name__},
        )
        repo_module.finish_pipeline_run(
            run_id,
            status="failed",
            message="Pipeline failed.",
            metrics=metrics,
        )
        raise


@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Load config only; do not fetch data."),
) -> None:
    """Run the daily investment-analysis pipeline."""
    settings = get_settings()
    configure_logging(settings.log_level)

    mode = "DRY RUN" if dry_run else "LIVE"
    console.print(f"[bold cyan]Daily pipeline starting ({mode})…[/bold cyan]")
    console.print(f"Environment : {settings.app_env}")

    if not dry_run:
        missing = settings.missing_required()
        if missing:
            console.print("[bold red]Pipeline aborted: missing required configuration.[/bold red]")
            for name in missing:
                console.print(f"  - [yellow]{name.upper()}[/yellow]")
            raise typer.Exit(code=1)

    if dry_run:
        companies = _load_watchlist_companies()
        providers_config = load_providers()
        console.print(f"Watchlist   : {len(companies)} companies")
        console.print("[bold]Would fetch:[/bold]")
        for company in companies:
            ticker = company.get("ticker", "?")
            cik = company.get("cik", "")
            console.print(f"  FMP profile / prices / statements : {ticker}")
            if cik:
                console.print(f"  SEC filings              : {ticker} (CIK {cik})")
        for currency in _ECB_CURRENCIES:
            console.print(f"  ECB FX rate              : EUR/{currency}")
        if _provider_enabled(providers_config, "gdelt"):
            console.print("  GDELT news               : enabled")
        else:
            console.print("  GDELT news               : skipped (disabled in providers.yml)")
        console.print("  Ratio computation      : would compute ratios_factors for each company")
        console.print("  Valuation computation  : would compute valuation_runs for each company")
        console.print("  Qualitative scoring    : would compute qualitative_scores for each company")
        console.print("  Signal scoring         : would compute signal_runs for each company")
        console.print("  Alert evaluation       : would evaluate alert_rules and write alert_history")
        console.print("[yellow]Dry run complete — no data was fetched.[/yellow]")
        return

    # ── Live mode ──────────────────────────────────────────────────────────────
    from investment_app.connectors.ecb import ECBConnector
    from investment_app.connectors.fmp import FMPConnector
    from investment_app.connectors.gdelt import GDELTConnector
    from investment_app.connectors.sec_edgar import SECEdgarConnector
    from investment_app.alerts import process_company_alerts
    from investment_app.db import repositories as repo
    from investment_app.etl.normalize_news import normalize_gdelt_news
    from investment_app.etl.normalize_prices import normalize_fmp_prices
    from investment_app.etl.normalize_statements import normalize_fmp_statements
    from investment_app.etl.raw_store import store_raw_response
    from investment_app.features import compute_all_features
    from investment_app.scoring.probabilistic import compute_signal_run
    from investment_app.scoring.qualitative import compute_qualitative_score
    from investment_app.valuation import compute_valuation_run
    providers_config = load_providers()

    # Check FMP key — warn but continue; many calls may fail but we should not abort.
    fmp_key = settings.fmp_api_key
    fmp_available = (
        _provider_enabled(providers_config, "fmp")
        and not _is_placeholder(fmp_key)
        and bool(fmp_key)
    )
    if not fmp_available:
        console.print(
            "[yellow]Warning: FMP_API_KEY not set — price/statement ingestion will be skipped.[/yellow]"
        )

    sec_user_agent = settings.sec_user_agent
    sec_available = (
        _provider_enabled(providers_config, "sec_edgar")
        and not _is_placeholder(sec_user_agent)
        and bool(sec_user_agent)
    )
    if not sec_available:
        console.print(
            "[yellow]Warning: SEC_USER_AGENT not set — SEC filing ingestion will be skipped.[/yellow]"
        )

    # Initialise connectors.
    fmp: FMPConnector | None = FMPConnector(fmp_key) if fmp_available else None
    sec: SECEdgarConnector | None = (
        SECEdgarConnector(sec_user_agent) if sec_available else None
    )
    ecb = ECBConnector() if _provider_enabled(providers_config, "ecb") else None
    gdelt = (
        GDELTConnector() if _provider_enabled(providers_config, "gdelt") else None
    )

    metrics = _run_live_pipeline(
        repo_module=repo,
        providers_config=providers_config,
        fmp=fmp,
        sec=sec,
        ecb=ecb,
        gdelt=gdelt,
        store_raw_response_fn=store_raw_response,
        normalize_prices_fn=normalize_fmp_prices,
        normalize_statements_fn=normalize_fmp_statements,
        normalize_news_fn=normalize_gdelt_news,
        compute_features_fn=compute_all_features,
        compute_valuation_fn=compute_valuation_run,
        compute_qualitative_fn=compute_qualitative_score,
        compute_signal_fn=compute_signal_run,
        process_alerts_fn=process_company_alerts,
        settings=settings,
    )

    console.print("[bold green]Pipeline complete.[/bold green]")
    for key, value in metrics.items():
        console.print(f"  {key}: {value}")


# ── Helper functions ───────────────────────────────────────────────────────────


def _extract_filings_index(
    payload: dict[str, Any],
    company_id: str,
    ticker: str,
    raw_payload_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract recent 10-K / 10-Q filings from SEC submissions payload."""
    rows: list[dict[str, Any]] = []
    filings: dict[str, Any] = payload.get("filings", {}).get("recent", {})
    cik = payload.get("cik")
    forms: list[str] = filings.get("form", [])
    accessions: list[str] = filings.get("accessionNumber", [])
    dates: list[str] = filings.get("filingDate", [])
    descriptions: list[str] = filings.get("primaryDocument", [])

    target_forms = {"10-K", "10-Q", "20-F"}
    for i, form in enumerate(forms):
        if form not in target_forms:
            continue
        try:
            rows.append(
                {
                    "company_id": company_id,
                    "source": "sec_edgar",
                    "filing_type": form,
                    "accession_number": accessions[i] if i < len(accessions) else None,
                    "filing_date": dates[i] if i < len(dates) else None,
                    "document_url": _build_sec_document_url(
                        cik,
                        accessions[i] if i < len(accessions) else None,
                        descriptions[i] if i < len(descriptions) else None,
                    ),
                }
            )
            if raw_payload_id:
                rows[-1]["raw_payload_id"] = raw_payload_id
        except (IndexError, KeyError):
            logger.debug("Skipping malformed filing index entry for %s index %d", ticker, i)
    return rows


def _extract_ecb_fx_rates(
    payload: dict[str, Any], quote_currency: str
) -> list[dict[str, Any]]:
    """Parse ECB JSON data format into ``fx_rates`` rows."""
    rows: list[dict[str, Any]] = []
    try:
        datasets: list[dict[str, Any]] = payload.get("dataSets", [])
        if not datasets:
            return rows
        series_key = list(datasets[0].get("series", {}).keys())
        if not series_key:
            return rows
        observations: dict[str, list[Any]] = (
            datasets[0]["series"][series_key[0]].get("observations", {})
        )
        # Map period index to date string from structure.
        structure = payload.get("structure", {})
        time_periods: list[str] = (
            structure.get("dimensions", {}).get("observation", [{}])[-1].get("values", [])
        )
        for idx_str, obs_list in observations.items():
            idx = int(idx_str)
            rate_val = obs_list[0] if obs_list else None
            date_str = time_periods[idx]["id"] if idx < len(time_periods) else None
            if rate_val is None or date_str is None:
                continue
            try:
                rows.append(
                    {
                        "rate_date": date_str,
                        "base_currency": "EUR",
                        "quote_currency": quote_currency,
                        "rate": float(rate_val),
                        "provider": "ecb",
                    }
                )
            except (TypeError, ValueError):
                continue
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Failed to parse ECB FX payload for %s: %s", quote_currency, exc)
    return rows


if __name__ == "__main__":
    app()

