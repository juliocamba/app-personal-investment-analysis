# 13 — Testing and Validation

## Objective

Define testing standards for a financial-analysis MVP where correctness, auditability and data quality matter.

## Test categories

### 1. Unit tests

Required for:

- ratio formulas;
- DCF calculations;
- qualitative scoring;
- signal thresholds;
- alert deduplication;
- checksum generation;
- configuration loading.

### 2. Integration tests

Required for:

- Supabase repository methods;
- raw payload storage;
- provider response normalisation;
- daily pipeline dry-run.

External API calls should be mocked in CI.

### 3. Data validation tests

Validate:

- no duplicate price rows for company/date/provider;
- no negative share count;
- no missing currency for prices or statements;
- valuation outputs are non-negative unless explicitly flagged invalid;
- terminal growth is lower than WACC;
- p_buy and p_sell are between 0 and 1.

### 4. Backtesting validation later

When enough historical data exists, implement:

- temporal train/test split;
- Brier score;
- log loss;
- reliability curves;
- forward return by probability bucket;
- sector-level performance;
- regime-level performance.

## Minimum CI checks

```bash
pytest
ruff check .
python scripts/validate_supabase_schema.py --dry-run
```

## Golden fixtures

Create deterministic fixtures for:

- one high-quality compounder;
- one cyclical industrial;
- one leveraged company;
- one financial company;
- one company with missing data.

## Acceptance criteria

Every phase must add or update tests. The coding agent should not mark a phase complete until tests pass.
