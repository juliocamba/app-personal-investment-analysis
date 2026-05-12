-- 001_initial_schema.sql
-- Supabase/Postgres schema for private investment analysis MVP.
-- Run this file first in Supabase SQL editor.

create extension if not exists pgcrypto;
create extension if not exists "uuid-ossp";

create table if not exists app_users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists companies (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  name text not null,
  exchange text,
  country text,
  currency text not null default 'USD',
  reporting_currency text not null default 'USD',
  cik text,
  isin text,
  sector text,
  industry text,
  company_type text not null default 'non_financial',
  fiscal_year_end text,
  active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(ticker, exchange)
);

create table if not exists watchlists (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references app_users(id) on delete cascade,
  name text not null default 'Default Watchlist',
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists watchlist_companies (
  id uuid primary key default gen_random_uuid(),
  watchlist_id uuid not null references watchlists(id) on delete cascade,
  company_id uuid not null references companies(id) on delete cascade,
  priority integer not null default 100,
  notes text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique(watchlist_id, company_id)
);

create table if not exists provider_requests (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  endpoint text not null,
  request_params jsonb not null default '{}'::jsonb,
  company_id uuid references companies(id) on delete set null,
  requested_at timestamptz not null default now(),
  status_code integer,
  success boolean not null default false,
  error_message text,
  response_checksum text,
  created_at timestamptz not null default now()
);

create table if not exists raw_provider_payloads (
  id uuid primary key default gen_random_uuid(),
  provider_request_id uuid references provider_requests(id) on delete set null,
  provider text not null,
  company_id uuid references companies(id) on delete set null,
  endpoint text not null,
  request_params jsonb not null default '{}'::jsonb,
  payload jsonb,
  payload_text text,
  checksum text not null,
  fetched_at timestamptz not null default now(),
  source_timestamp timestamptz,
  created_at timestamptz not null default now(),
  unique(provider, endpoint, checksum)
);

create table if not exists pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  run_type text not null default 'daily',
  status text not null default 'running',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  git_sha text,
  model_version text,
  message text,
  metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists pipeline_run_events (
  id uuid primary key default gen_random_uuid(),
  pipeline_run_id uuid not null references pipeline_runs(id) on delete cascade,
  level text not null default 'info',
  stage text not null,
  company_id uuid references companies(id) on delete set null,
  message text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists price_eod (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  price_date date not null,
  open numeric,
  high numeric,
  low numeric,
  close numeric not null,
  adjusted_close numeric,
  volume numeric,
  market_cap numeric,
  shares_outstanding numeric,
  currency text not null,
  provider text not null,
  asof_market_close timestamptz,
  created_at timestamptz not null default now(),
  unique(company_id, price_date, provider)
);

create table if not exists fx_rates (
  id uuid primary key default gen_random_uuid(),
  rate_date date not null,
  base_currency text not null,
  quote_currency text not null,
  rate numeric not null,
  provider text not null default 'ECB',
  published_at timestamptz,
  created_at timestamptz not null default now(),
  unique(rate_date, base_currency, quote_currency, provider)
);

create table if not exists corporate_actions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  action_type text not null,
  effective_date date not null,
  amount numeric,
  split_ratio numeric,
  currency text,
  provider text,
  raw_payload_id uuid references raw_provider_payloads(id) on delete set null,
  created_at timestamptz not null default now(),
  unique(company_id, action_type, effective_date, provider)
);

create table if not exists filings_index (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id) on delete cascade,
  filing_type text not null,
  filing_date date,
  accepted_at timestamptz,
  period_end_date date,
  accession_number text,
  document_url text,
  source text not null,
  language text,
  headline text,
  raw_payload_id uuid references raw_provider_payloads(id) on delete set null,
  created_at timestamptz not null default now(),
  unique(source, accession_number)
);

create table if not exists statements_raw (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  filing_id uuid references filings_index(id) on delete set null,
  statement_type text not null,
  fiscal_year integer,
  fiscal_period text,
  period_end_date date,
  currency text not null,
  raw_payload_id uuid references raw_provider_payloads(id) on delete set null,
  data jsonb not null default '{}'::jsonb,
  checksum text,
  created_at timestamptz not null default now()
);

create table if not exists statements_norm (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  filing_id uuid references filings_index(id) on delete set null,
  fiscal_year integer not null,
  fiscal_period text not null,
  period_end_date date not null,
  currency text not null,
  revenue numeric,
  gross_profit numeric,
  operating_income numeric,
  ebit numeric,
  ebitda numeric,
  net_income numeric,
  cfo numeric,
  capex numeric,
  free_cash_flow numeric,
  depreciation_amortization numeric,
  stock_based_compensation numeric,
  cash_and_equivalents numeric,
  total_debt numeric,
  lease_liabilities numeric,
  minority_interest numeric,
  preferred_equity numeric,
  total_assets numeric,
  total_liabilities numeric,
  total_equity numeric,
  receivables numeric,
  inventory numeric,
  payables numeric,
  diluted_shares numeric,
  restated_flag boolean not null default false,
  source text not null,
  created_at timestamptz not null default now(),
  unique(company_id, fiscal_year, fiscal_period, source)
);

create table if not exists news_events (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id) on delete cascade,
  published_at timestamptz not null,
  source text,
  provider text not null,
  title text not null,
  url text,
  language text,
  sentiment_raw numeric,
  relevance numeric,
  themes text[],
  raw_payload_id uuid references raw_provider_payloads(id) on delete set null,
  created_at timestamptz not null default now(),
  unique(provider, url)
);

