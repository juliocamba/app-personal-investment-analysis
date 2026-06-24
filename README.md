# Investment Analysis MVP

A personal, private research application that tracks a watchlist of public companies, runs a daily analytical pipeline, and surfaces buy/hold/sell signals in a dashboard.

> **This is a personal decision-support tool, not financial advice.** Outputs are analytical signals based on quantitative models and rule-based heuristics. They are not recommendations to buy or sell any security. Always verify independently before acting on any signal.

This repository contains both the Python backend pipeline and the React frontend.

For implementation detail, schema notes, RLS behavior, and the operational model, see [README-TECHNICAL.md](README-TECHNICAL.md).

## What this app does

Each day, the pipeline:

1. **Collects company data** — prices, financial statements, SEC filings, and FX rates from multiple providers.
2. **Validates data availability** — checks whether each company has enough recent, reliable data to support a signal.
3. **Calculates financial ratios** — growth rates, margins, leverage, and return metrics.
4. **Estimates an intrinsic value range** — using multiple DCF scenarios and multiples-based methods, producing low/mid/high estimates.
5. **Calculates margin of safety** — how far the current price is from the estimated intrinsic value.
6. **Assesses quality and risks** — a qualitative score combining profitability, leverage, competitive position, and red flag detection.
7. **Generates a rule-based buy/sell signal** — combining valuation, quality, and risk factors into a single signal with internal buy and sell scores plus auditable reasoning metadata.
8. **Classifies readiness** — marks companies as signal-ready, provider-limited, or tracking-only based on data availability.

Results appear in the dashboard within minutes of the pipeline completing.

Phase 12A has started with data-quality diagnostics and limited gating. These checks currently compare overlapping FMP and Twelve Data prices when both exist for the same company/date, summarize normalized statement completeness, and compare overlapping annual FMP vs SEC fundamentals when both normalized sources exist. They emit pipeline events/metrics, persist evidence, and surface a separate dashboard data-quality lane. As of the current Phase 12A hardening pass, stale underlying fundamentals older than 540 days also block valuation and signal generation through the existing readiness gate; this does not change valuation math or signal thresholds. Stale-age anchoring is deterministic: annual normalized statement `period_end_date`, anchored by latest signal date, then valuation date, then price date, then pipeline as-of date.

Phase 12B.1 adds a separate manual positions foundation. Positions are user-entered ownership records with entry date, quantity, average entry price, currency, fees, notes, and active/closed status. They are tracked separately from watchlist analytics and do not change signals, readiness, valuation, alerts, or data-quality diagnostics. Phase 12B.2 adds display-only current value and unrealized P&L using the latest stored price when an active position has a matching price currency; it does not add realized P&L, FX conversion, or investment advice. Phase 12C.1 adds an entry thesis + entry snapshot foundation so each position can keep optional thesis notes plus a frozen snapshot of already-stored app state at the time the profile is captured. Phase 12C.2 improves thesis readability and adds a neutral entry-vs-current comparison using already-persisted current signal, readiness, data-quality, quality score, valuation, and margin-of-safety state only. Phase 12F.1 adds a separate historical signal-validation foundation that persists point-in-time observations from already stored `signal_runs` and `price_eod`, then exposes read-only research summaries without changing live signal generation.

## Phase 12G checkpoint

Phase 12G hardens research credibility without changing signal labels, signal thresholds, valuation thresholds, or adding recommendation behavior.

- Stale fundamentals older than 540 days now suppress valuation and signal execution through readiness gating.
- Valuation outputs now carry a separate economic credibility layer via `valuation_sanity_status` and related suppression fields.
- `signal_display_state` separates analytical signals from readiness-suppressed or missing current-state signal rows.
- `p_buy`, `p_buy_adjusted`, and `p_sell` are internal rule-based scores, not calibrated probabilities.
- HOLD explanations now vary by hold reason so they say why conviction was withheld instead of repeating generic wording.

Before relying on outputs, verify data freshness, readiness status, provider mix, red flags, and valuation uncertainty. If a row is `tracking_only`, or if valuation sanity says the output is unreliable, treat the dashboard as a research surface rather than a current analytical signal.

