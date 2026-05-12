# Investment Analysis MVP

A private investment-analysis application that monitors a predefined watchlist of public companies and produces a daily analytical snapshot covering price data, fundamentals, intrinsic value ranges, margin of safety, qualitative scores, probabilistic buy/sell/hold signals, and configurable alerts.

> **Disclaimer:** This tool is for private research and education only. It must not be used as personalised financial advice.

## Stack

| Layer | Technology |
|---|---|
| Backend pipeline | Python 3.11+ |
| Database | Supabase / Postgres |
| Scheduler | GitHub Actions |
| Frontend | Cloudflare Pages (React + Vite + TypeScript) |
| Alerts | SMTP email + Telegram |

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Check app health
investment-app health

# Validate configuration
investment-app config-check

# Run tests
pytest
```

Copy `.env.example` to `.env` and fill in your values before running the pipeline.

## Frontend Dashboard (Phase 8)

The frontend is a React 18 + Vite 5 + TypeScript single-page application (SPA) located in the `frontend/` directory. It reads data directly from Supabase using the **anon key** and Supabase Auth (email/password) — no backend server is required for the UI.

### Local development

```powershell
cd frontend
cp .env.example .env         # then edit .env with real values
npm install
npm run dev                  # serves at http://localhost:5173
```

| Variable | Description |
|---|---|
| `VITE_SUPABASE_URL` | Your Supabase project URL (e.g. `https://xyz.supabase.co`) |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon (public) key — **never** the service-role key |

### Running frontend tests

```powershell
cd frontend
npm test           # run once (vitest run)
npm run test:watch # watch mode
```

63 tests across 5 suites: `SignalBadge.test.tsx`, `formatters.test.ts`, `watchlistFilters.test.ts`, `WatchlistPage.test.tsx`, `AlertsPage.test.tsx`.

### Production build

```powershell
cd frontend
npm run build      # outputs to frontend/dist/
```

### Deploying to Cloudflare Pages

1. Connect your GitHub repository to Cloudflare Pages.
2. Set **Framework preset** to `None` (or Vite).
3. Configure the build:

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm run build` |
| Build output directory | `dist` |

4. Add the following environment variables in the Cloudflare Pages dashboard (Settings → Environment variables):

| Variable | Value |
|---|---|
| `VITE_SUPABASE_URL` | Your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Your Supabase anon key |

5. Trigger a deploy. The first deployment should complete in under two minutes.

### Auth and data access assumptions

- Every page requires a **Supabase Auth session**. Users are redirected to the login screen until authenticated. Create users in the Supabase dashboard → Authentication → Users.
- Data is read from the `dashboard_watchlist_latest` view and the `alert_history` table. Both are protected by Row Level Security policies that require an authenticated session (see `sql/002_rls_policies.sql`).
- The anon key is intentionally public (it is embedded in client-side JavaScript). Access control is enforced by RLS — without a valid session the anon key cannot read any rows.
- `dashboard_watchlist_latest` is defined with `WITH (security_invoker = true)` (PostgreSQL 15+, see `sql/003_views_and_functions.sql`). This makes the security intent explicit: Supabase evaluates the RLS policies on the underlying tables for the **calling role** rather than the view owner. The `anon` role is explicitly denied `SELECT` on this view; only the `authenticated` role may query it. The underlying base-table RLS policies act as a second layer of defence.
- MVP visibility assumption: all authenticated Supabase Auth users share the same read-only view of **all active companies**. This is appropriate for a small private deployment with trusted users. Per-user watchlist isolation (user-scoped `WHERE` clauses + RLS updates) is a post-MVP enhancement.
- The **service-role key** must never appear in the frontend. It is used only by the Python backend pipeline.

### Disclaimer

The frontend shows a non-dismissible disclaimer on every page:
> *Private research tool — not financial advice. All data is stored and calculated internally. Do not redistribute.*

## Alert configuration

Phase 7 alerts are **disabled by default** (`ALERTS_ENABLED=false`). No alert rules are evaluated and no records are written to `alert_history` unless the setting is explicitly enabled.

| Setting | Default | Effect |
|---|---|---|
| `ALERTS_ENABLED` | `false` | Master on/off switch. When `false`, `process_company_alerts` returns immediately — no DB writes, no sends. |
| `SMTP_ENABLED` | `false` | Per-channel on/off for email. When `false`, matched email rules are silently skipped — no `failed` history row. |
| `TELEGRAM_ENABLED` | `false` | Per-channel on/off for Telegram. Same silent-skip behaviour. |

**Security rules:**

- Email credentials (`SMTP_PASSWORD`, `SMTP_USER`) and the Telegram bot token (`TELEGRAM_BOT_TOKEN`) must never be committed to the repository.
- Add them to `.env` locally or as GitHub Actions secrets (see [docs/03_ENVIRONMENT_AND_SECRETS.md](docs/03_ENVIRONMENT_AND_SECRETS.md)).
- Tests must never send real emails or Telegram messages. All adapter calls are injected via `send_email_fn=` / `send_telegram_fn=` parameters and replaced with mocks in tests.
- Delivery failures are persisted to `alert_history.error_message` using a sanitized format (`smtp_send_failed (ExcClassName)`) — never raw exception text, URLs, tokens, or credentials.

## Running the pipeline

Phases 3–7 run through the daily pipeline entry point in [scripts/run_daily_pipeline.py](scripts/run_daily_pipeline.py).

Run a dry-run to confirm configuration and pipeline stages without fetching data or writing to Supabase:

```powershell
.\.venv\Scripts\python scripts\run_daily_pipeline.py --dry-run
```

Run the live pipeline to execute ingestion, Phase 3 features, Phase 4 valuation, Phase 5 qualitative scoring, Phase 6 probabilistic signal generation, and Phase 7 alert evaluation:

```powershell
.\.venv\Scripts\python scripts\run_daily_pipeline.py
```

Inspect persisted valuation outputs in Supabase with a query such as:

```sql
select
	company_id,
	valuation_date,
	model_version,
	iv_p10,
	iv_p50,
	iv_p90,
	current_price,
	margin_of_safety_conservative,
	assumptions,
	method_weights
