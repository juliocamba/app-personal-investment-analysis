# Technical README

This document describes the current technical architecture of the Investment Analysis MVP. It complements [README.md](README.md), which is intended to stay concise and operator-focused.

## System architecture

The system has five main runtime surfaces:

- a Python backend pipeline that ingests provider data and computes analytical outputs;
- a Supabase/Postgres database that stores raw data, normalized data, analytical tables, views, and pipeline logs;
- a React + Vite frontend that reads from Supabase using the anon key and Supabase Auth;
- a GitHub Actions workflow for scheduled and manual pipeline runs;
- planned static hosting on Cloudflare Pages.

At a high level:

1. Users interact with the dashboard through Supabase Auth.
2. The frontend reads dashboard data from Supabase views and tables allowed by RLS.
3. The backend pipeline runs with the Supabase service-role key and performs all provider ingestion and write-heavy operations.
4. Analytical outputs are persisted to daily snapshot tables that the dashboard can read.

## Data flow

### Watchlist and add requests

- `watchlists` identifies a user-owned watchlist.
- `watchlist_companies` represents membership in the watchlist and is the source of truth for active or inactive membership.
- `watchlist_add_requests` stores pending, approved, rejected, failed, or cancelled request state for new-company requests.

### Provider ingestion

- FMP Stable API provides company profile, price, and statement data.
- SEC EDGAR provides submissions and company facts for filing coverage.
- ECB provides FX rates.
- GDELT/news can be wired in but remains optional and may be disabled.

### Raw payload storage

- Every external call should create a `provider_requests` row.
- Raw provider payloads are stored in `raw_provider_payloads` before normalization.

### Normalization

- Price payloads are normalized into `price_eod`.
- Financial statement payloads are normalized into `statements_norm`.
- Filing metadata is normalized into `filings_index`.
- News payloads are normalized into `news_events` when news ingestion is enabled.

### Ratios and features

- Phase 3 computes feature and ratio snapshots into `ratios_factors`.

### Valuation

- Phase 4 computes valuation outputs into `valuation_runs`.

### Qualitative scoring

- Phase 5 computes or updates `qualitative_scores`.

### Probabilistic signals

- Phase 6 computes `signal_runs` using valuation and qualitative inputs.

### Alerts

- Phase 7 evaluates enabled alert rules and writes to `alert_history` when alerts are enabled.

### Dashboard

- The frontend reads the latest analytical state primarily through `dashboard_watchlist_latest` and other authenticated surfaces.

## Pipeline stages in execution order

The live daily pipeline in [scripts/run_daily_pipeline.py](scripts/run_daily_pipeline.py) currently runs in this order:

1. create a `pipeline_runs` row;
2. process pending watchlist add requests;
3. load active companies from `watchlist_companies.active`, falling back to YAML only on technical failure;
4. for each active company: FMP profile, prices, statements, SEC data, optional news;
5. fetch ECB FX rates;
6. compute Phase 3 ratios and features;
7. compute Phase 4 valuation outputs;
8. compute Phase 5 qualitative scores;
9. compute Phase 6 probabilistic signals;
10. evaluate Phase 7 alerts if enabled;
11. finish the pipeline run with metrics and status.

Dry-run mode validates configuration and prints the planned pipeline flow without persisting provider-derived outputs.

## Supabase schema overview

### Core catalog and watchlist tables

| Table | Purpose |
|---|---|
| `companies` | Master company catalog keyed by ticker and exchange |
| `watchlists` | User-owned watchlists |
| `watchlist_companies` | Membership table linking companies into watchlists, including `active` state |
| `watchlist_add_requests` | User-submitted requests to add new companies to a watchlist |

### Ingestion and raw data tables

| Table | Purpose |
|---|---|
| `provider_requests` | Metadata for provider API requests |
| `raw_provider_payloads` | Raw provider response payloads for auditability and replay |
| `price_eod` | End-of-day price history |
| `statements_raw` | Raw statement landing table |
| `statements_norm` | Normalized financial statements |
| `filings_index` | SEC filing metadata |
| `news_events` | Normalized news records |
| `fx_rates` | ECB FX rates |

### Analytical output tables

| Table | Purpose |
|---|---|
| `ratios_factors` | Daily factor and ratio snapshot |
| `valuation_runs` | Daily valuation model outputs |
| `qualitative_scores` | Daily qualitative scoring outputs and overrides |
| `signal_runs` | Daily probabilistic signal outputs |

