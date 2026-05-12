"""Phase 7 alert evaluation and delivery orchestration."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from investment_app.alerts.email_alerts import send_email_alert
from investment_app.alerts.telegram_alerts import send_telegram_alert
from investment_app.utils.dates import utc_now

# Channel names recognised by the SQL schema check constraint.
_VALID_CHANNELS: frozenset[str] = frozenset({"email", "telegram"})

# Map channel name → human-readable tag for sanitized error messages.
_CHANNEL_TAGS: dict[str, str] = {"email": "smtp", "telegram": "telegram"}

RULE_TYPES: frozenset[str] = frozenset(
	{
		"p_buy_adjusted_above",
		"p_sell_above",
		"signal_changed",
		"margin_of_safety_above",
		"new_filing_detected",
		"red_flag_detected",
		"intrinsic_value_change_above",
	}
)


def _sanitize_error(exc: Exception, *, channel: str | None) -> str:
	"""Return a short, secret-free description of a delivery failure.

	Never persist raw exception messages, URLs, request bodies, tokens, or
	credentials.  Only the exception class name and a fixed channel tag are
	included so persisted error records cannot expose secrets.
	"""
	tag = _CHANNEL_TAGS.get(channel or "", "delivery")
	return f"{tag}_send_failed ({type(exc).__name__})"


def _safe_float(value: Any) -> float | None:
	if value is None:
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _date_not_after(value: str | None, as_of_date: str) -> bool:
	if not value:
		return False
	try:
		return date.fromisoformat(value) <= date.fromisoformat(as_of_date)
	except ValueError:
		return False


def _rounded_threshold(threshold: float | None) -> str:
	return "none" if threshold is None else f"{threshold:.4f}"


def _build_dedupe_key(
	*,
	company_id: str,
	rule: dict[str, Any],
	signal_row: dict[str, Any],
	filing_row: dict[str, Any] | None = None,
) -> str:
	rule_type = rule.get("rule_type", "unknown")
	if rule_type == "new_filing_detected" and filing_row is not None:
		accession = filing_row.get("accession_number") or filing_row.get("id") or "unknown"
		return f"{company_id}:new_filing:{accession}"
	threshold = _safe_float(rule.get("threshold"))
	return (
		f"{company_id}:{rule_type}:{signal_row.get('signal_date')}:"
		f"{_rounded_threshold(threshold)}:{signal_row.get('final_signal')}"
	)


def _crossed_above(current: float | None, previous: float | None, threshold: float | None) -> bool:
	if current is None or threshold is None:
		return False
	return current >= threshold and (previous is None or previous < threshold)


def _relative_change(current: float | None, previous: float | None) -> float | None:
	if current is None or previous is None or previous == 0.0:
		return None
	return abs((current - previous) / previous)


def _latest_relevant_filing(
	filings: list[dict[str, Any]],
	*,
	signal_date: str,
) -> dict[str, Any] | None:
	for filing in filings:
		filing_date = filing.get("filing_date")
		accepted_at = filing.get("accepted_at")
		if _date_not_after(filing_date, signal_date):
			return filing
		if accepted_at and accepted_at[:10] <= signal_date:
			return filing
	return None


def _build_alert_title(
	*,
	company: dict[str, Any],
	rule_type: str,
	signal_row: dict[str, Any],
) -> str:
	ticker = company.get("ticker", "UNKNOWN")
	final_signal = str(signal_row.get("final_signal", "hold")).upper()
	titles = {
		"p_buy_adjusted_above": f"{ticker} buy probability above threshold",
		"p_sell_above": f"{ticker} sell probability above threshold",
		"signal_changed": f"{ticker} signal changed to {final_signal}",
		"margin_of_safety_above": f"{ticker} margin of safety above threshold",
		"new_filing_detected": f"{ticker} new filing detected",
		"red_flag_detected": f"{ticker} new red flag detected",
		"intrinsic_value_change_above": f"{ticker} intrinsic value changed materially",
	}
	return titles.get(rule_type, f"{ticker} alert")


def _build_alert_message(
	*,
	company: dict[str, Any],
	signal_row: dict[str, Any],
	valuation_row: dict[str, Any] | None,
	current_filing: dict[str, Any] | None,
	detail_line: str | None,
) -> str:
	ticker = company.get("ticker", "UNKNOWN")
	currency = company.get("currency", "USD")
	lines = [f"{ticker} signal: {signal_row.get('final_signal')}"]

	if valuation_row is not None:
		current_price = valuation_row.get("current_price")
		if current_price is not None:
			lines.append(f"Price: {float(current_price):.2f} {currency}")
		iv_p10 = valuation_row.get("iv_p10")
		iv_p90 = valuation_row.get("iv_p90")
		if iv_p10 is not None and iv_p90 is not None:
			lines.append(f"IV range: {float(iv_p10):.2f}-{float(iv_p90):.2f} {currency}")
		mos = valuation_row.get("margin_of_safety_conservative")
		if mos is not None:
			lines.append(f"MOS conservative: {float(mos):.1%}")

	p_buy_adjusted = signal_row.get("p_buy_adjusted")
	if p_buy_adjusted is not None:
		lines.append(f"p_buy_adjusted: {float(p_buy_adjusted):.2f}")

	if current_filing is not None:
		filing_type = current_filing.get("filing_type") or "filing"
		accession = current_filing.get("accession_number")
		lines.append(f"Latest filing: {filing_type}{f' ({accession})' if accession else ''}")

	if detail_line:
		lines.append(detail_line)

	explanation = signal_row.get("explanation")
	if explanation:
		lines.append(f"Reason: {explanation}")

	return "\n".join(lines)


def _rule_match(
	*,
	rule: dict[str, Any],
	signal_row: dict[str, Any],
	previous_signal: dict[str, Any] | None,
	current_valuation: dict[str, Any] | None,
	previous_valuation: dict[str, Any] | None,
	filings: list[dict[str, Any]],
	signal_date: str,
) -> tuple[bool, str | None, dict[str, Any] | None]:
	rule_type = rule.get("rule_type")
	threshold = _safe_float(rule.get("threshold"))
	final_signal = signal_row.get("final_signal")

	if rule_type not in RULE_TYPES:
		return False, None, None

	if final_signal == "insufficient_data" and rule_type != "new_filing_detected":
		return False, None, None

	if rule_type == "p_buy_adjusted_above":
		current = _safe_float(signal_row.get("p_buy_adjusted"))
		previous = _safe_float((previous_signal or {}).get("p_buy_adjusted"))
		matched = _crossed_above(current, previous, threshold)
		return matched, None, None

	if rule_type == "p_sell_above":
		current = _safe_float(signal_row.get("p_sell"))
		previous = _safe_float((previous_signal or {}).get("p_sell"))
		matched = _crossed_above(current, previous, threshold)
		return matched, None, None

	if rule_type == "signal_changed":
		prev_label = (previous_signal or {}).get("final_signal")
		matched = bool(previous_signal) and prev_label != final_signal and final_signal != "insufficient_data"
		return matched, None, None

	if rule_type == "margin_of_safety_above":
		current = _safe_float((current_valuation or {}).get("margin_of_safety_conservative"))
		previous = _safe_float((previous_valuation or {}).get("margin_of_safety_conservative"))
		matched = _crossed_above(current, previous, threshold)
		return matched, None, None

	if rule_type == "intrinsic_value_change_above":
		current = _safe_float((current_valuation or {}).get("iv_p50"))
		previous = _safe_float((previous_valuation or {}).get("iv_p50"))
		change = _relative_change(current, previous)
		matched = change is not None and threshold is not None and change >= threshold
		detail = None if change is None else f"IV change: {change:.1%}"
		return matched, detail, None

	if rule_type == "red_flag_detected":
		current_flags = set(signal_row.get("red_flags") or [])
		previous_flags = set((previous_signal or {}).get("red_flags") or [])
		new_flags = sorted(current_flags - previous_flags)
		matched = bool(new_flags)
		detail = None if not new_flags else f"New red flags: {', '.join(new_flags)}"
		return matched, detail, None

	if rule_type == "new_filing_detected":
		filing = _latest_relevant_filing(filings, signal_date=signal_date)
		if filing is None:
			return False, None, None
		filing_date = filing.get("filing_date")
		previous_signal_date = (previous_signal or {}).get("signal_date")
		matched = previous_signal is None or (
			filing_date is not None and previous_signal_date is not None and filing_date > previous_signal_date
		)
		detail = None
		if filing.get("filing_type"):
			detail = f"New filing: {filing.get('filing_type')}"
		return matched, detail, filing

	return False, None, None


def process_company_alerts(
	company_id: str,
	repo_module: Any,
	alert_date: str,
	*,
	company: dict[str, Any],
	settings: Any,
	send_email_fn: Callable[..., None] = send_email_alert,
	send_telegram_fn: Callable[..., None] = send_telegram_alert,
) -> dict[str, int]:
	"""Evaluate configured rules and deliver any newly-triggered alerts."""
	counts = {"alerts_sent": 0, "alert_history_written": 0, "alerts_deduplicated": 0}

	# Global disable: return immediately without evaluating rules or touching the DB.
	if not getattr(settings, "alerts_enabled", False):
		return counts

	signal_rows = repo_module.get_signal_runs_for_company(
		company_id, as_of_date=alert_date, limit=2
	)
	if not signal_rows:
		return counts
	current_signal = signal_rows[0]
	previous_signal = signal_rows[1] if len(signal_rows) > 1 else None

	valuation_rows = repo_module.get_valuation_runs_for_company(
		company_id, as_of_date=alert_date, limit=2
	)
	current_valuation = valuation_rows[0] if valuation_rows else None
	previous_valuation = valuation_rows[1] if len(valuation_rows) > 1 else None
	filings = repo_module.get_filings_for_company(company_id, as_of_date=alert_date, limit=5)
	rules = repo_module.get_enabled_alert_rules(company_id)

	for rule in rules:
		matched, detail_line, current_filing = _rule_match(
			rule=rule,
			signal_row=current_signal,
			previous_signal=previous_signal,
			current_valuation=current_valuation,
			previous_valuation=previous_valuation,
			filings=filings,
			signal_date=alert_date,
		)
		if not matched:
			continue

		dedupe_key = _build_dedupe_key(
			company_id=company_id,
			rule=rule,
			signal_row=current_signal,
			filing_row=current_filing,
		)
		if repo_module.get_alert_history_by_dedupe(dedupe_key):
			# Duplicate: rule fired again for the same dedupe key that was already
			# handled.  Record in metrics for auditability; we cannot write a second
			# alert_history row because of the unique(dedupe_key) schema constraint.
			counts["alerts_deduplicated"] += 1
			continue

		title = _build_alert_title(
			company=company,
			rule_type=rule.get("rule_type", "unknown"),
			signal_row=current_signal,
		)
		message = _build_alert_message(
			company=company,
			signal_row=current_signal,
			valuation_row=current_valuation,
			current_filing=current_filing,
			detail_line=detail_line,
		)

		status = "sent"
		sent_at: str | None = utc_now().isoformat()
		error_message: str | None = None
		channel = rule.get("channel")

		# Per-channel disable: skip delivery silently — intentional disablement
		# must not produce failed alert_history rows.
		if channel == "email" and not getattr(settings, "smtp_enabled", False):
			continue
		if channel == "telegram" and not getattr(settings, "telegram_enabled", False):
			continue

		try:
			if channel == "email":
				send_email_fn(title=title, message=message, settings=settings)
			elif channel == "telegram":
				send_telegram_fn(title=title, message=message, settings=settings)
			else:
				raise ValueError("Unsupported alert channel")
		except Exception as exc:  # noqa: BLE001
			status = "failed"
			sent_at = None
			# Sanitize: never persist raw exception messages, URLs, or tokens.
			error_message = _sanitize_error(exc, channel=channel)

		repo_module.insert_alert_history(
			{
				"alert_rule_id": rule.get("id"),
				"company_id": company_id,
				"signal_run_id": current_signal.get("id"),
				"channel": channel,
				"title": title,
				"message": message,
				"dedupe_key": dedupe_key,
				"status": status,
				"sent_at": sent_at,
				"error_message": error_message,
			}
		)
		counts["alert_history_written"] += 1
		if status == "sent":
			counts["alerts_sent"] += 1

	return counts
