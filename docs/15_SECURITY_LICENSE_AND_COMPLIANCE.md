# 15 — Security, Licensing and Compliance

## Purpose

This document defines guardrails for using the MVP safely as a private research tool.

## Security rules

1. Never commit `.env` files.
2. Never expose service-role keys in frontend code.
3. Use GitHub Secrets for backend credentials.
4. Use Supabase anon key only in frontend.
5. Keep Row Level Security enabled.
6. Use least privilege when adding future users.
7. Log errors without printing full secrets.
8. Rotate keys if accidentally exposed.

## Data licensing rules

Many free market-data APIs are suitable for personal/internal prototyping but restrict redistribution, public display or commercial use.

MVP rule:

- keep the app private;
- do not publicly display raw provider data;
- do not sell access to the dashboard;
- do not publish automated recommendations;
- review provider terms before expanding beyond personal use.

## Investment compliance rules

This app must be framed as a private research and education tool.

Avoid public claims such as:

- “Buy this stock now.”
- “Guaranteed upside.”
- “Investment recommendation.”
- “Target price for clients.”

Use language such as:

- “Private research signal.”
- “Model output based on assumptions.”
- “Not financial advice.”
- “For educational analysis only.”

## Dashboard disclaimer

Include this disclaimer visibly:

```text
This is a private research tool for educational purposes. It is not financial advice, investment advice, or a recommendation to buy or sell securities. Outputs depend on assumptions, data quality and model limitations.
```

## Model-risk controls

- Show data freshness.
- Show assumptions.
- Show uncertainty range.
- Show red flags.
- Keep model version history.
- Keep qualitative overrides auditable.
- Avoid black-box-only outputs.

## Public release checklist

Before any public release:

- review all data-provider licenses;
- obtain legal review for investment-recommendation rules;
- remove or license restricted market data;
- add terms of use;
- add privacy policy;
- add user authentication and access control;
- add monitoring and abuse prevention.
