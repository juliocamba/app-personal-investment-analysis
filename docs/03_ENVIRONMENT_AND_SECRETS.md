# 03 — Environment and Secrets

## Local environment setup

Create a `.env` file locally. Never commit it.

```env
APP_ENV=local
LOG_LEVEL=INFO

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=replace_me
SUPABASE_ANON_KEY=replace_me

DATA_PROVIDER_PRIMARY=fmp
FMP_API_KEY=replace_me
FINNHUB_API_KEY=replace_me
ALPHA_VANTAGE_API_KEY=replace_me
TWELVE_DATA_API_KEY=replace_me

SEC_USER_AGENT="InvestmentAnalysisMVP your_email@example.com"

SMTP_ENABLED=false
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=replace_me
SMTP_PASSWORD=replace_me
ALERT_EMAIL_FROM=alerts@example.com
ALERT_EMAIL_TO=your_email@example.com

TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=replace_me
TELEGRAM_CHAT_ID=replace_me

ALERTS_ENABLED=false
```

## GitHub Actions secrets

Create the following repository secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `FMP_API_KEY`
- `FINNHUB_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `TWELVE_DATA_API_KEY`
- `SEC_USER_AGENT`
- `SMTP_ENABLED`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `ALERT_EMAIL_FROM`
- `ALERT_EMAIL_TO`
- `TELEGRAM_ENABLED`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ALERTS_ENABLED`

Only add provider keys you actually use.

## Cloudflare Pages environment variables

The frontend should only receive public/read-only variables:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=replace_me
```

Never expose `SUPABASE_SERVICE_ROLE_KEY` in Cloudflare Pages.

## Supabase authentication model

For MVP, the frontend may be protected by one of these options:

1. Cloudflare Access in front of the dashboard.
2. Supabase Auth with a single user.
3. Private local-only dashboard for development.

Recommended MVP path:

- Use Supabase Auth for dashboard login.
- Enable Row Level Security.
- Use service-role key only in GitHub Actions backend jobs.

## Provider rate limits

The pipeline must include provider-level rate limits and retries.

Recommended strategy:

- cache raw responses by provider/request/checksum;
- use daily EOD requests, not intraday polling;
- avoid fetching unchanged historical statements repeatedly;
- only fetch full historical data in backfill mode;
- use incremental updates in daily mode.

## Local commands

Suggested commands:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/validate_supabase_schema.py
python scripts/run_daily_pipeline.py --dry-run
python scripts/run_daily_pipeline.py
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python scripts\run_daily_pipeline.py --dry-run
```