### Alerts and operations tables

| Table | Purpose |
|---|---|
| `alert_rules` | User-configured alert definitions |
| `alert_history` | Alert delivery history and failures |
| `pipeline_runs` | Pipeline run status and metrics |
| `pipeline_run_events` | Stage-level structured event log |

## SQL migration order

Apply migrations in this order:

1. `sql/001_initial_schema.sql`
2. `sql/002_rls_policies.sql`
3. `sql/003_views_and_functions.sql`
4. `sql/004_seed_watchlist_example.sql`
5. `sql/005_watchlist_management.sql`
6. `sql/006_watchlist_add_requests.sql`
7. `sql/007_statements_norm_metadata.sql`
8. `sql/008_statements_norm_raw_payload_id.sql`
9. `sql/009_price_eod_metadata_and_precedence.sql`
10. `sql/010_analysis_readiness_latest_view.sql`
11. `sql/011_explicit_grants_and_rls_hardening.sql`
12. `sql/012_function_execute_and_effective_privilege_hardening.sql`

13. `sql/013_valuation_diagnostics_in_dashboard_view.sql`

Notes:

- `004_seed_watchlist_example.sql` is optional sample data.
- `005_watchlist_management.sql` implements Phase 9A watchlist active-membership behavior.
- `006_watchlist_add_requests.sql` implements Phase 9B add-company request flow and hardening.
- `011_explicit_grants_and_rls_hardening.sql` applies explicit GRANT/REVOKE to every table and view.  Apply this migration before running the permission validator.
- `012_function_execute_and_effective_privilege_hardening.sql` strips PUBLIC EXECUTE from `get_my_app_user_id()` and completes the view effective-privilege cleanup.
- `013_valuation_diagnostics_in_dashboard_view.sql` recreates `dashboard_watchlist_latest` with four appended diagnostic columns: `mos_basis`, `scenario_count`, `uncertainty_category`, `distribution_collapsed`.

## RLS and grants model

### Supabase explicit GRANT requirement

Supabase is removing the default public-schema grants that previously gave every
role automatic access to new tables.  Migration `011_explicit_grants_and_rls_hardening.sql`
adds explicit `GRANT` and `REVOKE` statements to every table and view in the
schema.  Without this migration the following symptoms appear:

- `authenticated` inherits unexpected `REFERENCES`, `TRIGGER`, and `TRUNCATE`
  privileges from the Supabase `ALTER DEFAULT PRIVILEGES` defaults.
- `service_role` is missing `SELECT`, `INSERT`, `UPDATE`, `DELETE` on tables
  created after the default grant behaviour was removed, preventing the backend
  pipeline from writing via the Data API.
- Tables that have an RLS SELECT policy but no explicit `GRANT SELECT` silently
  return empty result sets or permission errors for authenticated users.

Always apply all listed migrations in order (001–013) on a new or existing Supabase project.

### Helper function execute hardening

PostgreSQL grants `EXECUTE` on every new function to the `PUBLIC` pseudo-role
by default.  For SECURITY DEFINER functions this is a defence-in-depth concern:
the function runs as its owner regardless of the calling role, so any role —
including `anon` — can invoke it via the Supabase Data API
(`/rest/v1/rpc/<function_name>`) unless `PUBLIC` execute is explicitly revoked.

`get_my_app_user_id()` is the only SECURITY DEFINER helper in the public schema.
Its current correct grant state (after migration 012) is:

| Grantee | Privilege | Expected |
|---|---|---|
| `PUBLIC` | EXECUTE | ✗ revoked |
| `anon` | EXECUTE | ✗ revoked |
| `authenticated` | EXECUTE | ✓ granted |
| `service_role` | EXECUTE | ✓ granted |
| `postgres` | EXECUTE | Supabase internal — acceptable |

Any future SECURITY DEFINER function added to the public schema should
immediately revoke `PUBLIC` and `anon` execute and grant only to the intended
roles.

### Access tiers

