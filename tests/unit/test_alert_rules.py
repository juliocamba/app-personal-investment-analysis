"""Unit tests for Phase 7 alert rules and delivery adapters."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from investment_app.alerts.email_alerts import send_email_alert
from investment_app.alerts.rules import process_company_alerts
from investment_app.alerts.telegram_alerts import send_telegram_alert


class _FakeAlertRepo:
    def __init__(
        self,
        *,
        signals: list[dict[str, Any]] | None = None,
        valuations: list[dict[str, Any]] | None = None,
        filings: list[dict[str, Any]] | None = None,
        rules: list[dict[str, Any]] | None = None,
        history: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._signals = signals or []
        self._valuations = valuations or []
        self._filings = filings or []
        self._rules = rules or []
        self._history = history or {}
        self.inserted_history: list[dict[str, Any]] = []

    def get_signal_runs_for_company(self, company_id: str, *, as_of_date: str | None = None, limit: int = 2) -> list[dict[str, Any]]:
        return self._signals[:limit]

    def get_valuation_runs_for_company(self, company_id: str, *, as_of_date: str | None = None, limit: int = 2) -> list[dict[str, Any]]:
        return self._valuations[:limit]

    def get_filings_for_company(self, company_id: str, *, as_of_date: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        return self._filings[:limit]

    def get_enabled_alert_rules(self, company_id: str | None = None) -> list[dict[str, Any]]:
        return self._rules

    def get_alert_history_by_dedupe(self, dedupe_key: str) -> dict[str, Any] | None:
        return self._history.get(dedupe_key)

    def insert_alert_history(self, row: dict[str, Any]) -> dict[str, Any]:
        self.inserted_history.append(row)
        self._history[row["dedupe_key"]] = row
        return row


def _settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "alerts_enabled": True,
        "smtp_enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "user",
        "smtp_password": "secret",
        "alert_email_from": "alerts@example.com",
        "alert_email_to": "me@example.com",
        "telegram_enabled": True,
        "telegram_bot_token": "token",
        "telegram_chat_id": "chat-id",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


_COMPANY = {"id": "cid-001", "ticker": "AAPL", "currency": "USD"}
_SIGNAL_DATE = "2025-01-01"
_SIGNAL = {
    "id": "sig-001",
    "signal_date": _SIGNAL_DATE,
    "final_signal": "buy",
    "p_buy_adjusted": 0.66,
    "p_sell": 0.20,
    "red_flags": [],
    "explanation": "valuation improved and quality remains strong",
}
_PREV_SIGNAL = {
    "id": "sig-000",
    "signal_date": "2024-12-31",
    "final_signal": "hold",
    "p_buy_adjusted": 0.54,
    "p_sell": 0.22,
    "red_flags": [],
    "explanation": "previous state",
}
_VALUATION = {
    "id": "val-001",
    "valuation_date": _SIGNAL_DATE,
    "current_price": 180.25,
    "iv_p10": 170.0,
    "iv_p90": 230.0,
    "iv_p50": 200.0,
    "margin_of_safety_conservative": 0.124,
}
_PREV_VALUATION = {
    "id": "val-000",
    "valuation_date": "2024-12-31",
    "current_price": 181.0,
    "iv_p10": 160.0,
    "iv_p90": 220.0,
    "iv_p50": 180.0,
    "margin_of_safety_conservative": 0.05,
}
_FILING = {
    "id": "fil-001",
    "filing_type": "10-K",
    "filing_date": _SIGNAL_DATE,
    "accession_number": "0000000000-25-000001",
}


def test_alert_rule_filtering_and_threshold_match():
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )
    sent: list[tuple[str, str]] = []

    metrics = process_company_alerts(
        _COMPANY["id"],
        repo,
        _SIGNAL_DATE,
        company=_COMPANY,
        settings=_settings(),
        send_email_fn=lambda **kwargs: sent.append((kwargs["title"], kwargs["message"])),
        send_telegram_fn=lambda **kwargs: None,
    )
    assert metrics["alerts_sent"] == 1
    assert metrics["alert_history_written"] == 1
    assert len(sent) == 1


def test_disabled_rules_not_returned_not_triggered():
    repo = _FakeAlertRepo(signals=[_SIGNAL, _PREV_SIGNAL], valuations=[_VALUATION, _PREV_VALUATION], rules=[])
    sent: list[str] = []
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY, settings=_settings(),
        send_email_fn=lambda **kwargs: sent.append("email"),
        send_telegram_fn=lambda **kwargs: sent.append("telegram"),
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 0
    assert sent == []


def test_duplicate_suppression_skips_repeat_alert():
    existing_key = f"{_COMPANY['id']}:p_buy_adjusted_above:{_SIGNAL_DATE}:0.6000:buy"
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
        history={existing_key: {"dedupe_key": existing_key}},
    )
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY, settings=_settings(),
        send_email_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not send")),
        send_telegram_fn=lambda **kwargs: None,
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 0
    assert metrics["alerts_deduplicated"] == 1


def test_insufficient_data_suppresses_threshold_alerts():
    repo = _FakeAlertRepo(
        signals=[{**_SIGNAL, "final_signal": "insufficient_data"}, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY, settings=_settings(),
        send_email_fn=lambda **kwargs: None,
        send_telegram_fn=lambda **kwargs: None,
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 0


def test_new_filing_detected_uses_accession_dedupe():
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        filings=[_FILING],
        rules=[{"id": "r1", "channel": "telegram", "rule_type": "new_filing_detected", "threshold": None}],
    )
    sent: list[str] = []
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY, settings=_settings(),
        send_email_fn=lambda **kwargs: None,
        send_telegram_fn=lambda **kwargs: sent.append(kwargs["title"]),
    )
    assert metrics["alerts_sent"] == 1
    assert metrics["alert_history_written"] == 1
    assert repo.inserted_history[0]["dedupe_key"] == f"{_COMPANY['id']}:new_filing:{_FILING['accession_number']}"


def test_missing_alert_config_records_failure():
    """When SMTP config is present but structurally invalid, the failure is sanitized."""
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )
    # smtp_enabled=True but smtp_host empty → adapter raises, we expect a sanitized failure record.
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY,
        settings=_settings(smtp_host=""),
        send_email_fn=send_email_alert,
        send_telegram_fn=lambda **kwargs: None,
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 1
    row = repo.inserted_history[0]
    assert row["status"] == "failed"
    # Error message must not contain any real credentials or configuration values.
    assert row["error_message"] is not None
    assert "secret" not in (row["error_message"] or "").lower()
    assert "password" not in (row["error_message"] or "").lower()


def test_email_adapter_sends_with_mocked_smtp():
    smtp_instance = MagicMock()
    smtp_context = MagicMock()
    smtp_context.__enter__.return_value = smtp_instance
    smtp_context.__exit__.return_value = None
    smtp_cls = MagicMock(return_value=smtp_context)
    send_email_alert(title="Alert", message="Body", settings=_settings(), smtp_cls=smtp_cls)
    smtp_instance.send_message.assert_called_once()


def test_telegram_adapter_sends_with_mocked_http():
    response = MagicMock()
    response.raise_for_status.return_value = None
    http_post = MagicMock(return_value=response)
    send_telegram_alert(title="Alert", message="Body", settings=_settings(), http_post=http_post)
    http_post.assert_called_once()


# ── New: global disable ───────────────────────────────────────────────────────


def test_global_alerts_disabled_returns_empty_counts():
    """When alerts_enabled=False, no rules are evaluated and counts are all zero."""
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY,
        settings=_settings(alerts_enabled=False),
        send_email_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not send")),
        send_telegram_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not send")),
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 0
    assert metrics["alerts_deduplicated"] == 0
    assert repo.inserted_history == []


def test_global_alerts_disabled_does_not_query_repo():
    """When globally disabled, no signal/rule reads are made."""
    class _StrictRepo(_FakeAlertRepo):
        def get_signal_runs_for_company(self, *a: Any, **kw: Any) -> list:  # type: ignore[override]
            raise AssertionError("should not read signal runs when globally disabled")

    metrics = process_company_alerts(
        _COMPANY["id"], _StrictRepo(), _SIGNAL_DATE, company=_COMPANY,
        settings=_settings(alerts_enabled=False),
        send_email_fn=lambda **kwargs: None,
        send_telegram_fn=lambda **kwargs: None,
    )
    assert metrics["alerts_sent"] == 0


# ── New: per-channel disable ──────────────────────────────────────────────────


def test_per_channel_email_disabled_no_history_write():
    """When smtp_enabled=False, matched email rule is silently skipped — no failed row."""
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY,
        settings=_settings(smtp_enabled=False),
        send_email_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not send")),
        send_telegram_fn=lambda **kwargs: None,
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 0
    assert repo.inserted_history == []


def test_per_channel_telegram_disabled_no_history_write():
    """When telegram_enabled=False, matched telegram rule is silently skipped — no failed row."""
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "telegram", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY,
        settings=_settings(telegram_enabled=False),
        send_email_fn=lambda **kwargs: None,
        send_telegram_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not send")),
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 0
    assert repo.inserted_history == []


# ── New: sanitized delivery errors ────────────────────────────────────────────


def test_delivery_failure_error_message_is_sanitized():
    """A delivery failure records only a short channel tag, never raw exc text."""
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )

    def _raise(**kwargs: Any) -> None:
        raise RuntimeError("connection failed: secret_token=abc123")

    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY, settings=_settings(),
        send_email_fn=_raise,
        send_telegram_fn=lambda **kwargs: None,
    )
    assert metrics["alerts_sent"] == 0
    assert metrics["alert_history_written"] == 1
    row = repo.inserted_history[0]
    assert row["status"] == "failed"
    err = row["error_message"] or ""
    assert "secret_token" not in err
    assert "abc123" not in err
    assert "smtp_send_failed" in err


def test_telegram_failure_does_not_leak_token():
    """Telegram delivery failures must not expose the bot token in persisted errors."""
    secret_token = "REAL_BOT_TOKEN_12345"
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[{"id": "r1", "channel": "telegram", "rule_type": "p_buy_adjusted_above", "threshold": 0.60}],
    )

    def _raise_with_token(**kwargs: Any) -> None:
        # Simulate httpx embedding the URL (which contains the token) in the error.
        raise RuntimeError(
            f"ConnectError: https://api.telegram.org/bot{secret_token}/sendMessage"
        )

    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY,
        settings=_settings(telegram_bot_token=secret_token),
        send_email_fn=lambda **kwargs: None,
        send_telegram_fn=_raise_with_token,
    )
    assert metrics["alert_history_written"] == 1
    row = repo.inserted_history[0]
    err = row["error_message"] or ""
    assert secret_token not in err
    assert "telegram_send_failed" in err


# ── New: deduplicated counter ─────────────────────────────────────────────────


def test_deduplicated_counter_increments_per_suppressed_rule():
    """Each suppressed duplicate increments alerts_deduplicated without a history write."""
    existing_key = f"{_COMPANY['id']}:p_buy_adjusted_above:{_SIGNAL_DATE}:0.6000:buy"
    repo = _FakeAlertRepo(
        signals=[_SIGNAL, _PREV_SIGNAL],
        valuations=[_VALUATION, _PREV_VALUATION],
        rules=[
            {"id": "r1", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60},
            {"id": "r2", "channel": "email", "rule_type": "p_buy_adjusted_above", "threshold": 0.60},
        ],
        history={existing_key: {"dedupe_key": existing_key}},
    )
    metrics = process_company_alerts(
        _COMPANY["id"], repo, _SIGNAL_DATE, company=_COMPANY, settings=_settings(),
        send_email_fn=lambda **kwargs: None,
        send_telegram_fn=lambda **kwargs: None,
    )
    # Both rules share the same dedupe_key; both should be suppressed.
    assert metrics["alerts_deduplicated"] == 2
    assert metrics["alert_history_written"] == 0
