"""Phase 12D.1 persisted review alerts for open positions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from investment_app.utils.dates import utc_now

ALERT_TYPE_TARGET_PRICE_REACHED = "target_price_reached"
ALERT_TYPE_SIGNAL_DETERIORATION = "signal_deterioration"
ALERT_TYPE_READINESS_DETERIORATION = "readiness_deterioration"
ALERT_TYPE_DATA_QUALITY_DETERIORATION = "data_quality_deterioration"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

STATUS_OPEN = "open"
STATUS_SNOOZED = "snoozed"
STATUS_DISMISSED = "dismissed"
STATUS_RESOLVED = "resolved"
_ACTIVE_STATUSES = {STATUS_OPEN, STATUS_SNOOZED, STATUS_DISMISSED}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _lower(value: Any) -> str | None:
    text = _text(value)
    return text.lower() if text else None


def _title(ticker: str, title: str) -> str:
    return f"{ticker} {title}"


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _build_target_price_alert(
    position: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    target_price = _safe_float(profile.get("target_price"))
    current_price = _safe_float(position.get("current_price"))
    if target_price is None or current_price is None:
        return None

    target_currency = _text(profile.get("target_price_currency")) or _text(position.get("currency"))
    price_currency = _text(position.get("price_currency"))
    if not target_currency or not price_currency or target_currency != price_currency:
        return None

    if current_price < target_price:
        return None

    ticker = position.get("ticker", "UNKNOWN")
    return {
        "alert_type": ALERT_TYPE_TARGET_PRICE_REACHED,
        "severity": SEVERITY_WARNING,
        "title": _title(ticker, "target price reached"),
        "message": (
            "The latest stored price has reached or exceeded the manual target price "
            "recorded for this position. Review the thesis and current state."
        ),
        "details": {
            "entry_target_price": target_price,
            "target_price_currency": target_currency,
            "current_price": current_price,
            "price_currency": price_currency,
            "price_date": position.get("price_date"),
        },
        "dedupe_key": f"{position.get('id')}:{ALERT_TYPE_TARGET_PRICE_REACHED}:{target_price:.4f}:{target_currency}",
    }


def _build_signal_deterioration_alert(
    position: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    entry_signal = _lower(profile.get("entry_signal"))
    current_signal = _lower(position.get("current_signal"))
    if not entry_signal or not current_signal or entry_signal == current_signal:
        return None

    severity: str | None = None
    if entry_signal == "strong_buy" and current_signal == "hold":
        severity = SEVERITY_WARNING
    elif entry_signal in {"strong_buy", "buy"} and current_signal == "sell":
        severity = SEVERITY_WARNING
    elif entry_signal in {"strong_buy", "buy"} and current_signal == "strong_sell":
        severity = SEVERITY_CRITICAL

    if severity is None:
        return None

    ticker = position.get("ticker", "UNKNOWN")
    return {
        "alert_type": ALERT_TYPE_SIGNAL_DETERIORATION,
        "severity": severity,
        "title": _title(ticker, "signal changed materially since entry"),
        "message": (
            "The latest stored signal is materially weaker than the signal captured at "
            "entry. Review the thesis and current analytical state."
        ),
        "details": {
            "entry_signal": entry_signal,
            "current_signal": current_signal,
        },
        "dedupe_key": (
            f"{position.get('id')}:{ALERT_TYPE_SIGNAL_DETERIORATION}:"
            f"{entry_signal}:{current_signal}"
        ),
    }


def _build_readiness_deterioration_alert(
    position: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    entry_status = _lower(profile.get("entry_readiness_status"))
    current_status = _lower(position.get("current_readiness_status"))
    if not entry_status or not current_status or entry_status == current_status:
        return None

    severity: str | None = None
    if entry_status in {"analysis_ready", "partial_analysis"} and current_status == "provider_limited":
        severity = SEVERITY_WARNING
    elif entry_status in {"analysis_ready", "partial_analysis"} and current_status in {
        "tracking_only",
        "unsupported_for_analysis",
    }:
        severity = SEVERITY_CRITICAL

    if severity is None:
        return None

    ticker = position.get("ticker", "UNKNOWN")
    return {
        "alert_type": ALERT_TYPE_READINESS_DETERIORATION,
        "severity": severity,
        "title": _title(ticker, "readiness deteriorated since entry"),
        "message": (
            "The latest stored readiness state is materially weaker than the state "
            "captured at entry. Review current coverage and confidence carefully."
        ),
        "details": {
            "entry_readiness_status": entry_status,
            "current_readiness_status": current_status,
        },
        "dedupe_key": (
            f"{position.get('id')}:{ALERT_TYPE_READINESS_DETERIORATION}:"
            f"{entry_status}:{current_status}"
        ),
    }


def _build_data_quality_deterioration_alert(
    position: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    entry_status = _lower(profile.get("entry_data_quality_status"))
    current_status = _lower(position.get("current_data_quality_status"))
    if not current_status or current_status != "critical" or entry_status == "critical":
        return None

    ticker = position.get("ticker", "UNKNOWN")
    return {
        "alert_type": ALERT_TYPE_DATA_QUALITY_DETERIORATION,
        "severity": SEVERITY_CRITICAL,
        "title": _title(ticker, "data quality deteriorated materially"),
        "message": (
            "The latest stored data-quality status is now critical. Review the "
            "position using extra caution until the underlying data issues are understood."
        ),
        "details": {
            "entry_data_quality_status": entry_status,
            "current_data_quality_status": current_status,
        },
        "dedupe_key": (
            f"{position.get('id')}:{ALERT_TYPE_DATA_QUALITY_DETERIORATION}:"
            f"{entry_status or 'none'}:{current_status}"
        ),
    }


def _candidate_alerts(
    position: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    builders = (
        _build_target_price_alert,
        _build_signal_deterioration_alert,
        _build_readiness_deterioration_alert,
        _build_data_quality_deterioration_alert,
    )
    alerts: list[dict[str, Any]] = []
    for builder in builders:
        alert = builder(position, profile)
        if alert is not None:
            alerts.append(alert)
    return alerts


def process_position_review_alerts(
    repo_module: Any,
    alert_date: str,
) -> dict[str, int]:
    """Evaluate persisted review-alert conditions using stored state only."""
    counts = {
        "position_review_positions_checked": 0,
        "position_review_alerts_opened": 0,
        "position_review_alerts_refreshed": 0,
        "position_review_alerts_resolved": 0,
    }

    positions = repo_module.list_dashboard_positions()
    profiles = repo_module.list_position_entry_profiles()
    existing_alerts = repo_module.list_position_review_alerts()
    profile_by_position = {row.get("position_id"): row for row in profiles}
    existing_by_dedupe = {
        row.get("dedupe_key"): row
        for row in existing_alerts
        if row.get("dedupe_key")
    }

    now_dt = utc_now()
    now_iso = now_dt.isoformat()
    active_dedupes: set[str] = set()

    for position in positions:
        if position.get("status") != "active":
            continue
        profile = profile_by_position.get(position.get("id"))
        if not profile:
            continue

        counts["position_review_positions_checked"] += 1
        for alert in _candidate_alerts(position, profile):
            dedupe_key = alert["dedupe_key"]
            active_dedupes.add(dedupe_key)
            existing = existing_by_dedupe.get(dedupe_key)

            if existing:
                update_fields: dict[str, Any] = {
                    "severity": alert["severity"],
                    "title": alert["title"],
                    "message": alert["message"],
                    "details": alert["details"],
                    "last_seen_at": now_iso,
                }
                if existing.get("status") == STATUS_RESOLVED:
                    update_fields.update(
                        {
                            "status": STATUS_OPEN,
                            "triggered_at": now_iso,
                            "first_seen_at": now_iso,
                            "resolved_at": None,
                            "dismissed_at": None,
                            "dismissed_reason": None,
                            "snoozed_until": None,
                        }
                    )
                    counts["position_review_alerts_opened"] += 1
                elif existing.get("status") == STATUS_SNOOZED:
                    snoozed_until = _parse_iso_datetime(existing.get("snoozed_until"))
                    if snoozed_until is None or snoozed_until <= now_dt:
                        update_fields.update(
                            {
                                "status": STATUS_OPEN,
                                "dismissed_at": None,
                                "dismissed_reason": None,
                                "snoozed_until": None,
                            }
                        )
                    counts["position_review_alerts_refreshed"] += 1
                elif existing.get("status") == STATUS_DISMISSED:
                    counts["position_review_alerts_refreshed"] += 1
                else:
                    counts["position_review_alerts_refreshed"] += 1
                repo_module.update_position_review_alert(existing["id"], update_fields)
                continue

            repo_module.insert_position_review_alert(
                {
                    "position_id": position.get("id"),
                    "user_id": position.get("user_id"),
                    "company_id": position.get("company_id"),
                    "alert_type": alert["alert_type"],
                    "severity": alert["severity"],
                    "status": STATUS_OPEN,
                    "title": alert["title"],
                    "message": alert["message"],
                    "details": alert["details"],
                    "dedupe_key": dedupe_key,
                    "triggered_at": now_iso,
                    "first_seen_at": now_iso,
                    "last_seen_at": now_iso,
                }
            )
            counts["position_review_alerts_opened"] += 1

    for existing in existing_alerts:
        dedupe_key = existing.get("dedupe_key")
        if not dedupe_key or dedupe_key in active_dedupes:
            continue
        if existing.get("status") not in _ACTIVE_STATUSES:
            continue
        repo_module.update_position_review_alert(
            existing["id"],
            {
                "status": STATUS_RESOLVED,
                "resolved_at": now_iso,
            },
        )
        counts["position_review_alerts_resolved"] += 1

    return counts