## SEC normalization freshness fix

After Phase 12G, the SEC companyfacts normalizer was tightened so annual
fiscal-year discovery uses the union of relevant SEC concepts rather than
stopping at the first concept with data. This prevents stale concept coverage
from hiding fresher annual facts available under other revenue, cash-flow,
balance-sheet, or share-count concepts. The change does not alter readiness
thresholds, valuation thresholds, signal thresholds, providers, or
stale-fundamentals gating; it only improves which usable SEC annual statement
years are normalized when the raw facts already exist.

## Derived ratio freshness guard

Post-SEC-refresh valuation now checks that historical `ratios_factors` rows used
for multiples were computed from the same latest normalized annual statement
period as the DCF input. New ratio snapshots persist statement and price vintage
metadata. When valuation sees older or mismatched ratio history, it excludes
those rows from the multiples estimate and records diagnostics such as
`stale_ratio_history` and `ratio_history_statement_vintage_mismatch` rather
than silently blending stale derived factors with fresh statements. This does
not change readiness thresholds, valuation sanity thresholds, signal thresholds,
providers, or signal labels.

The daily pipeline also recomputes the latest stored ratio history when possible
from already normalized statements and stored prices as of each factor date. This
backfills statement/price vintage metadata for recent historical rows while
leaving unsupported rows excluded and diagnosable.

Valuation diagnostics also flag conservative input-scale anomalies when price,
share count, and fundamentals are internally inconsistent. Codes such as
`price_scale_anomaly`, `price_provider_scale_mismatch`, and
`share_count_unit_anomaly` explain suppressed valuations without changing
readiness thresholds, signal thresholds, valuation thresholds, providers, or
signal labels.

## Current capabilities

- Authenticated React dashboard (Supabase Auth).
- FMP Stable API as primary provider for prices, profiles, and statements.
- SEC EDGAR as fallback for US company fundamentals.
- Twelve Data as fallback for price data.
- ECB FX rates for non-USD currency conversion.
- Daily pipeline via GitHub Actions (scheduled weekday runs + manual dispatch).
- Manual signal-validation refresh via a separate GitHub Actions workflow that runs the research backtest only on demand.
- Watchlist management: add, remove, and reactivate companies.
- Manual positions tracking: add, edit, list, and close user-owned positions.
- Display-only position metrics: current price, cost basis, current value, unrealized gain/loss, and unrealized return when the latest stored price is usable.
- Entry thesis + snapshot tracking: optional thesis notes plus a frozen reference snapshot of signal/readiness/valuation/data-quality state for positions.
- Entry-vs-current comparison for positions: a display-only comparison of the frozen entry snapshot against the latest stored signal, readiness, data-quality, quality-score, valuation-range, and margin-of-safety state.
- Historical signal validation: a separate research page summarizing forward price returns by signal bucket and horizon from persisted historical state only.
- Extended historical signal validation: descriptive breakdowns by readiness, data quality, sector, and signal-stability transitions from persisted history only.
- Coverage transparency for historical signal validation: explicit counts for unknown historical readiness/data-quality context, unknown sector context, and forward-price coverage gaps.
- Signal Validation interpretation panel: a conservative top-level read on dataset maturity, coverage, observation count, and signal-history span for non-quant interpretation.
- Full analytical stack: ratios, valuation, qualitative score, probabilistic signal.
- Readiness classification: signals are only generated when data meets quality thresholds.
- Valuation diagnostics in the dashboard: MoS basis, DCF scenario count, uncertainty category, distribution-collapsed warning, and valuation sanity credibility classification (`usable`, `high_uncertainty`, `unreliable`, `model_failure`).
- Signal rule v3 with midpoint fair-value anchoring, uncertainty-adjusted hold/sell bands, and stricter STRONG_SELL confirmation.
- Phase 12A.5 dashboard data-quality lane: persisted price-validation, statement-completeness, and FMP-vs-SEC annual diagnostics now surface as a separate dashboard lane. Most diagnostics remain explanatory only, but stale annual fundamentals older than 540 days now gate valuation and signal generation through the existing `tracking_only` path with the `stale_fundamentals` readiness reason code.
- Dashboard stale-output suppression: when readiness blocks valuation or signal (including stale fundamentals), `dashboard_watchlist_latest` returns those analytical fields as null so old analytical rows are not displayed as current state.
- Dashboard valuation-sanity suppression: when valuation diagnostics mark valuation output as not display-credible (`unreliable` or `model_failure`), `dashboard_watchlist_latest` suppresses valuation display fields to avoid presenting non-credible valuation precision.
- Dashboard research-quality badge: a read-only grouping badge shows whether the current row is fully blocked, valuation blocked, confidence limited, or available for analysis. It uses compact diagnostic codes and does not change signal, readiness, valuation, or suppression behavior.
- Valuation input-consistency diagnostics: valuation assumptions and audit exports surface stale or mismatched derived ratio history so multiples evidence cannot quietly rely on factor rows computed from an older statement vintage.
- Alerts present but disabled by default.
- Cloudflare Pages deployment is planned but not yet live.

