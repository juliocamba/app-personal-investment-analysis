# 14 — Operations Runbook

## Daily operation

The GitHub Actions workflow should run once per day after market close.

Recommended UTC schedule for US-focused MVP:

```cron
30 22 * * 1-5
```

This is late enough to fetch EOD data from most free providers.

## Manual run

In GitHub Actions:

1. Open the repository.
2. Go to Actions.
3. Select Daily Investment Pipeline.
4. Click Run workflow.
5. Choose dry-run or full run.

## Local run

```bash
python scripts/run_daily_pipeline.py --dry-run
python scripts/run_daily_pipeline.py
```

## Monitoring checklist

After each run, check:

- `pipeline_runs.status`;
- number of companies processed;
- number of provider errors;
- missing price count;
- missing statement count;
- number of signals changed;
- number of alerts sent;
- pipeline duration.

## Common failures

### Provider rate limit

Symptoms:

- HTTP 429;
- missing rows for some companies.

Actions:

- enable backoff;
- reduce calls;
- use cached raw responses;
- split backfill into multiple days.

### Supabase insert failure

Symptoms:

- constraint violation;
- RLS error;
- invalid numeric type.

Actions:

- check unique constraints;
- verify service-role key is used in backend;
- validate numeric conversions;
- inspect `pipeline_run_events`.

### Missing valuation

Symptoms:

- company has ratios but no valuation run.

Actions:

- check statements_norm completeness;
- check diluted shares;
- check latest price;
- check company_type.

### Alerts not sent

Symptoms:

- signal changed but no alert.

Actions:

- check alert rules enabled;
- check dedupe key;
- check channel configuration;
- check `alert_history.error_message`.

## Monthly maintenance

- Review provider API usage.
- Review failed companies.
- Review stale filings.
- Review qualitative overrides.
- Update valuation assumptions.
- Run backtest when enough data exists.

## Backup

For MVP:

- use Supabase backups if available;
- export core tables monthly to CSV;
- keep SQL migrations in Git.
