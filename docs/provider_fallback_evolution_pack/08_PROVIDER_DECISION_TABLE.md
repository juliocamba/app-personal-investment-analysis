# Provider Decision Table

| Need | Primary | Fallback | Optional tertiary | Avoid as core |
|---|---|---|---|---|
| Company profile | FMP | SEC metadata where possible | Finnhub | yfinance |
| Historical daily price | FMP | Twelve Data | Finnhub | yfinance, Stooq |
| Income statement | FMP | SEC companyfacts | Finnhub/Twelve selectively | Alpha Vantage Free as core |
| Balance sheet | FMP | SEC companyfacts | Finnhub/Twelve selectively | Alpha Vantage Free as core |
| Cash flow | FMP | SEC companyfacts | Finnhub/Twelve selectively | Alpha Vantage Free as core |
| Filings/CIK | SEC | FMP profile if available | — | — |
| FX | ECB | — | — | — |

## Recommendation

Implement in this order:
1. SEC fundamentals fallback.
2. Twelve Data price fallback.
3. Provider orchestration/readiness rules.
4. Optional Finnhub validation layer.

Do not rely on yfinance or Alpha Vantage Free as core providers for production-like daily analysis.