## High-level architecture

| Layer | Role |
|---|---|
| Python backend | Ingests provider data, stores raw payloads, normalizes data, computes analytics, writes results |
| Supabase / Postgres | Operational database, analytical tables, views, RLS, auth-backed frontend access |
| GitHub Actions | Scheduled weekday runner and manual dispatch for the daily pipeline |
| React + Vite frontend | Dashboard UI for watchlist, positions, add requests, and alert history |
| Cloudflare Pages | Planned static hosting target for the frontend |

## Main stack

| Component | Technology |
|---|---|
| Backend language | Python 3.11+ |
| Database | Supabase / PostgreSQL |
| Scheduler | GitHub Actions |
| Frontend | React 18 + Vite 5 + TypeScript |
| Frontend hosting | Cloudflare Pages |
| Market/provider data | FMP Stable API (primary), Twelve Data (price fallback) |
| Filings / fundamentals | SEC EDGAR (US fundamentals fallback) |
| FX rates | ECB FX |

## Dashboard field guide

Each row in the dashboard represents one company. The columns mean:

| Field | What it shows |
|---|---|
| **Signal** | The overall model outcome: STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL, or INSUFFICIENT_DATA. It is not investment advice. |
| **Price** | The latest end-of-day closing price. |
| **p_buy_adj** | Adjusted internal buy score (0–1). It is a rule-based model score, not a calibrated probability. Reduced when evidence quality or confidence is limited. |
| **p_sell** | Internal sell score (0–1). It is a rule-based model score, not a calibrated probability. It rises when valuation downside or bearish risk evidence becomes stronger. |
| **Quality** | A qualitative score (0–100) based on profitability, leverage, competitive position, and management signals. |
| **IV Range** | Intrinsic value range: low / mid / high estimate from DCF and multiples scenarios. |
| **MoS** | Margin of safety: how far the current price is below (positive) or above (negative) the estimated intrinsic value. A large positive MoS means the price looks cheap relative to the model. |
| **Freshness** | How recent the underlying data is. Stale data can reduce signal reliability. |
| **Readiness status** | Data availability classification: `analysis_ready`, `partial_analysis`, `provider_limited`, `tracking_only`, or `unsupported_for_analysis`. |
| **Provider coverage** | A coverage classification showing whether data came from primary sources only, a fallback mix, or price-only coverage. |
| **Data quality** | A separate diagnostic lane in the expanded row showing validation health, warning codes, statement completeness evidence, and FMP-vs-SEC comparison summaries. It is explanatory only. |
| **Research quality** | A read-only diagnostic grouping derived from readiness, data-quality, and valuation-sanity evidence. It can show fully blocked, valuation blocked, confidence limited, or analysis available. |
| **Red flags** | Specific bearish concerns detected: high debt, declining revenue, margin compression, etc. |
| **Valuation uncertainty** | Low / moderate / high / extreme — reflects how spread the DCF scenario range is. |
| **DCF scenarios** | How many DCF method variants contributed to the intrinsic value estimate (out of 3 possible). |

### Signal reasoning metadata

Each persisted signal also carries deterministic reasoning metadata inside its auditable contributor payload. The metadata explains why the model outcome is credible, limited, or caveated without using the final label as evidence for itself.

