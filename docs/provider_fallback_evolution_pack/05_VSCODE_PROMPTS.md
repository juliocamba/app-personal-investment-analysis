# VS Code Prompts

## Recommended workflow

Use:
- GPT-5.4 for planning and reviews.
- Claude Sonnet 4.6 for implementation.

Do not implement all phases at once.

---

## Prompt 1 — Repository-specific Phase 10A implementation plan

Use GPT-5.4.

```text
Read the provider fallback evolution markdown files.

Create a repository-specific implementation plan for Phase 10A — SEC Fundamentals Fallback.

Do not implement code yet.
Do not change files yet.
Do not change SQL yet.

Context:
- FMP remains the primary provider.
- SEC EDGAR/companyfacts should become the fallback for US annual fundamentals.
- The current app already fetches SEC filings/companyfacts in some form.
- The goal is to populate statements_norm when FMP statements return 402, empty, or unavailable.
- No frontend provider calls.
- No secrets exposed.
- No live APIs in tests.
- Do not change valuation/scoring/signal algorithms unless strictly necessary.

Inspect:
- scripts/run_daily_pipeline.py
- src/investment_app/run_daily_pipeline.py if present
- src/investment_app/connectors/sec_edgar.py
- src/investment_app/connectors/fmp.py
- src/investment_app/ingestion/
- src/investment_app/db/repositories.py
- sql/001_initial_schema.sql
- tests related to SEC, ingestion, statements, ratios, valuation

Deliver:
1. Current repo assessment.
2. Existing SEC capabilities.
3. Files to change.
4. Proposed normalizer design.
5. SEC tag mapping.
6. Pipeline integration plan.
7. Diagnostics and provenance plan.
8. Test plan.
9. Risks/open questions.
10. Exact implementation order.
11. Acceptance criteria.

Do not write code.
```

---

## Prompt 2 — Implement Phase 10A

Use Claude Sonnet 4.6 after Prompt 1 is accepted.

```text
Implement Phase 10A — SEC Fundamentals Fallback.

Do not implement Phase 10B.
Do not implement Twelve Data.
Do not call live APIs in tests.
Do not expose secrets.
Do not change frontend unless strictly necessary.
Do not change valuation/scoring/signal algorithms.

Goal:
When FMP statements fail, return empty data, or return provider-limited status such as 402, use SEC companyfacts as fallback for US companies with CIK and populate statements_norm annual rows.

Tasks:
1. Add a SEC companyfacts normalizer using fixtures in tests.
2. Map annual SEC facts to statements_norm fields.
3. Use conservative selection rules: annual/FY/10-K, USD, latest filed for duplicates.
4. Derive free_cash_flow from cfo and capex where possible.
5. Do not silently derive weak fields without diagnostics.
6. Integrate fallback into the existing company ingestion pipeline.
7. Preserve FMP as primary.
8. Add safe pipeline events and diagnostics.
9. Add tests for successful fallback, incomplete fallback, missing CIK, duplicate facts/restatements, and no-secrets logging.
10. Run backend tests.

Before finishing:
1. Explain root cause solved.
2. Summarize files changed.
3. Explain how to rerun pipeline safely.
4. State whether Phase 10A is ready for GPT-5.4 review.
```

---

## Prompt 3 — Review Phase 10A

Use GPT-5.4.

```text
Review Phase 10A — SEC Fundamentals Fallback.

Check:
1. FMP remains primary.
2. SEC fallback runs only when FMP statements are unavailable/empty/provider-limited.
3. SEC fallback is US/CIK-based.
4. Annual facts are selected conservatively.
5. statements_norm receives correct canonical fields.
6. free_cash_flow is derived safely.
7. FMP data is not overwritten incorrectly.
8. Provenance/diagnostics are present and safe.
9. No live APIs are used in tests.
10. No secrets are logged or persisted.
11. Ratios/valuation can consume SEC-derived statements when price exists.
12. Backend tests pass.

Return:
1. Critical issues.
2. Recommended fixes.
3. Whether Phase 10A is ready for manual testing.
```

---

## Prompt 4 — Repository-specific Phase 10B implementation plan

Use GPT-5.4 after Phase 10A is stable.

```text
Create a repository-specific implementation plan for Phase 10B — Twelve Data Price Fallback.

Do not implement code.

Goal:
Use Twelve Data as fallback for price_eod when FMP price data fails, returns empty data, or returns provider-limited status.

Cover:
1. connector design;
2. env vars;
3. raw provider storage;
4. normalization into price_eod;
5. incremental fetch;
6. rate limits/free-tier constraints;
7. diagnostics;
8. tests;
9. manual validation.
```

---

## Prompt 5 — Implement Phase 10B

Use Claude Sonnet 4.6 after the Phase 10B plan is accepted.

```text
Implement Phase 10B — Twelve Data Price Fallback.

Do not change fundamentals fallback.
Do not change financial model logic.
Do not expose TWELVE_DATA_API_KEY to frontend.
Do not call live APIs in tests.

Tasks:
1. Add Twelve Data backend connector.
2. Add price normalizer.
3. Integrate fallback after FMP price failure/empty/provider-limited.
4. Upsert into price_eod.
5. Add sanitized diagnostics.
6. Add tests with fixtures only.
7. Run backend tests.
```
