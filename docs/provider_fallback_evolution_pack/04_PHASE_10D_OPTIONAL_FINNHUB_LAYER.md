# Phase 10D — Optional Finnhub Layer

## Goal

Evaluate Finnhub as an optional tertiary provider after SEC fundamentals fallback and Twelve Data price fallback are stable.

## Recommended role

Finnhub should not be implemented before Phase 10A and Phase 10B.

Potential uses:
- fallback for price when FMP and Twelve Data fail;
- sanity-check selected fundamentals;
- supplement difficult fields such as shares, company profile, or normalized financials;
- validation layer for SEC-derived results.

## Constraints

- Keep it optional.
- Do not expose FINNHUB_API_KEY to frontend.
- Respect personal-use terms.
- Do not redistribute data.
- Do not use Finnhub as an excuse to weaken SEC provenance/auditability.

## Acceptance criteria if implemented

- Connector follows existing raw-first pattern.
- Sanitized provider errors.
- Tests use fixtures only.
- Provider usage is rate-limited/configurable.
- FMP and SEC/Twelve remain the main paths.