- `dominant_signal_driver` identifies the main evidence category behind the outcome.
- `hold_reason` distinguishes HOLD variants such as near-fair-value, uncertainty-constrained, valuation-unreliable, risk-offset, data-constrained, or neutral mixed.
- `valuation_used_in_signal` shows whether valuation evidence was allowed to influence the model outcome.
- `confidence_limiter_codes` lists deterministic reasons that reduce conviction.
- `strong_sell_basis` distinguishes whether a STRONG_SELL is driven by risk, valuation, or both.
- `buy_conviction_limited` marks BUY and STRONG_BUY outcomes where confidence limiters still apply.

### Signal labels

| Signal | Meaning |
|---|---|
| **STRONG_BUY** | High internal buy score, low sell pressure, strong quality. |
| **BUY** | Elevated internal buy score with acceptable quality and limited sell pressure. |
| **HOLD** | Neutral or mixed evidence. Can mean the price is near fair value, the quality is mixed, or there is not enough conviction in either direction. A HOLD does not mean "safe to hold" — it means the model found no strong signal. |
| **SELL** | Meaningful downside evidence, typically from price significantly above fair value or bearish quality signals. |
| **STRONG_SELL** | Strong sell requires stronger evidence: either severe overvaluation versus midpoint fair value, an independent hard-risk flag, or both together. A price above the conservative range alone is not sufficient for STRONG_SELL. |
| **INSUFFICIENT_DATA** | Not enough reliable data to generate any signal. The company is visible but not actionable. |

> **Note on tracking-only companies:** A company with readiness status `tracking_only` or `unsupported_for_analysis` appears in the dashboard with its latest price but without a valuation or signal. The signal column shows a readiness badge rather than a signal value, and current-state audit exports distinguish the raw stored signal from the suppressed display state. Non-US companies without SEC EDGAR coverage (for example, ASML) may remain in this state. `TRACKING_ONLY` is a readiness/display state, not a stored signal value.

> **Note on data-quality warnings:** The dashboard now shows a separate data-quality lane inside the expanded company panel. These warnings are diagnostic evidence only. They are not signal labels, not readiness states, and not investment advice.

> **Note on the audit severity matrix:** Current-state audit exports classify existing readiness, data-quality, valuation, and signal diagnostic codes into `informational`, `confidence_limited`, `blocks_valuation`, `blocks_signal`, or `blocks_both`. FCF/DCF-path gaps are treated as component-level confidence limiters unless valuation sanity itself blocks valuation, and fully blocked ratio history is separated from filtered stale ratio history. This is explanatory metadata for review; it does not change readiness gates, valuation thresholds, signal thresholds, providers, signal labels, or dashboard suppression behavior.

HOLD can include uncertainty-constrained valuation concern, valuation-unreliable constraint, risk-offset behavior, or data-constrained neutrality, not only a plain neutral read. If valuation warnings are visible but the valuation range is wide, the explanation text should describe the stretched valuation evidence and the reduced conviction without changing the model outcome.

### Signal calibration note

The valuation engine remains conservative: margin of safety is still calculated from `iv_p10` and remains visible as a downside/reference diagnostic. Signal rule v3 uses `iv_p50` as the main fair-value anchor for sell calibration, with wider neutral bands when valuation uncertainty is high. A margin of safety within ±0.5% of zero is also treated as near fair value to avoid spurious signals from floating-point rounding near zero.

The `p_buy_adj` and `p_sell` fields are internal rule-based model scores. They are useful for ranking and calibration inside this app, but they are not calibrated probabilities and should not be read as direct chances of market outcomes.

## How to read a company row

Example: you open the dashboard and see:

> **AAPL** | Signal: **HOLD** | Price: $195 | p_buy_adj: 0.42 | p_sell: 0.18 | Quality: 78 | IV Range: $160–$200–$240 | MoS: +2.6% | Readiness: analysis_ready | Uncertainty: moderate | DCF: 3/3

This means:
- The model estimates fair value between $160 and $240, with a mid-point near $200.
- At $195, the price is close to the mid-point, giving a small positive margin of safety.
- Quality is good (78/100) but not exceptional.
- No strong buy or sell conviction — HOLD means "no strong edge either way."
- All three DCF scenarios ran successfully; moderate uncertainty is normal.

