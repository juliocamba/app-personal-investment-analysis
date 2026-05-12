# 07 — Phase 3: Features and Financial Ratios

## Objective

Compute the financial, market, news and data-quality features required by valuation and scoring.

## Scope

This phase calculates and stores `ratios_factors`.

## Agent instructions

Implement deterministic formulas and tests. Do not implement DCF or final signal yet.

## Required modules

- `src/investment_app/features/ratios.py`
- `src/investment_app/features/quality_features.py`
- `src/investment_app/features/market_features.py`
- `src/investment_app/features/news_features.py`

## Financial ratios

Compute where data is available:

- revenue growth YoY;
- gross margin;
- operating margin;
- net margin;
- free cash flow margin;
- ROE;
- ROIC;
- net debt / EBITDA;
- interest coverage;
- FCF yield;
- P/E;
- EV/EBITDA;
- P/S;
- P/B.

## Market features

Compute:

- momentum 20 trading days;
- momentum 60 trading days;
- momentum 250 trading days;
- volatility 30 trading days;
- volatility 90 trading days;
- drawdown if price history exists.

## News features

Compute:

- average sentiment 7 days;
- average sentiment 30 days;
- news volume 7 days;
- news volume 30 days;
- negative-event count.

For MVP, sentiment can be provider-provided if available. Do not over-engineer NLP in this phase.

## Data-quality score

Create `data_quality_score` from 0 to 100.

Suggested components:

- latest price available: 20 points;
- latest annual/quarterly statements available: 30 points;
- share count available: 10 points;
- market cap available: 10 points;
- FX available if needed: 10 points;
- latest filing/news scan completed: 10 points;
- no major missing required fields: 10 points.

## Formula examples

```text
gross_margin = gross_profit / revenue
operating_margin = operating_income / revenue
fcf_margin = free_cash_flow / revenue
roe = net_income / average_total_equity
roic = nopat / invested_capital
net_debt_to_ebitda = (total_debt - cash_and_equivalents) / ebitda
fcf_yield = free_cash_flow / market_cap
```

## Pipeline integration

Add a feature-computation stage after data normalisation.

Daily pipeline order becomes:

1. ingestion;
2. normalisation;
3. feature computation;
4. persist `ratios_factors`.

## Acceptance criteria

- `ratios_factors` is populated for every company with sufficient data.
- Missing data does not crash pipeline.
- Each ratio function has unit tests.
- Division-by-zero returns `None`, not an exception.
- Data-quality score is visible in database.

## Suggested commit message

```text
feat: compute financial ratios and factor snapshots
```
