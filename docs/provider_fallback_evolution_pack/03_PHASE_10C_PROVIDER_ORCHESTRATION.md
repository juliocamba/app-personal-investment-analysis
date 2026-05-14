# Phase 10C — Provider Orchestration and Analysis Readiness

## Goal

Centralize provider fallback rules and analysis-readiness decisions so the app does not silently approve or display companies that cannot produce reliable investment analysis.

## Why this phase matters

After SEC and Twelve Data fallbacks exist, the app should decide whether a company is:

- analysis-ready;
- temporarily provider-limited;
- unsupported for analysis;
- tracking-only, if that mode is later implemented.

The current `missing_inputs` state is safe but not sufficiently actionable.

## Proposed provider priority

### Profile / identity
1. FMP profile
2. SEC metadata where CIK exists
3. Optional Finnhub later

### Price
1. FMP
2. Twelve Data
3. Optional Finnhub later

### Fundamentals
1. FMP
2. SEC EDGAR/companyfacts
3. Optional Finnhub later

### FX
1. ECB, as currently implemented

## Analysis readiness rules

A company is analysis-ready only if:
- latest price exists;
- enough price history exists for required momentum/volatility features;
- annual statements exist for at least the minimum number of years required by ratios/valuation;
- valuation-critical fields are present:
  - free cash flow or enough inputs to derive it;
  - shares;
  - cash;
  - debt;
  - net income/revenue/equity where required;
- source/provenance is known.

If not:
- do not produce a misleading valuation;
- do not present a normal buy/sell signal as if analysis were complete;
- expose a clear safe status.

## Add-request behavior

After Phase 10C, add requests should follow a preflight model:

1. Validate profile/ticker.
2. Determine whether a price provider path exists.
3. Determine whether a fundamentals provider path exists.
4. If both exist:
   - approve for analysis.
5. If one path is missing:
   - reject as `unsupported_for_analysis`; or
   - optionally allow `tracking_only` in a later phase.
6. If provider failure appears temporary:
   - mark `failed` or keep pending based on design.

## Provenance model

Prefer metadata without schema changes initially.

For each normalized row, store or preserve:
- primary source provider;
- fallback source provider;
- source endpoint;
- source accession number for SEC-derived data;
- filed date where available;
- field-level provenance where possible;
- fallback confidence:
  - primary
  - fallback_official
  - fallback_vendor
  - derived
  - missing

## Acceptance criteria

- Provider fallback decisions are centralized and testable.
- Add requests do not silently create companies that can never be analyzed.
- The dashboard can distinguish incomplete analysis from true neutral/hold signals.
- No frontend provider calls.
- No secrets exposed.
- Backend tests pass.