If the same row showed `p_sell: 0.72` and an independent hard-risk flag such as high leverage, the signal might be **SELL** or **STRONG_SELL**. If the only issue is valuation and the valuation range is wide, the model may cap the output at **SELL** rather than **STRONG_SELL**.

## What to do before acting on a signal

Before making any real decision based on a signal:

1. **Check data freshness.** Stale data can produce misleading signals. If the freshness indicator is old, wait for the next pipeline run.
2. **Check readiness status.** A `provider_limited` or `tracking_only` company has incomplete data. Treat its signal with extra caution or ignore it entirely.
	Companies with underlying annual fundamentals older than 540 days are forced into a non-analytical readiness state and will not receive new valuation or signal outputs until fresher fundamentals are available.
3. **Check provider mix.** If the company is on SEC fallback or Twelve Data fallback, the data source is less complete than FMP primary. The dashboard shows which providers contributed.
4. **Check red flags.** Even a BUY signal can carry red flags. Review them before acting.
5. **Check valuation uncertainty.** An `extreme` uncertainty category means the DCF scenarios are very spread. The intrinsic value range is wide and less reliable.
6. **Verify externally.** This tool is a starting point for research, not a conclusion. Check company filings, news, and analyst views before acting.

## Provider coverage

The pipeline uses a cascading fallback for data:

| Data type | Primary | Fallback |
|---|---|---|
| Price (EOD) | FMP | Twelve Data |
| Financial statements | FMP | SEC EDGAR (US companies only) |
| Company profile | FMP | — |
| SEC filings | SEC EDGAR | — |
| FX rates | ECB | — |

**Non-US companies** (for example, ASML listed on Euronext) may remain as `tracking_only` if FMP does not supply sufficient fundamental data and SEC EDGAR does not cover the company. This is a known limitation of the current provider set.

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

## Running historical signal validation

Use the separate research refresh job in [scripts/run_backtest.py](scripts/run_backtest.py).

```powershell
.\.venv\Scripts\python scripts\run_backtest.py
```

This refreshes persisted historical validation observations from already stored `signal_runs` and `price_eod` only. It does not call providers, does not modify live signal generation, and does not simulate a strategy.

You can also run the same refresh manually in GitHub Actions through [.github/workflows/signal_validation.yml](.github/workflows/signal_validation.yml). That workflow is `workflow_dispatch` only, checks the required Supabase secrets, runs the signal-validation test subset, validates schema access, and then executes `scripts/run_backtest.py`. It is intentionally separate from the daily scheduled pipeline.

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
7. `sql/007_statements_norm_metadata.sql`
8. `sql/008_statements_norm_raw_payload_id.sql`
9. `sql/009_price_eod_metadata_and_precedence.sql`
10. `sql/010_analysis_readiness_latest_view.sql`
11. `sql/011_explicit_grants_and_rls_hardening.sql`
12. `sql/012_function_execute_and_effective_privilege_hardening.sql`
13. `sql/013_valuation_diagnostics_in_dashboard_view.sql`
14. `sql/014_company_data_quality_snapshots.sql`
15. `sql/015_dashboard_data_quality_lane.sql`
16. `sql/016_positions.sql`
17. `sql/017_positions_display_metrics.sql`
18. `sql/018_position_entry_profiles.sql`
19. `sql/019_positions_current_comparison_fields.sql`
20. `sql/020_position_review_alerts.sql`
21. `sql/021_position_review_alert_lifecycle_controls.sql`
22. `sql/022_portfolio_dashboard_views.sql`
23. `sql/023_portfolio_dashboard_fx_normalized_views.sql`
24. `sql/024_signal_backtest_observations.sql`
25. `sql/025_signal_backtest_segmentations.sql`
26. `sql/026_signal_backtest_interpretation_summary.sql`
27. `sql/027_latest_views_security_invoker.sql`
28. `sql/028_dashboard_stale_readiness_suppression.sql`
29. `sql/029_dashboard_valuation_sanity_suppression.sql`
30. `sql/030_dashboard_signal_display_state.sql`
31. `sql/031_dashboard_quality_matrix_fields.sql`

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

