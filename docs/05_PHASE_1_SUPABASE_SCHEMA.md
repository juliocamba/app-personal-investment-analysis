# 05 — Phase 1: Supabase Schema

## Objective

Create and validate the Supabase database schema required by the MVP.

## Scope

This phase focuses on database setup only.

## Inputs

Use SQL files:

1. `sql/001_initial_schema.sql`
2. `sql/002_rls_policies.sql`
3. `sql/003_views_and_functions.sql`
4. `sql/004_seed_watchlist_example.sql`

## Agent instructions

Implement only Supabase connectivity and schema validation. Do not implement data ingestion yet.

## Tasks

### 1. Copy SQL files into project

Place all SQL files under the project `sql/` folder.

### 2. Create Supabase client module

Implement:

- `src/investment_app/db/supabase_client.py`
- `src/investment_app/db/repositories.py`

Client requirements:

- use `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` for backend scripts;
- expose a function `get_supabase_client()`;
- do not instantiate client at import time if it makes tests difficult.

### 3. Create schema validation script

Implement `scripts/validate_supabase_schema.py`.

It should verify that these tables exist:

- `companies`
- `watchlists`
- `watchlist_companies`
- `raw_provider_payloads`
- `price_eod`
- `filings_index`
- `statements_norm`
- `ratios_factors`
- `qualitative_scores`
- `valuation_runs`
- `signal_runs`
- `alert_rules`
- `alert_history`
- `pipeline_runs`

Validation strategy:

- query `information_schema.tables` through a SQL RPC if available; or
- use Supabase REST select calls against each table with limit 1.

### 4. Create repository methods

Add minimal repository methods:

```python
list_active_companies()
get_company_by_ticker(ticker: str)
insert_pipeline_run(...)
finish_pipeline_run(...)
log_pipeline_event(...)
```

### 5. Seed data

Use `004_seed_watchlist_example.sql` as an example only. Update the user email before running it.

## Acceptance criteria

- SQL files run successfully in Supabase.
- RLS is enabled.
- Dashboard view `dashboard_watchlist_latest` exists.
- `python scripts/validate_supabase_schema.py` succeeds.
- Repository methods are tested with mocks.

## Suggested commit message

```text
feat: add supabase schema and repository foundation
```
