# Phase 10A — SEC Fundamentals Fallback

## Goal

Implement SEC EDGAR/companyfacts as a fallback source for annual fundamentals when FMP statement endpoints fail, return empty data, or are unavailable due to provider limitations such as HTTP 402.

This phase should help companies such as MU and ORCL, which have SEC CIKs and structured filings, but do not receive FMP statement data in the current free plan.

## Scope

Included:
- US companies only.
- Companies with a valid CIK.
- Annual facts only, preferably FY / 10-K.
- `us-gaap` concepts first.
- FMP remains primary.
- SEC is used only as fallback or to fill missing fields when safe.
- Persist normalized rows into `statements_norm`.
- Preserve source/provenance in available metadata fields where possible.
- Add safe diagnostics and tests.

Excluded:
- Price fallback.
- Quarterly 10-Q fallback.
- IFRS / 20-F support.
- Non-US issuers.
- Frontend provider calls.
- Valuation/scoring/signal algorithm changes.
- yfinance.
- Finnhub.

## Target canonical fields

High priority:
- `revenue`
- `gross_profit`
- `operating_income`
- `net_income`
- `cfo`
- `capex`
- `free_cash_flow`
- `cash_and_equivalents`
- `total_debt`
- `total_assets`
- `total_liabilities`
- `total_equity`
- `diluted_shares`

Medium priority:
- `ebit`
- `ebitda`
- `depreciation_amortization`
- `stock_based_compensation`
- `receivables`
- `inventory`
- `payables`

## Initial SEC tag mapping

Use `us-gaap` first.

### Income statement

| Canonical field | Candidate SEC concepts |
|---|---|
| revenue | Revenues; SalesRevenueNet; RevenueFromContractWithCustomerExcludingAssessedTax |
| gross_profit | GrossProfit |
| operating_income | OperatingIncomeLoss |
| net_income | NetIncomeLoss |
| ebit | OperatingIncomeLoss as conservative fallback |
| ebitda | derive only if depreciation/amortization is available |

### Cash flow

| Canonical field | Candidate SEC concepts |
|---|---|
| cfo | NetCashProvidedByUsedInOperatingActivities |
| capex | PaymentsToAcquirePropertyPlantAndEquipment; PaymentsToAcquireProductiveAssets |
| free_cash_flow | derive as cfo - abs(capex) |
| depreciation_amortization | DepreciationDepletionAndAmortization; DepreciationAndAmortization |
| stock_based_compensation | ShareBasedCompensation |

### Balance sheet

| Canonical field | Candidate SEC concepts |
|---|---|
| cash_and_equivalents | CashAndCashEquivalentsAtCarryingValue; CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents |
| total_assets | Assets |
| total_liabilities | Liabilities |
| total_equity | StockholdersEquity; StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest |
| total_debt | DebtCurrent + LongTermDebtNoncurrent; ShortTermBorrowings + LongTermDebtNoncurrent; LongTermDebtAndFinanceLeaseObligationsCurrent + LongTermDebtAndFinanceLeaseObligationsNoncurrent |
| diluted_shares | WeightedAverageNumberOfDilutedSharesOutstanding; EntityCommonStockSharesOutstanding as fallback with lower confidence |

## Selection rules

Use conservative selection rules:
1. Use only annual periods initially.
2. Prefer facts from 10-K forms.
3. Prefer USD units for monetary facts.
4. Prefer shares units for share counts.
5. Group by fiscal year and fiscal period.
6. Prefer latest `filed` date for duplicate/restated facts.
7. Avoid mixing annual and quarterly facts.
8. Do not silently fill ambiguous fields.
9. Record missing/ambiguous fields in diagnostics.

## Integration plan

1. Inspect current SEC connector and raw storage.
2. Confirm whether companyfacts payloads are already persisted.
3. Add a SEC companyfacts normalizer module.
4. Add tests with fixture payloads, no live SEC calls.
5. Integrate fallback in the company ingestion loop:
   - call FMP statements first;
   - if FMP statements fail/empty/402 and company has CIK, use SEC fallback;
   - upsert into `statements_norm` with `source = 'sec'` or equivalent metadata.
6. Add compact pipeline events:
   - `sec_fundamentals_fallback_used`
   - `sec_fundamentals_fallback_incomplete`
   - `sec_fundamentals_fallback_skipped_no_cik`
7. Ensure ratios and valuation consume the resulting `statements_norm` rows without financial-model changes.

## Acceptance criteria

- MU or ORCL can obtain annual `statements_norm` rows from SEC companyfacts when FMP statements return 402.
- FMP-supported companies still use FMP as primary.
- No live SEC calls in tests.
- No raw secrets or provider URLs with keys in logs.
- Incomplete SEC fallback does not produce misleading valuation.
- Backend test suite passes.

## Recommended VS Code agent

Use GPT-5.4 first for repository-specific implementation planning.
Use Claude Sonnet 4.6 for implementation.
