# 00 — Project Brief

## Product goal

Build a private investment-analysis application that helps the user monitor a predefined list of public companies and produces a daily analytical snapshot covering:

- price and market data;
- fundamentals and financial statements;
- financial ratios;
- intrinsic value ranges;
- margin of safety;
- qualitative score;
- probabilistic buy/sell/hold signal;
- explanation of what changed since the previous run;
- configurable alerts through email and Telegram.

The application should support gradual development and remain transparent. The output must not be a black-box recommendation engine. Every score and signal must be traceable to source data, assumptions, and model version.

## MVP scope

The first MVP should focus on a small watchlist of approximately 10–30 companies. It should prioritise US-listed companies first because SEC data is structured and free. European and Portuguese companies can be added later through CMVM, issuer investor-relations pages, and ESEF annual reports.

The MVP must be private-use only.

## Selected technology stack

- Python 3.11+
- Supabase Postgres
- GitHub Actions scheduled workflow
- Cloudflare Pages frontend
- Email alerts through SMTP
- Telegram alerts through Bot API
- Optional market-data providers: Financial Modeling Prep, Finnhub, Alpha Vantage, Twelve Data, SEC EDGAR, ECB FX, GDELT news

## Design principles

1. Point-in-time storage: never overwrite analytical history without keeping the previous state.
2. Raw data first: store raw provider responses before normalising.
3. Conservative valuation: output a range, not a single target price.
4. Explainability first: every signal must show drivers, penalties, and red flags.
5. Auditability: all model runs, assumptions, overrides and alerts must be logged.
6. Private usage: avoid redistribution of licensed market data.
7. Phased delivery: each phase must be independently testable.

## Core daily workflow

1. Load watchlist.
2. Fetch prices, FX, filings, fundamentals, and news.
3. Store raw responses with checksums.
4. Normalise financial statements and market data.
5. Compute ratios and features.
6. Run valuation models.
7. Run qualitative score rules.
8. Run probabilistic signal engine.
9. Persist a daily snapshot.
10. Trigger alerts if thresholds are crossed.
11. Update the dashboard.

## Non-goals for MVP

- Intraday trading signals.
- Broker integration.
- Automatic order execution.
- Public investment recommendations.
- Portfolio optimisation.
- Full global exchange coverage.
- Paid data-provider integration unless free tier is insufficient.

## First version success criteria

The MVP is successful when it can:

- run automatically once per day through GitHub Actions;
- process at least 10 companies without manual intervention;
- persist raw and normalised data in Supabase;
- calculate basic valuation range and margin of safety;
- assign transparent rule-based probability scores;
- display the watchlist in a Cloudflare Pages dashboard;
- send Telegram/email alerts for material changes;
- keep logs sufficient to debug failures.