| Tier | Tables | authenticated | service_role | anon / public |
|---|---|---|---|---|
| **backend_only** | `pipeline_runs`, `pipeline_run_events`, `provider_requests`, `raw_provider_payloads`, `statements_raw` | none | SELECT/INSERT/UPDATE/DELETE | none |
| **backend_rw_auth_r** | `companies`, `price_eod`, `fx_rates`, `filings_index`, `statements_norm`, `ratios_factors`, `qualitative_scores`, `valuation_runs`, `signal_runs`, `news_events`, `corporate_actions`, `company_analysis_readiness` | SELECT only | SELECT/INSERT/UPDATE/DELETE | none |
| **auth_scoped_write** | `app_users`, `watchlists`, `alert_rules`, `alert_history` | SELECT only (own rows via RLS) | SELECT/INSERT/UPDATE/DELETE | none |
| **auth_scoped_write** | `watchlist_companies` | SELECT + UPDATE (own rows via RLS) | SELECT/INSERT/UPDATE/DELETE | none |
| **auth_scoped_write** | `watchlist_add_requests` | SELECT + column-scoped INSERT + UPDATE(status) | SELECT/INSERT/UPDATE/DELETE | none |
| **views** | all `latest_*`, `dashboard_*`, `analysis_readiness_latest` | SELECT | SELECT | none |

### Validating permissions

After applying all migrations, run the permission validator:

```powershell
.\.venv\Scripts\python scripts\validate_supabase_permissions.py
```

This calls the `check_permission_matrix()` function (defined in migration 011)
and reports pass/fail for six key invariants.

For a full diagnostic breakdown, run the SQL queries in `sql/audit/` in the
Supabase SQL Editor:

- `sql/audit/permission_audit.sql` — table and view privileges by grantee
- `sql/audit/rls_policy_audit.sql` — RLS enabled/disabled and all policies
- `sql/audit/view_security_audit.sql` — view `security_invoker` settings, grants, and function execute privileges

### Manual validation queries

Run the following in the Supabase SQL Editor after applying migrations 011 and 012.

**Function execute privileges for `get_my_app_user_id`**
```sql
-- PUBLIC and anon must be absent.
-- authenticated and service_role must be present.
-- Owner/internal rows such as postgres may appear and are acceptable.
select r.routine_name, rp.grantee, rp.privilege_type
from information_schema.routines r
join information_schema.routine_privileges rp
  on rp.specific_schema = r.specific_schema
 and rp.specific_name   = r.specific_name
where r.routine_schema = 'public'
  and r.routine_name   = 'get_my_app_user_id'
order by rp.grantee;
```

**Effective privileges on `company_analysis_readiness` for `authenticated`**
```sql
-- INSERT must be false; SELECT must be true.
select
  has_table_privilege('authenticated', 'company_analysis_readiness', 'INSERT') as insert_allowed,
  has_table_privilege('authenticated', 'company_analysis_readiness', 'SELECT') as select_allowed;
```

**Effective SELECT on dashboard and readiness views for `authenticated`**
```sql
-- All must be true.
select
  has_table_privilege('authenticated', 'dashboard_watchlist_latest',   'SELECT') as dash_latest,
  has_table_privilege('authenticated', 'dashboard_watchlist_inactive',  'SELECT') as dash_inactive,
  has_table_privilege('authenticated', 'analysis_readiness_latest',     'SELECT') as readiness_latest,
  has_table_privilege('authenticated', 'latest_price_eod',              'SELECT') as price_eod,
  has_table_privilege('authenticated', 'latest_signal_runs',            'SELECT') as signal_runs;
```

**`anon`/`public` must have zero table/view grants**
```sql
-- Expected: zero rows.
select table_name, grantee, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee in ('anon', 'PUBLIC')
order by table_name;
```

**Backend-only tables must have zero `authenticated` grants**
```sql
-- Expected: zero rows.
select table_name, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee      = 'authenticated'
  and table_name in (
    'pipeline_runs', 'pipeline_run_events', 'provider_requests',
    'raw_provider_payloads', 'statements_raw'
  )
order by table_name, privilege_type;
```

### Frontend anon access

- The frontend ships with the Supabase anon key only.
- The anon key is public but should not grant useful data access without a valid authenticated session.
- Dashboard views rely on RLS plus `security_invoker` assumptions to ensure access is evaluated as the calling role.

### Authenticated read and write surfaces

Authenticated users can read their dashboard surfaces and have narrowly-scoped write access only where intended.

Examples:

