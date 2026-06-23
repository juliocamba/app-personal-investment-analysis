from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path('.').resolve() / 'src'))
from investment_app.db.repositories import (
    get_company_by_ticker,
    get_statements_for_company,
    get_prices_for_company,
    get_latest_valuation_run,
    get_signal_runs_for_company,
)
from investment_app.db.supabase_client import get_supabase_client

client = get_supabase_client()

tickers = ['MFC', 'MU', 'VRTX', 'WLDN']

results = {}

for ticker in tickers:
    company = get_company_by_ticker(ticker, client=client)
    if not company:
        results[ticker] = {'error': 'company_not_found'}
        continue
    cid = company['id']
    def first_or_none(rows):
        return rows[0] if rows else None
    results[ticker] = {
        'company': {k: company.get(k) for k in ['id','ticker','name','country','exchange','currency','sector','industry','cik']},
        'latest_price': first_or_none(get_prices_for_company(cid, client=client)),
        'latest_statements': get_statements_for_company(cid, limit=10, client=client),
        'latest_valuation': get_latest_valuation_run(cid, client=client),
        'latest_signals': get_signal_runs_for_company(cid, limit=2, client=client),
        'analysis_readiness_latest': client.table('analysis_readiness_latest').select('*').eq('company_id', cid).execute().data,
        'latest_company_data_quality_snapshots': client.table('latest_company_data_quality_snapshots').select('*').eq('company_id', cid).execute().data,
        'pipeline_events': client.table('pipeline_run_events').select('*').eq('company_id', cid).order('created_at', desc=True).limit(20).execute().data,
    }

print(json.dumps(results, indent=2, default=str))
