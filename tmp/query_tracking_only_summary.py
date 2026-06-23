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
    latest_price = get_prices_for_company(cid, client=client, limit=1)
    latest_statements = get_statements_for_company(cid, limit=10, client=client)
    latest_valuation = get_latest_valuation_run(cid, client=client)
    latest_signals = get_signal_runs_for_company(cid, limit=2, client=client)
    readiness = client.table('analysis_readiness_latest').select('*').eq('company_id', cid).execute().data
    dq = client.table('latest_company_data_quality_snapshots').select('*').eq('company_id', cid).execute().data
    events = client.table('pipeline_run_events').select('*').eq('company_id', cid).order('created_at', desc=True).limit(20).execute().data

    def summarize_statement(row):
        if not row:
            return None
        return {
            'source': row.get('source'),
            'fiscal_year': row.get('fiscal_year'),
            'fiscal_period': row.get('fiscal_period'),
            'period_end_date': row.get('period_end_date'),
            'diluted_shares': row.get('diluted_shares'),
            'free_cash_flow': row.get('free_cash_flow'),
            'cfo': row.get('cfo'),
            'capex': row.get('capex'),
        }

    results[ticker] = {
        'company': {k: company.get(k) for k in ['id','ticker','name','country','exchange','currency','sector','industry','cik']},
        'latest_price': latest_price[0] if latest_price else None,
        'latest_statements': [summarize_statement(row) for row in latest_statements[:5]],
        'latest_valuation': {
            'valuation_date': latest_valuation.get('valuation_date') if latest_valuation else None,
            'model_version': latest_valuation.get('model_version') if latest_valuation else None,
            'current_price': latest_valuation.get('current_price') if latest_valuation else None,
            'iv_p50': latest_valuation.get('iv_p50') if latest_valuation else None,
            'iv_p90': latest_valuation.get('iv_p90') if latest_valuation else None,
            'assumptions': latest_valuation.get('assumptions') if latest_valuation else None,
        } if latest_valuation else None,
        'latest_signals': [
            {
                'signal_date': row.get('signal_date'),
                'final_signal': row.get('final_signal'),
                'p_buy': row.get('p_buy'),
                'p_sell': row.get('p_sell'),
                'uncertainty_penalty': row.get('uncertainty_penalty'),
                'red_flags': row.get('red_flags'),
                'freshness_flag': row.get('freshness_flag'),
            }
            for row in latest_signals
        ],
        'readiness': readiness[0] if readiness else None,
        'data_quality': dq[0] if dq else None,
        'pipeline_events': [
            {
                'created_at': row.get('created_at'),
                'stage': row.get('stage'),
                'level': row.get('level'),
                'message': row.get('message'),
                'details': row.get('details'),
            }
            for row in events
        ],
    }

print(json.dumps(results, indent=2, default=str))