## Manual positions

Positions are a separate manual tracking surface from the watchlist.

- A position records what you currently own or previously owned.
- It includes company, entry date, quantity, average entry price, currency, optional fees, optional notes, and active/closed status.
- Positions are created manually from companies that already exist in the app catalog.
- It does not alter watchlist analytics, readiness, valuation, signal generation, delivery-alert logic, or data-quality warnings in this phase.
- Creating a position does not trigger provider validation, pipeline analysis, or automatic signal behavior.
- The positions page can now show display-only current price, cost basis, current value, unrealized gain/loss, and unrealized return using the latest stored price.
- Those display metrics remain blank when no latest price exists, when the latest price currency does not match the position currency, or when the position is already closed.
- Positions can also store an optional entry thesis with summary, rationale, risks, catalysts, holding period, confidence, target price, and invalidation criteria.
- A separate entry snapshot is captured from already-stored database state only. It can include the latest stored market price, signal, readiness, data-quality status, quality score, valuation range, and margin of safety that were available at capture time.
- The positions page can compare that frozen entry snapshot against the latest stored current state for price, signal, readiness, data quality, quality score, valuation range, and margin of safety.
- Entry snapshot fields are historical reference points. They do not recalculate automatically and do not change pipeline behavior, signals, readiness, valuation, or alerts.
- The comparison remains descriptive only. It does not create buy/sell/reduce recommendations or automate any position action.
- Open positions can now surface persisted review alerts for a small set of low-noise conditions using already stored app state only: target price reached, severe signal deterioration, major readiness deterioration, and critical data-quality deterioration.
- Those review alerts are reassessment prompts only. They do not close positions automatically and do not recommend selling automatically.
- Users can now manage those review alerts with simple lifecycle controls on the positions page: dismiss, snooze 7 days, snooze 30 days, or snooze 90 days.
- Snoozing or dismissing an alert does not change position ownership, signals, readiness, valuation outputs, data-quality diagnostics, or pipeline behavior.
- The portfolio page now provides a display-only aggregate view over persisted positions, review alerts, and current stored analytics.
- Portfolio totals exclude positions with missing current prices or currency mismatches. No FX conversion or silent estimation is applied in this phase.
- An optional `FX-normalized estimate (EUR)` section can show EUR totals using stored ECB daily FX rates matched by exact price date only.
- FX-normalized rows without exact-date stored FX coverage are excluded from the EUR estimate rather than silently converted.
- The portfolio dashboard does not provide portfolio recommendations, rebalancing suggestions, tax logic, or automated advice.
- A separate signal validation page now summarizes historical forward price returns by signal bucket and horizon using persisted history only.
- The signal validation page also adds descriptive subgroup breakdowns for readiness, data quality, sector, and signal-stability transitions.
- The signal validation page also surfaces compact coverage-limit summaries for unknown historical context and missing forward-price horizons.
- The signal validation page now adds a top-level `Can I trust this model yet?` interpretation panel with conservative dataset-maturity labels (`LOW`, `MEDIUM`, `HIGH`) based on evidence coverage and history span only.
- Dataset maturity describes the quality and coverage of the historical evidence so far. It does not mean the model is proven correct or safe to trust blindly.
- Signal validation is price-return only, historical only, and explicit about coverage gaps or not-available fields. It is not a future guarantee and does not alter live signals.
- No FX conversion, realized P&L, tax logic, or recommendation logic is added in this phase.
- It is recordkeeping and decision support only, not automated investment advice.

## Alerts

Alerts are present in the MVP but remain disabled by default.

| Setting | Default | Meaning |
|---|---|---|
| `ALERTS_ENABLED` | `false` | Master switch for all alert evaluation |
| `SMTP_ENABLED` | `false` | Enables SMTP delivery when alerts are enabled |
| `TELEGRAM_ENABLED` | `false` | Enables Telegram delivery when alerts are enabled |

When alerts are disabled, no alert evaluation runs and no new `alert_history` rows are written by the alert stage.

