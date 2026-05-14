# Manual Validation Runbook

## After Phase 10A

Use a company that FMP blocks but SEC supports, for example MU or ORCL.

1. Ensure the company has:
   - ticker
   - CIK
   - active watchlist membership

2. Run the pipeline:
```powershell
.\.venv\Scripts\python.exe scripts\run_daily_pipeline.py
```

3. Validate SEC-derived statements:
```sql
select
  c.ticker,
  s.fiscal_year,
  s.period_end_date,
  s.revenue,
  s.net_income,
  s.cfo,
  s.capex,
  s.free_cash_flow,
  s.cash_and_equivalents,
  s.total_debt,
  s.total_assets,
  s.total_liabilities,
  s.total_equity,
  s.diluted_shares,
  s.source
from statements_norm s
join companies c on c.id = s.company_id
where c.ticker in ('MU', 'ORCL')
order by c.ticker, s.fiscal_year desc;
```

Expected:
- `statements_norm > 0`
- source/provenance indicates SEC or fallback where possible
- incomplete fields are diagnosed

4. Validate downstream:
```sql
select 'ratios_factors' as table_name, count(*) from ratios_factors r
join companies c on c.id = r.company_id
where c.ticker in ('MU', 'ORCL')
union all
select 'valuation_runs', count(*) from valuation_runs v
join companies c on c.id = v.company_id
where c.ticker in ('MU', 'ORCL');
```

If price is still missing, valuation may still be blocked. That is expected until Phase 10B.

## After Phase 10B

1. Configure `TWELVE_DATA_API_KEY` in backend `.env` and GitHub Actions secrets.
2. Run the pipeline.
3. Validate price fallback:
```sql
select
  c.ticker,
  p.price_date,
  p.close,
  p.volume
from price_eod p
join companies c on c.id = p.company_id
where c.ticker in ('MU', 'ORCL')
order by c.ticker, p.price_date desc
limit 20;
```

Expected:
- price rows exist for tickers that FMP blocked
- downstream ratios/valuation may now compute if SEC statements are complete

## Provider request diagnostics

```sql
select
  created_at,
  provider,
  endpoint,
  status_code,
  success,
  error_message
from provider_requests
order by created_at desc
limit 50;
```

No API keys or raw secret-bearing URLs should appear.
