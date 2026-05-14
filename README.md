# Investment Analysis MVP

A private research application that tracks a watchlist of public companies, ingests market and filing data, computes daily analytics, and exposes the latest results in a Supabase-backed dashboard.

This repository contains both the Python backend pipeline and the React frontend.

For implementation detail, schema notes, RLS behavior, and the operational model, see [README-TECHNICAL.md](README-TECHNICAL.md).

## Project overview

The app is designed for a single-operator or small trusted-user deployment.

It combines:

- provider ingestion from FMP Stable API, SEC EDGAR, and ECB FX;
- a Supabase/Postgres analytical store with Row Level Security;
- a daily Python pipeline for ingestion, normalization, analytics, and alerts;
- a React + Vite dashboard that reads from Supabase using the anon key plus Supabase Auth.

## What the app does

On each pipeline run, the system can:

- refresh company profile, price, statement, filing, and FX data;
- store raw provider payloads before normalization;
- compute ratios and features;
- compute valuation ranges and margin of safety outputs;
- compute qualitative scores;
- compute probabilistic buy, hold, and sell signals;
- optionally evaluate alerts;
- keep watchlist history intact when companies are removed or reactivated.

## Current MVP capabilities

- Supabase schema is applied and validated.
- FMP Stable API ingestion works.
- SEC EDGAR ingestion works.
- ECB FX ingestion works.
- Daily pipeline runs successfully.
- Dashboard works locally.
- Phase 9A watchlist active-membership management is implemented and manually tested.
- Phase 9B add-new-company request flow is implemented and ready; manual testing is in progress.
- Alerts exist but remain disabled by default.
- Cloudflare Pages deployment is planned.
- GitHub Actions daily pipeline is included in the repo and is configurable once secrets are set.

## High-level architecture

| Layer | Role |
|---|---|
| Python backend | Ingests provider data, stores raw payloads, normalizes data, computes analytics, writes results |
| Supabase / Postgres | Operational database, analytical tables, views, RLS, auth-backed frontend access |
| GitHub Actions | Planned scheduler/runner for the daily pipeline and manual workflow dispatch |
| React + Vite frontend | Dashboard UI for watchlist, add requests, and alert history |
| Cloudflare Pages | Planned static hosting target for the frontend |

## Main stack

| Component | Technology |
|---|---|
| Backend language | Python 3.11+ |
| Database | Supabase / PostgreSQL |
| Scheduler | GitHub Actions |
| Frontend | React 18 + Vite 5 + TypeScript |
| Frontend hosting | Cloudflare Pages |
| Market/provider data | FMP Stable API |
| Filings | SEC EDGAR |
| FX rates | ECB FX |

## Safe setup summary

1. Copy `.env.example` to `.env` and fill in placeholder values with your own secrets locally.
2. Copy `frontend/.env.example` to `frontend/.env` and set only the public Supabase frontend variables.
3. Create the Python virtual environment and install backend dependencies.
4. Install frontend dependencies in `frontend/`.
5. Apply the SQL migrations in order in Supabase.
6. Validate the schema.
7. Run the pipeline in `--dry-run` mode first.
8. Start the frontend locally and sign in with a Supabase Auth user.

On Linux or macOS, the commands are equivalent but activation paths differ.

## Required environment variables

Use placeholders only. Never commit real values.

### Backend `.env`

| Variable | Example placeholder | Purpose |
|---|---|---|
| `APP_ENV` | `local` | Runtime environment |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `SUPABASE_URL` | `https://your-project.supabase.co` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | `replace_me` | Backend-only Supabase key |
| `SUPABASE_ANON_KEY` | `replace_me` | Public Supabase anon key |
| `DATA_PROVIDER_PRIMARY` | `fmp` | Primary market-data provider |
| `FMP_API_KEY` | `replace_me` | FMP Stable API key |
| `SEC_USER_AGENT` | `InvestmentAnalysisMVP your_email@example.com` | SEC EDGAR required identifier |
| `SMTP_ENABLED` | `false` | Email alert toggle |
| `SMTP_HOST` | `smtp.example.com` | SMTP host |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | `replace_me` | SMTP username |
| `SMTP_PASSWORD` | `replace_me` | SMTP password |
| `ALERT_EMAIL_FROM` | `alerts@example.com` | Sender address |
| `ALERT_EMAIL_TO` | `operator@example.com` | Recipient address |
| `TELEGRAM_ENABLED` | `false` | Telegram alert toggle |
| `TELEGRAM_BOT_TOKEN` | `replace_me` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | `replace_me` | Telegram destination |
| `ALERTS_ENABLED` | `false` | Master alert switch |