Phase 12D.1 also adds separate persisted position review alerts for open positions. Those alerts are generated only from already stored DB state after the analytical pipeline finishes. They are review prompts only, not automated trade instructions.

## GitHub Actions daily pipeline

The repository includes [.github/workflows/daily_pipeline.yml](.github/workflows/daily_pipeline.yml).

GitHub only executes workflow files placed under `.github/workflows/`. The file at that path is the authoritative, executable workflow.

Current workflow characteristics:

- runs on both `workflow_dispatch` (manual) and a weekday cron schedule (`30 22 * * 1-5`, 22:30 UTC Monday–Friday);
- opts into Node.js 24 for JavaScript actions (`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`);
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

## GitHub Actions signal validation refresh

The repository also includes [.github/workflows/signal_validation.yml](.github/workflows/signal_validation.yml).

Current workflow characteristics:

- runs on `workflow_dispatch` only;
- does not run on the weekday schedule;
- uses only already stored Supabase data;
- fails early with a clear error when `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` is missing;
- runs the signal-validation test subset before the refresh;
- validates Supabase schema before executing `scripts/run_backtest.py`;
- does not call live providers and does not change the daily pipeline behavior.
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

- **Not investment advice.** This is a personal research tool. Signals are rule-based heuristics, not statistically calibrated probabilities or professional recommendations.
- **Data may be incomplete.** Free-tier providers have rate limits and coverage gaps. Missing data can suppress signals or cause partial analysis.
- **Non-US fundamentals may not be fully supported.** Companies without SEC EDGAR coverage may remain as tracking-only if the primary provider does not supply sufficient fundamental data.
- **Tracking-only rows are suppressed by display state.** Old consumers that read only `final_signal` may miss `signal_display_state`, `stored_final_signal`, and readiness-suppression semantics.
- **Valuation models are based on assumptions, not predictions.** DCF outputs are scenario estimates. Small changes in growth or discount rate assumptions can materially change the intrinsic value range.
- **Internal buy/sell scores are rule-based, not statistically calibrated.** `p_buy_adj` and `p_sell` reflect formula outputs, not historical win rates.
- **Near-zero margin of safety is treated as near fair value.** Values within ±0.5% of zero are clamped to zero in signal calibration.
- **Signal calibration uses midpoint fair value.** `iv_p10` remains the conservative margin-of-safety diagnostic, while `iv_p50` anchors sell-pressure calibration and uncertainty-adjusted hold/sell boundaries.
- **Cloudflare Pages deployment is planned but not yet live.** The frontend currently runs locally.
- **Alerts are disabled by default.** No alert evaluation or delivery occurs unless `ALERTS_ENABLED=true`.
- The app is designed for a private deployment, not a public multi-tenant product.
- Per-user watchlist isolation beyond the current trusted-user model is not implemented.

## Roadmap / post-MVP ideas

- Cloudflare Pages production deployment.
- GitHub Actions production scheduling and secret management.
- Backfill and reconciliation workflows.
- Per-user watchlist isolation.
- Improved operator dashboards for `pipeline_runs` and provider health.
- Additional valuation diagnostics and model calibration tools.
- Expanded alert rule management in the frontend.

## Next planned slice

After the current audit-first Data Quality / Readiness Gating Matrix slice, the next planned work should use the new matrix export to decide whether any frontend grouping, backfill, or gating-policy changes are justified. Threshold tuning, provider additions, and new signal categories remain out of scope unless explicitly approved.

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
| 10A | SEC Fundamentals Fallback | Complete |
| 10B | Twelve Data Price Fallback | Complete |
| 10C | Provider Orchestration | Complete |
| 10D | Finnhub Optional Layer | Deferred — connectors are placeholder stubs; no active fallback |
| 11A | Signal Calibration & Valuation Diagnostics | Complete |
| 12A.5 | Dashboard Data-Quality Lane | Started: separate dashboard diagnostics lane for price-validation, statement-completeness, and FMP-vs-SEC annual checks |

## Financial disclaimer

This application is for private research and education only. It is not financial advice, not an offer to buy or sell securities, and not a recommendation engine for public distribution. Any public distribution of market data, rankings, or recommendations requires separate legal, compliance, and data-licensing review.
