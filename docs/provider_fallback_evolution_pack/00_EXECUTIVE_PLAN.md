# Provider Fallback Evolution Plan

## Context

The investment-analysis MVP is working end-to-end for companies where FMP provides complete data.

Current system:
- Python backend
- Supabase
- React/Vite frontend
- GitHub Actions planned/configurable for the daily pipeline
- Cloudflare Pages planned
- FMP Stable API as primary provider
- SEC EDGAR partially integrated
- ECB FX integrated
- Watchlist add/remove/reactivate implemented
- Phase 9A and Phase 9B implemented
- Some tickers work with FMP, for example AAPL and BAC
- Other tickers, for example MU and ORCL, have FMP profile available but price and financial-statement endpoints return HTTP 402

Problem:
- Without `price_eod` and `statements_norm`, the app cannot compute reliable ratios, valuation, margin of safety, or investment signals.
- A generic `missing_inputs` state is technically safe but not sufficient for a useful analysis product.
- The next step should be real data fallback, not only better diagnostics.

## Deep-research conclusion

The best free/free-tier strategy is not to replace FMP with a single provider.

Recommended provider architecture:
1. Keep FMP as the primary provider where it works.
2. Use SEC EDGAR/companyfacts as the primary fallback for US fundamentals.
3. Use Twelve Data as the primary fallback for daily/EOD prices.
4. Keep Finnhub as an optional tertiary/validation layer.
5. Avoid Alpha Vantage Free and yfinance/Yahoo Finance as core production dependencies.

## Product principle

A company should be considered analysis-ready only when there is a viable path for:

- daily/EOD price data: FMP or Twelve Data;
- annual fundamentals: FMP or SEC EDGAR;
- valuation-critical fields: free cash flow, shares, latest price, historical statements, and factors;
- explicit data provenance for every fallback-derived field.

If no viable data path exists:
- reject the request as `unsupported_for_analysis`; or
- allow `tracking_only` only as an explicit future opt-in mode.

## Recommended implementation sequence

### Phase 10A — SEC Fundamentals Fallback
Use SEC EDGAR/companyfacts to populate `statements_norm` when FMP statements are unavailable, empty, or blocked.

### Phase 10B — Twelve Data Price Fallback
Use Twelve Data to populate `price_eod` when FMP prices are unavailable, empty, or blocked.

### Phase 10C — Provider Orchestration and Analysis Readiness
Centralize provider selection, fallback rules, data provenance, and readiness gates.

### Phase 10D — Optional Finnhub Validation Layer
Use Finnhub only as a selective optional fallback or cross-check layer after SEC and Twelve Data are stable.

## Recommended order

1. Implement Phase 10A.
2. Implement Phase 10B.
3. Implement Phase 10C.
4. Consider Phase 10D only if needed.

Do not implement all phases at once.
