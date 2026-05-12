# 06 — Phase 2: Data Ingestion

## Objective

Implement the first operational data ingestion pipeline.

## Scope

Fetch and store:

- active companies from watchlist;
- EOD prices;
- basic financial statements or provider fundamentals;
- SEC filing index for US companies;
- FX rates;
- basic news/events.

## Agent instructions

Implement ingestion in small connector modules. Do not implement valuation or probabilistic scoring in this phase.

## Connector interface

Create `src/investment_app/connectors/base.py`.

Required classes:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class ProviderRequest:
    provider: str
    endpoint: str
    params: dict[str, Any]
    company_id: str | None = None

@dataclass
class ProviderResponse:
    provider: str
    endpoint: str
    params: dict[str, Any]
    status_code: int
    success: bool
    payload: dict[str, Any] | list[Any] | None
    payload_text: str | None
    error_message: str | None = None
```

## Required connectors

### 1. SEC EDGAR connector

File: `src/investment_app/connectors/sec_edgar.py`

MVP endpoints:

- company submissions by CIK;
- company facts by CIK.

Requirements:

- use `SEC_USER_AGENT`;
- rate-limit requests;
- normalise CIK to 10 digits;
- store raw payloads.

### 2. Market-data connector

File: `src/investment_app/connectors/fmp.py` or selected primary provider.

MVP endpoints:

- EOD historical quote or daily price;
- income statement;
- balance sheet;
- cash flow statement;
- company profile.

Requirements:

- provider abstraction should allow replacement later;
- handle missing data;
- log rate-limit responses.

### 3. ECB FX connector

File: `src/investment_app/connectors/ecb.py`

MVP requirement:

- fetch EUR reference exchange rates;
- store USD/EUR and other required pairs if needed.

### 4. GDELT connector

File: `src/investment_app/connectors/gdelt.py`

MVP requirement:

- fetch recent news by company name and ticker;
- store title, URL, published timestamp, sentiment if available.

## Raw storage

Implement `src/investment_app/etl/raw_store.py`.

Function:

```python
store_raw_response(response: ProviderResponse, company_id: str | None) -> str
```

Requirements:

- create checksum from provider, endpoint, params and payload;
- insert into `provider_requests` and `raw_provider_payloads`;
- avoid duplicate inserts when checksum already exists.

## Normalisation

Implement:

- `etl/normalize_prices.py`
- `etl/normalize_statements.py`
- `etl/normalize_news.py`

For MVP, normalisation can be provider-specific but must output canonical table inserts.

## Daily ingestion script

Update `scripts/run_daily_pipeline.py`.

MVP steps:

1. create pipeline run;
2. load active companies;
3. fetch prices;
4. fetch financial statements;
5. fetch filings for US companies with CIK;
6. fetch FX rates;
7. fetch news;
8. store raw payloads;
9. normalise into database;
10. finish pipeline run.

Add `--dry-run` mode.

## Acceptance criteria

- Pipeline runs for the seeded companies.
- Raw payloads are stored.
- `price_eod` has at least one row per company.
- `statements_norm` has at least one annual or quarterly row per company when provider data exists.
- `filings_index` has rows for US companies with CIK.
- Pipeline errors are logged but do not stop the full run unless configuration is invalid.

## Suggested commit message

```text
feat: implement data ingestion pipeline
```
