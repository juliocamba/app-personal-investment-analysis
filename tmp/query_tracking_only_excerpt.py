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

for ticker in tickers:
    company = get_company_by_ticker(ticker, client=client)
    if not company:
        print(f"{ticker}: COMPANY NOT FOUND")
        continue
    cid = company['id']
    latest_price = get_prices_for_company(cid, client=client, limit=1)
    latest_statements = get_statements_for_company(cid, limit=10, client=client)
    latest_valuation = get_latest_valuation_run(cid, client=client)
    latest_signals = get_signal_runs_for_company(cid, limit=2, client=client)
    readiness = client.table('analysis_readiness_latest').select('*').eq('company_id', cid).execute().data
    dq = client.table('latest_company_data_quality_snapshots').select('*').eq('company_id', cid).execute().data

    statement_dates = [row.get('period_end_date') for row in latest_statements[:5]]
    statement_sources = {row.get('source') for row in latest_statements[:5]}
    last_statement = latest_statements[0] if latest_statements else None
    last_price = latest_price[0] if latest_price else None
    last_signal = latest_signals[0] if latest_signals else None
    rd = readiness[0] if readiness else {}
    dq0 = dq[0] if dq else {}

    print('='*80)
    print(f"{ticker}: {company.get('name')} ({company.get('country')}, {company.get('exchange')})")
    print(f"  CIK: {company.get('cik')}")
    print(f"  Price provider: {last_price.get('provider') if last_price else 'none'}")
    print(f"  Latest price date: {last_price.get('price_date') if last_price else 'none'}")
    print(f"  Statement sources: {sorted(statement_sources)}")
    print(f"  Latest statements (annual): {statement_dates}")
    print(f"  Latest statement source/date: {last_statement.get('source') if last_statement else 'none'} / {last_statement.get('period_end_date') if last_statement else 'none'}")
    print(f"  Latest valuation date: {latest_valuation.get('valuation_date') if latest_valuation else 'none'}")
    print(f"  Latest valuation iv_p50: {latest_valuation.get('iv_p50') if latest_valuation else 'none'}")
    print(f"  Latest signal date: {last_signal.get('signal_date') if last_signal else 'none'}")
    print(f"  Latest signal final: {last_signal.get('final_signal') if last_signal else 'none'}")
    print(f"  Readiness status: {rd.get('readiness_status')}")
    print(f"  Readiness provider_mix: {rd.get('provider_mix')}")
    print(f"  Readiness codes: {rd.get('readiness_reason_codes')}")
    print(f"  can_run_valuation: {rd.get('can_run_valuation')}, can_run_signal: {rd.get('can_run_signal')}")
    print(f"  Limiting domain: {rd.get('limiting_domain')}")
    print(f"  Data-quality status: {dq0.get('data_quality_status')}")
    print(f"  Data-quality warnings: {dq0.get('data_quality_warning_codes')}")
    print(f"  Fundamentals compare status: {dq0.get('fundamentals_provider_comparison_status')}")
    print(f"  Price validation status: {dq0.get('price_validation_status')}")
    print(f"  Latest pipeline events (last 5):")
    for event in dq0.get('pipeline_events', []):
        pass
    events = client.table('pipeline_run_events').select('created_at,stage,level,message,details').eq('company_id', cid).order('created_at', desc=True).limit(5).execute().data
    for event in events:
        print(f"    - [{event.get('created_at')}] {event.get('stage')} {event.get('level')} {event.get('message')} {event.get('details')}")
print('='*80)
