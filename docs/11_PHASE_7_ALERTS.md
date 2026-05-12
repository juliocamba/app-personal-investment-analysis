# 11 — Phase 7: Alerts

## Objective

Send configurable alerts through email and Telegram when material changes occur.

## Scope

Implement alert rules and delivery channels.

## Agent instructions

Alerts must be deduplicated. Do not send repeated alerts every run unless the underlying condition changed materially.

## Required modules

- `src/investment_app/alerts/rules.py`
- `src/investment_app/alerts/email_alerts.py`
- `src/investment_app/alerts/telegram_alerts.py`

## Alert rule types

Implement these MVP rule types:

- `p_buy_adjusted_above`
- `p_sell_above`
- `signal_changed`
- `margin_of_safety_above`
- `new_filing_detected`
- `red_flag_detected`
- `intrinsic_value_change_above`

## Email alerts

Use SMTP.

Requirements:

- configurable enable/disable;
- plain text first;
- concise subject;
- include company ticker, signal, price, IV range and explanation;
- log result into `alert_history`.

## Telegram alerts

Use Telegram Bot API.

Requirements:

- configurable enable/disable;
- send Markdown-safe message;
- include key metrics only;
- log result into `alert_history`.

## Deduplication

Create dedupe key:

```text
{company_id}:{rule_type}:{signal_date}:{rounded_threshold_value}:{final_signal}
```

For filing alerts:

```text
{company_id}:new_filing:{accession_number}
```

## Example alert message

```text
AAPL signal changed to BUY
Price: 180.25 USD
IV range: 170.00–230.00 USD
MOS conservative: 12.4%
p_buy_adjusted: 0.64
Reason: margin of safety improved and quality score remains strong.
```

## Pipeline integration

Run alerts after `signal_runs` is written.

## Acceptance criteria

- Alerts can be disabled globally via `ALERTS_ENABLED=false` (the default).
  When disabled, `process_company_alerts` returns immediately with zero counts;
  no rules are evaluated and no rows are written to `alert_history`.
- Per-channel disable (`SMTP_ENABLED=false` or `TELEGRAM_ENABLED=false`) silently
  skips delivery for that channel without writing a failed `alert_history` row.
- Delivery failures are recorded as `status='failed'` with a sanitized
  `error_message` that contains only a channel tag and exception class name —
  never raw exception text, URLs, tokens, or credentials.
- Deduplicated alerts are counted in the returned metrics (`alerts_deduplicated`)
  and propagated to pipeline-level metrics, providing a full audit trail without
  violating the `unique(dedupe_key)` schema constraint.
- Telegram and email senders can be tested in dry-run mode.
- Alert history is persisted.
- Duplicate alerts are not sent.
- Failures do not fail the full pipeline unless configured.

## Suggested commit message

```text
feat: add email and telegram alerts
```