create table if not exists ratios_factors (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  factor_date date not null,
  revenue_growth_yoy numeric,
  gross_margin numeric,
  operating_margin numeric,
  net_margin numeric,
  fcf_margin numeric,
  roe numeric,
  roic numeric,
  net_debt_to_ebitda numeric,
  interest_coverage numeric,
  pe_ratio numeric,
  ev_to_ebitda numeric,
  price_to_sales numeric,
  price_to_book numeric,
  fcf_yield numeric,
  momentum_20d numeric,
  momentum_60d numeric,
  momentum_250d numeric,
  volatility_30d numeric,
  volatility_90d numeric,
  news_sentiment_7d numeric,
  news_volume_7d integer,
  data_quality_score numeric,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(company_id, factor_date)
);

create table if not exists qualitative_scores (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  score_date date not null,
  moat_score numeric not null default 50,
  management_score numeric not null default 50,
  risk_score numeric not null default 50,
  governance_score numeric not null default 50,
  final_quality_score numeric not null default 50,
  auto_score jsonb not null default '{}'::jsonb,
  human_override numeric not null default 0,
  override_reason text,
  evidence_notes text,
  model_version text not null default 'qual_v0',
  created_at timestamptz not null default now(),
  unique(company_id, score_date, model_version)
);

create table if not exists valuation_runs (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  valuation_date date not null,
  model_version text not null,
  method_weights jsonb not null default '{}'::jsonb,
  assumptions jsonb not null default '{}'::jsonb,
  iv_p10 numeric,
  iv_p25 numeric,
  iv_p50 numeric,
  iv_p75 numeric,
  iv_p90 numeric,
  current_price numeric,
  margin_of_safety_conservative numeric,
  uncertainty_width numeric,
  currency text not null,
  created_at timestamptz not null default now(),
  unique(company_id, valuation_date, model_version)
);

create table if not exists signal_runs (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  signal_date date not null,
  model_version text not null,
  valuation_run_id uuid references valuation_runs(id) on delete set null,
  qualitative_score_id uuid references qualitative_scores(id) on delete set null,
  p_buy numeric not null,
  p_buy_adjusted numeric not null,
  p_sell numeric not null,
  final_signal text not null,
  uncertainty_penalty numeric not null default 0,
  red_flags text[] not null default '{}',
  top_feature_contributors jsonb not null default '[]'::jsonb,
  explanation text,
  freshness_flag text,
  created_at timestamptz not null default now(),
  unique(company_id, signal_date, model_version)
);

create table if not exists alert_rules (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references app_users(id) on delete cascade,
  company_id uuid references companies(id) on delete cascade,
  channel text not null,
  rule_type text not null,
  threshold numeric,
  enabled boolean not null default true,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists alert_history (
  id uuid primary key default gen_random_uuid(),
  alert_rule_id uuid references alert_rules(id) on delete set null,
  company_id uuid references companies(id) on delete cascade,
  signal_run_id uuid references signal_runs(id) on delete set null,
  channel text not null,
  title text not null,
  message text not null,
  dedupe_key text not null,
  sent_at timestamptz,
  status text not null default 'pending',
  error_message text,
  created_at timestamptz not null default now(),
  unique(dedupe_key)
);

create index if not exists idx_companies_ticker on companies(ticker);
create index if not exists idx_price_eod_company_date on price_eod(company_id, price_date desc);
create index if not exists idx_statements_norm_company_period on statements_norm(company_id, period_end_date desc);
create index if not exists idx_ratios_factors_company_date on ratios_factors(company_id, factor_date desc);
create index if not exists idx_valuation_runs_company_date on valuation_runs(company_id, valuation_date desc);
create index if not exists idx_signal_runs_company_date on signal_runs(company_id, signal_date desc);
create index if not exists idx_news_events_company_date on news_events(company_id, published_at desc);
create index if not exists idx_filings_company_date on filings_index(company_id, accepted_at desc);

-- ── Check constraints (idempotent) ──────────────────────────────────────────
-- Wrapped in DO blocks so re-running the file is safe.

do $$ begin
  alter table companies add constraint check_company_type
    check (company_type in ('non_financial', 'financial', 'reit', 'spac', 'utility', 'commodity'));
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table pipeline_runs add constraint check_pipeline_status
    check (status in ('running', 'success', 'failed', 'partial'));
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table pipeline_run_events add constraint check_event_level
    check (level in ('info', 'warning', 'error', 'debug'));
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table qualitative_scores add constraint check_moat_score
    check (moat_score between 0 and 100);
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table qualitative_scores add constraint check_management_score
    check (management_score between 0 and 100);
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table qualitative_scores add constraint check_risk_score
    check (risk_score between 0 and 100);
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table qualitative_scores add constraint check_governance_score
    check (governance_score between 0 and 100);
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table qualitative_scores add constraint check_final_quality_score
    check (final_quality_score between 0 and 100);
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table signal_runs add constraint check_final_signal
    check (final_signal in ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell', 'insufficient_data'));
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table alert_rules add constraint check_alert_channel
    check (channel in ('email', 'telegram'));
exception when duplicate_object then null;
end $$;

do $$ begin
  alter table alert_history add constraint check_alert_status
    check (status in ('pending', 'sent', 'failed', 'deduplicated'));
exception when duplicate_object then null;
end $$;
