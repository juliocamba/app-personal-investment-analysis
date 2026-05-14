# Phase 10B — Twelve Data Price Fallback

## Goal

Implement Twelve Data as a fallback provider for daily/EOD prices when FMP price endpoints fail, return empty data, or are unavailable due to provider limitations such as HTTP 402.

SEC does not provide market prices, so SEC fundamentals fallback alone is not enough for valuation.

## Scope

Included:
- Daily/EOD historical price fallback.
- Latest close price fallback.
- US equities first.
- Cache/incremental fetch where practical.
- Raw-first provider request storage consistent with existing architecture.
- Normalization into `price_eod`.

Excluded:
- Intraday prices.
- Realtime trading use.
- Twelve Data fundamentals as a default fallback.
- Frontend provider calls.
- Valuation/scoring/signal algorithm changes.

## Provider role

Twelve Data should be used for:
- `price_eod`
- latest close/current price
- momentum/volatility inputs where FMP price data is missing

Twelve Data should not initially be used for:
- income statement
- balance sheet
- cash flow
- valuation assumptions
- qualitative scoring fields

## Environment variables

Add only to backend/pipeline environments:
- `TWELVE_DATA_API_KEY`

Never expose it in:
- frontend `.env`
- Cloudflare Pages frontend env vars
- browser code

## Integration plan

1. Inspect existing provider settings and connector patterns.
2. Add/update Twelve Data connector.
3. Add normalized price parser for Twelve Data responses.
4. Integrate fallback:
   - try FMP price first;
   - if FMP returns 402/empty/failure, try Twelve Data;
   - if Twelve succeeds, upsert `price_eod` with source/provenance metadata if available.
5. Add provider request logging with sanitized errors.
6. Add safe diagnostics to pipeline events.
7. Respect Twelve Data free-tier limits:
   - avoid unnecessary full backfills;
   - fetch only missing/incremental date ranges where possible;
   - keep daily watchlist small.

## Acceptance criteria

- Companies with FMP price 402 can receive `price_eod` from Twelve Data.
- FMP remains primary where it works.
- Twelve Data key is never exposed to frontend.
- Pipeline continues if Twelve Data fails.
- Provider failures are sanitized.
- Backend tests pass.

## Recommended VS Code agent

Use GPT-5.4 for implementation planning after Phase 10A.
Use Claude Sonnet 4.6 for implementation.
