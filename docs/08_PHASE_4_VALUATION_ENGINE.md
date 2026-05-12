# 08 — Phase 4: Valuation Engine

## Objective

Implement transparent intrinsic-value models that output value ranges instead of a single target price.

## Scope

Implement first versions of:

- DCF by FCFF for non-financial companies;
- multiples-based valuation as a sanity check;
- dividend discount model for stable dividend payers;
- financial-sector fallback using book value/excess return placeholders.

## Agent instructions

Prioritise clarity over sophistication. Store assumptions and intermediate outputs. Do not implement probabilistic buy/sell signals yet.

## Required modules

- `src/investment_app/valuation/dcf.py`
- `src/investment_app/valuation/multiples.py`
- `src/investment_app/valuation/dividend_discount.py`
- `src/investment_app/valuation/financials.py`
- `src/investment_app/valuation/scenarios.py`

## DCF model

### Formula

```text
FCFF = EBIT * (1 - tax_rate) + depreciation_amortization - capex - change_in_working_capital
Enterprise Value = PV(explicit FCFF) + PV(terminal value)
Terminal Value = FCFF_next / (WACC - terminal_growth)
Equity Value = Enterprise Value - net_debt - minority_interest - preferred_equity + non_operating_assets
Intrinsic Value per Share = Equity Value / diluted_shares
```

### MVP simplifications

If detailed working capital is unavailable, use conservative approximations:

- project revenue growth from historical revenue growth capped by scenario assumptions;
- use normalised operating margin from recent years;
- capex as percentage of revenue;
- D&A as percentage of revenue;
- tax rate from 3-year average or fallback;
- terminal growth capped below WACC.

### Scenarios

Implement three scenarios:

| Scenario | Weight | Behaviour |
|---|---:|---|
| Bear | 25% | lower growth, lower margin, higher WACC |
| Base | 50% | normalised assumptions |
| Bull | 25% | higher growth, better margin, lower WACC |

## Output range

Store:

- `iv_p10`
- `iv_p25`
- `iv_p50`
- `iv_p75`
- `iv_p90`
- `current_price`
- `margin_of_safety_conservative`
- `uncertainty_width`
- `assumptions`
- `method_weights`

For MVP, derive percentiles from scenario outputs and uncertainty adjustments.

## Multiples model

Use available ratios and sector defaults.

MVP approach:

- use current company historical median multiple if peer set is not available;
- later add peer table and sector medians;
- compute values from P/E, EV/EBITDA, P/S, P/B when applicable.

## Dividend discount model

Use only when:

- dividends exist;
- payout appears stable;
- company is mature.

MVP formula:

```text
V0 = D1 / (Ke - g)
```

Use conservative growth assumptions.

## Financial-sector handling

For banks and insurers, do not use FCFF DCF by default. In MVP:

- use P/B and ROE/Ke spread;
- store method as `financial_sector_placeholder_v0`;
- mark uncertainty as high.

## Pipeline integration

Daily pipeline order becomes:

1. ingestion;
2. normalisation;
3. feature computation;
4. valuation;
5. persist `valuation_runs`.

## Acceptance criteria

- Valuation run exists for each company with enough data.
- Each valuation stores assumptions as JSON.
- Output includes range and margin of safety.
- Missing data produces a clear freshness/data-quality flag.
- Unit tests cover DCF calculations with known fixtures.

## Suggested commit message

```text
feat: add intrinsic valuation engine
```
