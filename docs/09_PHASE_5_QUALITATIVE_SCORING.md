# 09 — Phase 5: Qualitative Scoring

## Objective

Implement a transparent qualitative scoring framework inspired by value investing concepts: moat, management, risks and governance.

## Scope

This phase creates automated qualitative scores plus optional human overrides.

## Agent instructions

Do not use LLM-generated judgments as the primary scoring method in MVP. Use rules based on observable data. Human override must be auditable.

## Required module

- `src/investment_app/scoring/qualitative.py`

## Score structure

Final qualitative score is 0–100.

Weights:

```text
final_quality_score =
  0.35 * moat_score +
  0.25 * management_score +
  0.25 * risk_score +
  0.15 * governance_score +
  human_override
```

Clamp final score between 0 and 100.

## Moat score

MVP automated evidence:

- ROIC above estimated WACC;
- stable or expanding gross margin;
- positive FCF in most recent years;
- revenue stability;
- low share dilution;
- high recurring revenue if manually tagged in metadata.

Scoring example:

- start at 50;
- add points for persistent ROIC > WACC;
- add points for stable margins;
- subtract points for volatile margins or repeated negative FCF.

## Management score

MVP automated evidence:

- share count trend;
- buybacks when valuation appears attractive;
- dividend discipline;
- acquisition/capex intensity;
- consistency of FCF conversion.

## Risk score

This is an inverted score: higher is better, lower means more risk.

MVP negative evidence:

- high net debt / EBITDA;
- weak interest coverage;
- high cyclicality tag;
- negative news concentration;
- falling revenue and margin together;
- recent dividend cut if data exists.

## Governance score

MVP evidence:

- restatement flags;
- excessive share-based compensation if available;
- unusual dilution;
- missing filings;
- auditor/internal-control flags if detected later.

## Human override

Allow `human_override` between -10 and +10 only.

Required fields:

- override value;
- reason;
- evidence notes;
- timestamp;
- model version.

## Acceptance criteria

- `qualitative_scores` is populated daily or when data changes.
- Override is clamped between -10 and +10.
- Every score includes evidence JSON.
- Tests cover score calculation and clamping.

## Suggested commit message

```text
feat: add qualitative scoring framework
```