from valuation_runs
order by valuation_date desc, company_id;
```

Inspect qualitative scores:

```sql
select
	company_id,
	score_date,
	model_version,
	moat_score,
	management_score,
	risk_score,
	governance_score,
	final_quality_score,
	human_override,
	override_reason
from qualitative_scores
order by score_date desc, company_id;
```

Inspect signal runs:

```sql
select
	company_id,
	signal_date,
	model_version,
	p_buy,
	p_buy_adjusted,
	p_sell,
	final_signal,
	uncertainty_penalty,
	red_flags,
	freshness_flag
from signal_runs
order by signal_date desc, company_id;
```

Inspect alert history:

```sql
select
	company_id,
	channel,
	title,
	status,
	dedupe_key,
	sent_at,
	created_at
from alert_history
order by created_at desc;
```

## Applying the Supabase schema

Run the SQL files in order using the Supabase SQL editor (Dashboard → SQL Editor → New query):

1. `sql/001_initial_schema.sql` — creates all tables, indexes, and check constraints
2. `sql/002_rls_policies.sql` — enables Row Level Security and creates access policies
3. `sql/003_views_and_functions.sql` — creates dashboard views and `updated_at` triggers
4. `sql/004_seed_watchlist_example.sql` — *(optional)* inserts example companies and watchlist

> **Before running step 4:** replace `your_email@example.com` inside `004_seed_watchlist_example.sql` with your real Supabase Auth user email. All four files are idempotent — re-running them will not create duplicate objects or rows.

After applying the schema, confirm all required tables exist:

```powershell
python scripts\validate_supabase_schema.py
```

## Phase status

| Phase | Name | Status |
|---|---|---|
| 0 | Project Bootstrap | ✅ Complete |
| 1 | Supabase Schema | ✅ Complete |
| 2 | Data Ingestion | ✅ Complete |
| 3 | Features & Ratios | ✅ Complete |
| 4 | Valuation Engine | ✅ Complete |
| 5 | Qualitative Scoring | ✅ Complete |
| 6 | Probabilistic Signal | ✅ Complete |
| 7 | Alerts | ✅ Complete |
| 8 | Frontend Dashboard | ✅ Complete |

## Documentation

The implementation documentation is written for phased development in VS Code with coding agents such as Claude Sonnet, Codex, or ChatGPT. Each phase is intentionally scoped so the agent can complete, test, and commit one stable increment at a time.

## Recommended development order

1. `docs/00_PROJECT_BRIEF.md`
2. `docs/01_ARCHITECTURE.md`
3. `docs/02_REPOSITORY_STRUCTURE.md`
4. `docs/03_ENVIRONMENT_AND_SECRETS.md`
5. `sql/001_initial_schema.sql`
6. `sql/002_rls_policies.sql`
7. `sql/003_views_and_functions.sql`
8. `sql/004_seed_watchlist_example.sql`
9. `docs/04_PHASE_0_PROJECT_BOOTSTRAP.md`
10. `docs/05_PHASE_1_SUPABASE_SCHEMA.md`
11. `docs/06_PHASE_2_DATA_INGESTION.md`
12. `docs/07_PHASE_3_FEATURES_AND_RATIOS.md`
13. `docs/08_PHASE_4_VALUATION_ENGINE.md`
14. `docs/09_PHASE_5_QUALITATIVE_SCORING.md`
15. `docs/10_PHASE_6_PROBABILISTIC_SIGNAL.md`
16. `docs/11_PHASE_7_ALERTS.md`
17. `docs/12_PHASE_8_FRONTEND_DASHBOARD.md`
18. `docs/13_TESTING_AND_VALIDATION.md`
19. `docs/14_OPERATIONS_RUNBOOK.md`
20. `docs/15_SECURITY_LICENSE_AND_COMPLIANCE.md`
21. `agent_prompts/AGENT_MASTER_PROMPT.md`
22. `agent_prompts/PHASE_EXECUTION_TEMPLATE.md`
23. `github/daily_pipeline.yml`

## Important disclaimer

This MVP is designed for private research and education. It must not be presented as personalised financial advice. Any public distribution of market data, signals, rankings, or recommendations requires legal and data-licensing review.
