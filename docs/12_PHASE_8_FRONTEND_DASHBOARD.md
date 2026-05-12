# 12 — Phase 8: Cloudflare Pages Frontend Dashboard

## Objective

Build a simple read-only dashboard hosted on Cloudflare Pages.

## Scope

Create a React + Vite + TypeScript frontend that reads Supabase dashboard views.

## Agent instructions

The frontend must not contain service-role keys or provider API keys. It must be read-only in MVP.

## Pages

### 1. Watchlist page

Table columns:

- ticker;
- company name;
- price;
- IV P25/P50/P75;
- conservative margin of safety;
- quality score;
- p_buy_adjusted;
- p_sell;
- final signal;
- freshness flag;
- red flags.

Data source:

- `dashboard_watchlist_latest`

### 2. Company detail page

Sections:

- current signal summary;
- valuation range;
- DCF assumptions;
- financial ratios;
- quality score breakdown;
- latest filings;
- recent news;
- signal history.

### 3. Alerts page

Show:

- recent alert history;
- alert status;
- failed alerts.

Configuration editing can be added after MVP.

## UI requirements

- clear signal badges;
- no misleading trading language;
- show disclaimer: “Private research tool. Not financial advice.”;
- show data freshness;
- show model version;
- show last pipeline run status.

## Supabase client

Use only:

```env
VITE_SUPABASE_URL
VITE_SUPABASE_ANON_KEY
```

## Cloudflare deployment

Create a Cloudflare Pages project connected to GitHub.

Build command:

```bash
npm run build
```

Output directory:

```text
dist
```

## Acceptance criteria

- Dashboard deploys to Cloudflare Pages.
- Watchlist page loads data from Supabase.
- No secret keys are exposed in client code.
- Empty states are handled gracefully.
- Build passes in CI.

## Suggested commit message

```text
feat: add read-only investment dashboard
```
