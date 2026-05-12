# 02 — Repository Structure

## Recommended mono-repo layout

```text
investment-analysis-mvp/
  README.md
  pyproject.toml
  requirements.txt
  .env.example
  .gitignore
  configs/
    watchlist.example.yml
    providers.yml
    valuation_defaults.yml
    scoring_weights.yml
  src/
    investment_app/
      __init__.py
      cli.py
      config/
        settings.py
        loader.py
      db/
        supabase_client.py
        repositories.py
      connectors/
        base.py
        sec_edgar.py
        fmp.py
        finnhub.py
        alpha_vantage.py
        ecb.py
        gdelt.py
      etl/
        raw_store.py
        normalize_prices.py
        normalize_statements.py
        normalize_news.py
      features/
        ratios.py
        quality_features.py
        market_features.py
        news_features.py
      valuation/
        dcf.py
        multiples.py
        dividend_discount.py
        financials.py
        scenarios.py
      scoring/
        qualitative.py
        rule_based.py
        probabilistic.py
        explanations.py
      alerts/
        email_alerts.py
        telegram_alerts.py
        rules.py
      utils/
        logging.py
        retry.py
        dates.py
        checksum.py
  scripts/
    run_daily_pipeline.py
    run_backfill.py
    run_backtest.py
    validate_supabase_schema.py
  tests/
    unit/
    integration/
    fixtures/
  sql/
    001_initial_schema.sql
    002_rls_policies.sql
    003_views_and_functions.sql
    004_seed_watchlist_example.sql
  frontend/
    package.json
    vite.config.ts
    src/
      main.tsx
      App.tsx
      lib/supabase.ts
      pages/
      components/
  .github/
    workflows/
      daily_pipeline.yml
      frontend_deploy.yml
```

## Repository rules for coding agents

1. Do not implement multiple phases in one large change.
2. Do not change SQL schema without updating documentation.
3. Do not place API keys in code.
4. Do not call providers from frontend.
5. Add or update tests for each new module.
6. Keep functions small and typed.
7. Use deterministic fixtures for tests.
8. Every pipeline run must create a `pipeline_runs` record.
9. Every model run must store a version string.
10. Every alert must be deduplicated.

## Python packaging

Use a standard package layout under `src/investment_app`.

Recommended `pyproject.toml` dependencies:

```toml
[project]
name = "investment-analysis-mvp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.0",
  "pydantic-settings>=2.0",
  "httpx>=0.27",
  "tenacity>=8.2",
  "pandas>=2.2",
  "numpy>=1.26",
  "scikit-learn>=1.4",
  "supabase>=2.0",
  "python-dotenv>=1.0",
  "typer>=0.12",
  "rich>=13.0",
  "pyyaml>=6.0"
]
```

## Configuration files

### `configs/watchlist.example.yml`

```yaml
companies:
  - ticker: AAPL
    name: Apple Inc.
    exchange: NASDAQ
    country: US
    currency: USD
    reporting_currency: USD
    cik: "0000320193"
    sector: Technology
    industry: Consumer Electronics
    active: true
  - ticker: MSFT
    name: Microsoft Corporation
    exchange: NASDAQ
    country: US
    currency: USD
    reporting_currency: USD
    cik: "0000789019"
    sector: Technology
    industry: Software
    active: true
```

### `configs/valuation_defaults.yml`

```yaml
defaults:
  explicit_forecast_years: 5
  terminal_growth_floor: 0.01
  terminal_growth_cap: 0.03
  tax_rate_fallback: 0.25
  scenario_weights:
    bear: 0.25
    base: 0.50
    bull: 0.25
  margin_of_safety:
    strong_buy: 0.15
    buy: 0.10
```

### `configs/scoring_weights.yml`

```yaml
rule_score_weights:
  valuation: 0.40
  quality: 0.25
  balance_sheet: 0.15
  news: 0.10
  market_regime: 0.10
qualitative_weights:
  moat: 0.35
  management: 0.25
  risks: 0.25
  governance: 0.15
```