- `watchlist_companies` is hardened so authenticated users do not get INSERT or DELETE privileges; only scoped UPDATE is allowed for their own watchlist memberships.
- `watchlist_add_requests` is hardened so authenticated users can insert only `watchlist_id`, `requested_ticker`, and `requested_exchange`, and can update only `status` for cancellation.

### Service-role backend access

- The backend pipeline uses the Supabase service-role key.
- It is the only trusted runtime allowed to perform provider ingestion, create company rows, create watchlist memberships, and update pipeline-owned request outcome fields.

### Phase 9A hardening

Phase 9A moved active watchlist authority from `companies.active` to `watchlist_companies.active` and hardened the privileges so the frontend cannot insert new memberships directly.

### Phase 9B hardening

Phase 9B introduced `watchlist_add_requests` with a constrained security model:

- authenticated users may read only their own requests;
- authenticated users may insert only request input fields;
- authenticated users may update only `status` to cancel their own pending request;
- authenticated users may not approve, reject, fail, or mutate pipeline-owned fields such as `company_id`, `error_code`, `error_message`, or `processed_at`.

## Watchlist behavior

The system treats watchlist state as follows:

- `companies` is the master company catalog.
- `watchlist_companies.active` is the source of truth for whether a company is in the active watchlist.
- Soft removal keeps the company row and historical analytical data intact.
- Reactivation restores visibility and future pipeline processing through the same membership model.
- Historical preservation is intentional; removal is not deletion.

## Add-company request lifecycle

`watchlist_add_requests.status` uses this lifecycle:

| Status | Meaning |
|---|---|
| `pending` | Waiting for pipeline validation |
| `approved` | Accepted and linked to a company/watchlist membership |
| `rejected` | Business-rule rejection, such as invalid or ambiguous ticker |
| `failed` | Technical failure, such as provider unavailable |
| `cancelled` | User cancelled before pipeline approval |

The pipeline resolves pending requests before loading active companies for the rest of the run, so newly approved companies can enter the same run if the request is approved early enough.

## Provider model

### FMP Stable API

FMP is the primary market-data connector for company profile, price, and financial statement data.

### SEC EDGAR (US fundamentals fallback)

SEC EDGAR provides filing submissions and company facts (from the XBRL `companyfacts` endpoint) for US-listed companies. It is used as a fallback when FMP fundamental data is insufficient or missing. SEC requests require a valid `SEC_USER_AGENT` string identifying the operator.

Non-US companies (for example, ASML) are not covered by SEC EDGAR and may remain as `tracking_only` if FMP does not supply sufficient fundamental data.

### Twelve Data (price fallback)

Twelve Data is used as a price fallback when FMP price data is unavailable or stale. It covers end-of-day prices for most major exchanges.

### ECB FX

ECB is used for daily FX rates needed by the analytical pipeline for non-USD currency conversion.

### Finnhub and Alpha Vantage

Finnhub and Alpha Vantage keys are present in the workflow env and local env template but are not actively used as primary or fallback connectors in the current implementation. They remain available for future use.

### GDELT / news

GDELT/news ingestion is optional and disabled by default. The pipeline logs when news ingestion is skipped.

## Error handling and secret safety

- Provider errors written to database rows should be sanitized.
- Raw exception text should not be persisted as user-facing pipeline failure messages.
- Secrets must not be logged.
- The frontend must never contain the Supabase service-role key or provider API keys.
- SMTP and Telegram credentials must remain outside version control.

## Readiness classification

The pipeline computes a readiness snapshot for each company into `company_analysis_readiness` and surface fields on the dashboard.

### Readiness status values

Defined in `readiness.py` and constrained in `company_analysis_readiness.check_readiness_status`:

| Status | Meaning |
|---|---|
| `analysis_ready` | Sufficient data for a full valuation and signal run. |
| `partial_analysis` | Some data is present but incomplete. A signal may be generated with a demoted buy probability. |
| `provider_limited` | The provider set does not supply enough data for this company. Signal is suppressed or degraded. |
| `tracking_only` | Price data is available but fundamental data is not sufficient or not supported. No valuation or signal is generated. |
| `unsupported_for_analysis` | The company or exchange is not supported by the current provider set. No data or signal is produced. |

### Dashboard fields from readiness

The `dashboard_watchlist_latest` view exposes:

