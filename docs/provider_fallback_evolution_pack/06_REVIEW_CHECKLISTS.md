# Review Checklists

## Phase 10A — SEC Fundamentals Fallback

Use GPT-5.4.

Checklist:
- FMP remains primary.
- SEC only runs as fallback or safe fill.
- SEC fallback is limited to US companies with CIK.
- No price assumptions are made from SEC.
- Annual facts are selected conservatively.
- Duplicate/restated facts are handled deterministically.
- `statements_norm` schema is respected.
- `source` or metadata/provenance identifies SEC-derived data.
- Derived fields are marked or diagnosed.
- Missing critical fields block valuation.
- No raw provider payloads or secrets are logged.
- Tests use fixtures only.
- Backend suite passes.

## Phase 10B — Twelve Data Price Fallback

Checklist:
- FMP remains primary for price.
- Twelve Data only runs on FMP failure/empty/provider-limited.
- `TWELVE_DATA_API_KEY` is backend-only.
- No frontend provider calls.
- Price rows are normalized into `price_eod`.
- Incremental fetching avoids excessive free-tier usage.
- Provider failures are sanitized.
- Pipeline continues if Twelve Data fails.
- Tests use fixtures only.
- Backend suite passes.

## Phase 10C — Provider Orchestration

Checklist:
- Provider decisions are centralized.
- Analysis-ready criteria are explicit.
- Unsupported companies are not silently treated as analyzable.
- Tracking-only, if added, is explicit.
- Provenance is visible in metadata/diagnostics.
- No financial logic is weakened.
- No secrets exposed.