Additional provider keys such as `FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`, and `TWELVE_DATA_API_KEY` exist in the template but only need to be set if you actually use them.

### Frontend `frontend/.env`

| Variable | Example placeholder | Purpose |
|---|---|---|
| `VITE_SUPABASE_URL` | `https://your-project.supabase.co` | Public Supabase URL for browser client |
| `VITE_SUPABASE_ANON_KEY` | `replace_me` | Public anon key for browser client |

## Local backend setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

Copy-Item .env.example .env

investment-app health
investment-app config-check
```

## Local frontend setup

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Local frontend URL: `http://localhost:5173`

## Running the pipeline

Use the daily pipeline entry point in [scripts/run_daily_pipeline.py](scripts/run_daily_pipeline.py).

### Dry-run

```powershell
.\.venv\Scripts\python scripts\run_daily_pipeline.py --dry-run
```

Dry-run validates configuration and prints the planned stages without writing provider-derived results.

### Live run

```powershell
.\.venv\Scripts\python scripts\run_daily_pipeline.py
```

The live run processes pending add-company requests, loads the active watchlist, ingests provider data, computes analytics, and optionally evaluates alerts.

## Running tests

### Backend

```powershell
.\.venv\Scripts\python -m pytest
```

### Frontend

```powershell
Set-Location frontend
npm test
npm run build
```

Use `npm run test:watch` in `frontend/` for interactive frontend test work.

## Supabase setup summary

Apply the SQL files in order in the Supabase SQL editor:

1. `sql/001_initial_schema.sql`
2. `sql/002_rls_policies.sql`
3. `sql/003_views_and_functions.sql`
4. `sql/004_seed_watchlist_example.sql` (optional sample data)
5. `sql/005_watchlist_management.sql`
6. `sql/006_watchlist_add_requests.sql`

Before using the optional seed file, replace any placeholder email with your own test or operator email in a local copy or directly in the SQL editor. Do not commit personal addresses.

Validate the schema after applying the migrations:

```powershell
.\.venv\Scripts\python scripts\validate_supabase_schema.py
```

## Watchlist management

The dashboard supports two watchlist flows.

### Existing companies

- Companies can be soft-removed from the active watchlist.
- Removed companies can be reactivated later.
- Historical analytical data is preserved; removal does not delete company history.

### Request new company flow

- A user can submit a request with ticker and optional exchange.
- The pipeline validates the request before creating or reusing a company row.
- Approved requests create or reactivate the watchlist membership.
- Ambiguous tickers are rejected unless an exact exchange match can be resolved safely.
- Analysis appears after the next successful pipeline run.

## Alerts

Alerts are present in the MVP but remain disabled by default.

| Setting | Default | Meaning |
|---|---|---|
| `ALERTS_ENABLED` | `false` | Master switch for all alert evaluation |
| `SMTP_ENABLED` | `false` | Enables SMTP delivery when alerts are enabled |
| `TELEGRAM_ENABLED` | `false` | Enables Telegram delivery when alerts are enabled |

When alerts are disabled, no alert evaluation runs and no new `alert_history` rows are written by the alert stage.

## GitHub Actions daily pipeline

The repository includes [.github/workflows/daily_pipeline.yml](.github/workflows/daily_pipeline.yml).

GitHub only executes workflow files placed under `.github/workflows/`. The file at that path is the authoritative, executable workflow.

Current workflow characteristics:

- manual-only via `workflow_dispatch` — weekday cron schedule is disabled;
- fails early with a clear error when required secrets are absent;
- runs unit tests before the live pipeline step;
- validates Supabase schema before running the pipeline;
- requires repository secrets before it can be used safely in production.

Required GitHub Actions secrets:

| Secret | Required | Purpose |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service-role key for backend DB access |
| `SUPABASE_ANON_KEY` | No | Anon key (optional; used if backend logic needs it) |
| `FMP_API_KEY` | Yes | Financial Modeling Prep primary data provider |
| `SEC_USER_AGENT` | Yes | User-agent string for SEC EDGAR requests |
| `ALERTS_ENABLED` | No | Master switch for alert evaluation (`true`/`false`) |
| `SMTP_ENABLED` | No | Enable SMTP delivery (`true`/`false`) |
| `SMTP_HOST` | No | SMTP server hostname |
| `SMTP_PORT` | No | SMTP server port |
| `SMTP_USER` | No | SMTP username |
| `SMTP_PASSWORD` | No | SMTP password |
| `ALERT_EMAIL_FROM` | No | Sender address for email alerts |
| `ALERT_EMAIL_TO` | No | Recipient address for email alerts |
| `TELEGRAM_ENABLED` | No | Enable Telegram delivery (`true`/`false`) |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID |
| `FINNHUB_API_KEY` | No | Optional secondary data provider |
| `ALPHA_VANTAGE_API_KEY` | No | Optional secondary data provider |
| `TWELVE_DATA_API_KEY` | No | Optional secondary data provider |

Only configure provider and alert secrets you actually use.

## Cloudflare Pages deployment

Cloudflare Pages deployment is planned. The intended configuration is:

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm run build` |
| Output directory | `dist` |

Frontend environment variables:

| Variable | Placeholder |
|---|---|
| `VITE_SUPABASE_URL` | `https://your-project.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | `replace_me` |

Do not put `SUPABASE_SERVICE_ROLE_KEY` into Cloudflare Pages.

## Security notes

- Never expose the Supabase service-role key in the frontend.
- The frontend uses the anon key only, together with Supabase Auth.
- RLS is the primary access-control layer for browser access.
- `dashboard_watchlist_latest` and related dashboard views rely on `security_invoker` behavior so access is evaluated as the calling role.
- Do not commit `.env`, `frontend/.env`, API keys, SMTP credentials, or Telegram tokens.
- Provider errors persisted to the database should remain sanitized.

## Current limitations

- The app is designed for a private deployment, not a public multi-tenant product.
- The frontend reads directly from Supabase; there is no separate backend API layer for dashboard queries.
- Cloudflare Pages deployment is documented but not described here as already live.
- GitHub Actions automation depends on repository secrets being configured.
- GDELT/news ingestion is optional and can remain disabled.
- Alerts exist but are intentionally off by default.
- Per-user watchlist isolation beyond the current trusted-user model is not implemented.

## Roadmap / post-MVP ideas

- Cloudflare Pages production deployment.
- GitHub Actions production scheduling and secret management.
- Backfill and reconciliation workflows.
- Per-user watchlist isolation.
- Improved operator dashboards for `pipeline_runs` and provider health.
- Additional valuation diagnostics and model calibration tools.
- Expanded alert rule management in the frontend.

## Phase status

| Phase | Name | Status |
|---|---|---|
| 0 | Project Bootstrap | Complete |
| 1 | Supabase Schema | Complete |
| 2 | Data Ingestion | Complete |
| 3 | Features & Ratios | Complete |
| 4 | Valuation Engine | Complete |
| 5 | Qualitative Scoring | Complete |
| 6 | Probabilistic Signal | Complete |
| 7 | Alerts | Implemented, disabled by default |
| 8 | Frontend Dashboard | Complete |
| 9A | Watchlist Active Membership | Complete and manually tested |
| 9B | Add New Company Request Flow | Implemented, ready; manual testing in progress |

## Financial disclaimer

This application is for private research and education only. It is not financial advice, not an offer to buy or sell securities, and not a recommendation engine for public distribution. Any public distribution of market data, rankings, or recommendations requires separate legal, compliance, and data-licensing review.