- `readiness_status` — the classification above.
- `can_run_valuation` — boolean; false suppresses the valuation diagnostics panel.
- `can_run_signal` — boolean; false suppresses the signal.
- `provider_mix` — a coverage classification (`primary_only`, `fallback_mix`, `mixed_sources`, `price_only`, or `insufficient_coverage`).

### Tracking-only behavior

- A `tracking_only` company appears in the dashboard with its latest price but without an intrinsic value range, margin of safety, or signal.
- The readiness notice is shown in the expanded detail panel instead of valuation or signal fields.
- This state is expected for non-US companies without SEC EDGAR fundamentals coverage.

## Valuation model summary

The valuation layer (model version `valuation_v1`) is designed as a daily snapshot combining multiple approaches.

Current implementation:

- multiple DCF scenarios with varied growth and terminal assumptions;
- multiples-based valuation support;
- scenario results stored as percentile outputs: `iv_p10`, `iv_p50`, `iv_p90`;
- `mos_basis` records which percentile was used for the conservative margin-of-safety calculation;
- `scenario_count` records how many DCF method variants contributed;
- `uncertainty_category` (`low` / `moderate` / `high` / `extreme`) derived from the spread of the scenario range;
- `distribution_collapsed` flag set when scenarios collapsed to a single point;
- method and assumption diagnostics stored in `valuation_runs.assumptions["diagnostics"]` JSON;
- margin-of-safety outputs consumed by the signal engine and surfaced in the dashboard.

### Valuation diagnostics in dashboard

Migration `013_valuation_diagnostics_in_dashboard_view.sql` adds four diagnostic columns to `dashboard_watchlist_latest`:

| Column | Source |
|---|---|
| `mos_basis` | `assumptions->'diagnostics'->>'mos_basis'` |
| `scenario_count` | `(assumptions->'diagnostics'->>'scenario_count')::int` |
| `uncertainty_category` | `assumptions->'diagnostics'->>'uncertainty_category'` |
| `distribution_collapsed` | `(assumptions->'diagnostics'->'warnings') @> '["distribution_collapsed"]'` |

## Signal model summary

The signal layer uses model version `signal_rule_v2`.

Persisted outputs:

- `p_buy` — raw buy probability before quality adjustment;
- `p_buy_adjusted` — buy probability after partial-analysis demotion;
- `p_sell` — sell pressure probability;
- `final_signal` — the classified signal.

Allowed `final_signal` values are constrained in SQL (`signal_runs.check_final_signal`):

- `strong_buy`
- `buy`
- `hold`
- `sell`
- `strong_sell`
- `insufficient_data`

> **`tracking_only` is not a stored signal value.** It is a readiness/display state. When `can_run_signal = false` the frontend shows a readiness badge instead of a signal, and the `TRACKING_ONLY` filter in the dashboard selects rows by `can_run_signal = false`, not by `final_signal`.

### Signal rule v2 behaviour

- **Near-fair-value epsilon band**: MoS values within `±0.5%` (i.e. `abs(mos) ≤ 0.005`) are clamped to zero before sell-pressure calculation. This prevents floating-point noise near zero from generating spurious sell signals (observed with values such as `-1.5e-16` for near-fair-value companies).
- **STRONG_SELL confirmation requirement**: A `strong_sell` classification requires both elevated sell pressure (`p_sell` above threshold) **and** at least one confirming bearish red flag. Elevated price alone is not sufficient.
- **Partial-analysis buy demotion**: When `readiness_status = partial_analysis`, `p_buy_adjusted` is reduced from `p_buy` to reflect reduced data confidence.
- **Tracking-only passthrough**: Companies with `tracking_only` or `unsupported_for_analysis` readiness have `can_run_signal = false`. The signal engine is not invoked and no `signal_runs` row is written for those companies.

The signal output also stores red flags, explanation text, top feature contributors, and freshness indicators.

## Model interpretation and limitations

- Outputs are rule-based analytical signals, not statistically calibrated probabilities.
- `p_buy_adj` and `p_sell` reflect formula outputs against thresholds, not historical win rates.
- Valuation models rely on assumptions. Small changes to growth or discount rate inputs can materially shift the intrinsic value range.
- The `uncertainty_category` field gives a qualitative sense of model confidence, but even a `low` uncertainty category does not imply accuracy.
- Non-US companies may have degraded or missing fundamental data, which can result in `tracking_only` or `provider_limited` states regardless of company quality.
- Do not treat any output as a recommendation. Use outputs as a starting point for further research.

## Frontend architecture

The frontend is a React SPA in `frontend/`.

Key characteristics:

- Supabase Auth gates the application;
- the browser client uses `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` only;
- the Watchlist page reads the active dashboard view;
- the Watchlist page supports Phase 9A remove/reactivate behavior;
- the Watchlist page includes the Phase 9B add-request UI and recent-request list;
- the Alerts page reads alert history surfaces;
- no provider APIs are called directly from frontend code.

## Testing strategy

- Backend uses unit tests under `tests/` with pytest.
- Frontend uses Vitest and Testing Library under `frontend/src/__tests__/`.
- Tests do not call live external APIs.
- Provider calls are mocked or injected in backend tests.
- Alert delivery is mocked in tests and must not send real messages.

## Deployment

### GitHub Actions

The repository includes [.github/workflows/daily_pipeline.yml](.github/workflows/daily_pipeline.yml), which:

- runs on both `workflow_dispatch` (manual) and a weekday cron schedule (`30 22 * * 1-5`, 22:30 UTC Monday–Friday);
- sets `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` at workflow level to opt into Node.js 24 for `actions/checkout` and `actions/setup-python` before GitHub forces the migration;
- fails early when required secrets are absent;
- sets up Python and installs dependencies;
- runs unit tests;
- validates Supabase schema;
- executes the pipeline with environment variables sourced from repository secrets.

GitHub only executes workflow files placed under `.github/workflows/`. That path is the authoritative, executable workflow.

This is best treated as a configurable deployment artifact until production secrets are supplied.

### Cloudflare Pages

Cloudflare Pages is the intended frontend hosting target.

Target settings:

- root directory: `frontend`
- build command: `npm run build`
- output directory: `dist`
- frontend environment variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`

## Operational runbook

### First setup

1. Create Supabase project.
2. Apply SQL migrations in order.
3. Configure local `.env` and `frontend/.env` using placeholders as templates.
4. Validate schema.
5. Run backend dry-run.
6. Start frontend locally and verify authenticated access.

### Daily run

- Run the pipeline live locally or through GitHub Actions once credentials are configured.
- Review `pipeline_runs` and `pipeline_run_events` after completion.

### Manual run

PowerShell examples:

```powershell
.\.venv\Scripts\python scripts\run_daily_pipeline.py --dry-run
.\.venv\Scripts\python scripts\run_daily_pipeline.py
```

### Checking `pipeline_runs`

Confirm:

- latest run status;
- started and finished timestamps;
- metrics JSON;
- any error message.

### Checking `provider_requests`

Confirm:

- provider request volume;
- success vs failure;
- repeated status codes;
- whether raw payload capture is occurring as expected.

### Checking dashboard views

Inspect:

- `dashboard_watchlist_latest`
- `dashboard_watchlist_inactive`
- latest analytical output tables for companies expected to appear in the UI.

## Troubleshooting

### FMP 403

Check:

- `FMP_API_KEY` value;
- provider plan and quota;
- network egress restrictions;
- whether the request is being made from the intended environment.

### Missing `valuation_runs`

Check:

- `statements_norm` completeness;
- latest price availability;
- feature computation success;
- pipeline events in the `valuation` stage.

### RLS permission errors

Check:

- whether the frontend is authenticated;
- whether the right role has the expected base GRANT in SQL;
- whether the row matches the RLS predicate;
- whether recent manual privilege changes drifted from migrations.

### Frontend auth errors

Check:

- `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`;
- Supabase Auth user existence;
- redirect/session handling;
- browser console for Supabase client initialization issues.

### Stuck `pipeline_runs`

Check:

- whether the process exited before `finish_pipeline_run`;
- the latest `pipeline_run_events` entries;
- uncaught connector or normalization exceptions;
- GitHub Actions job logs if running remotely.

## Contribution and development guidelines

- Keep analytical and security behavior in Python and SQL, not in the frontend.
- Do not expose the service-role key or provider secrets.
- Keep migrations idempotent.
- Preserve RLS hardening when changing frontend write surfaces.
- Add or update tests when changing pipeline behavior, RLS-adjacent logic, or dashboard data access.
- Avoid live API calls in automated tests.
- Treat this repository as a private research tool, not a public advisory product.