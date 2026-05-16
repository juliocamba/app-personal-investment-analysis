from __future__ import annotations

from datetime import datetime, timezone

from investment_app.alerts.position_review import process_position_review_alerts


def _fixed_now() -> datetime:
    return datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)


def _position(**overrides):
    row = {
        "id": "pos-1",
        "user_id": "user-1",
        "company_id": "company-1",
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "status": "active",
        "currency": "USD",
        "price_currency": "USD",
        "price_date": "2026-05-16",
        "current_price": 230.0,
        "current_signal": "strong_sell",
        "current_readiness_status": "tracking_only",
        "current_data_quality_status": "critical",
    }
    row.update(overrides)
    return row


def _profile(**overrides):
    row = {
        "id": "profile-1",
        "position_id": "pos-1",
        "user_id": "user-1",
        "target_price": 220.0,
        "target_price_currency": "USD",
        "entry_signal": "buy",
        "entry_readiness_status": "analysis_ready",
        "entry_data_quality_status": "healthy",
    }
    row.update(overrides)
    return row


class _Repo:
    def __init__(self, *, positions, profiles, alerts=None):
        self._positions = list(positions)
        self._profiles = list(profiles)
        self._alerts = list(alerts or [])

    def list_dashboard_positions(self):
        return list(self._positions)

    def list_position_entry_profiles(self):
        return list(self._profiles)

    def list_position_review_alerts(self):
        return list(self._alerts)

    def insert_position_review_alert(self, row):
        saved = {"id": f"alert-{len(self._alerts) + 1}", **row}
        self._alerts.append(saved)
        return saved

    def update_position_review_alert(self, alert_id, fields):
        for idx, row in enumerate(self._alerts):
            if row["id"] == alert_id:
                updated = {**row, **fields}
                self._alerts[idx] = updated
                return updated
        raise AssertionError(f"unknown alert id {alert_id}")


def test_generates_only_requested_first_wave_review_alerts(monkeypatch) -> None:
    monkeypatch.setattr("investment_app.alerts.position_review.utc_now", _fixed_now)
    repo = _Repo(positions=[_position()], profiles=[_profile()])

    metrics = process_position_review_alerts(repo, "2026-05-16")

    assert metrics["position_review_positions_checked"] == 1
    assert metrics["position_review_alerts_opened"] == 4
    assert metrics["position_review_alerts_refreshed"] == 0
    assert metrics["position_review_alerts_resolved"] == 0
    assert {row["alert_type"] for row in repo._alerts} == {
        "target_price_reached",
        "signal_deterioration",
        "readiness_deterioration",
        "data_quality_deterioration",
    }


def test_refreshes_existing_alert_without_duplicate_insert(monkeypatch) -> None:
    monkeypatch.setattr("investment_app.alerts.position_review.utc_now", _fixed_now)
    existing = {
        "id": "alert-1",
        "position_id": "pos-1",
        "user_id": "user-1",
        "company_id": "company-1",
        "alert_type": "target_price_reached",
        "severity": "warning",
        "status": "open",
        "title": "Old title",
        "message": "Old message",
        "details": {},
        "dedupe_key": "pos-1:target_price_reached:220.0000:USD",
        "triggered_at": "2026-05-15T10:00:00+00:00",
        "first_seen_at": "2026-05-15T10:00:00+00:00",
        "last_seen_at": "2026-05-15T10:00:00+00:00",
        "resolved_at": None,
        "dismissed_at": None,
        "dismissed_reason": None,
        "snoozed_until": None,
        "created_at": "2026-05-15T10:00:00+00:00",
        "updated_at": "2026-05-15T10:00:00+00:00",
    }
    repo = _Repo(
        positions=[_position(current_signal="hold", current_readiness_status="analysis_ready", current_data_quality_status="healthy", current_price=225.0)],
        profiles=[_profile(entry_signal="strong_buy")],
        alerts=[existing],
    )

    metrics = process_position_review_alerts(repo, "2026-05-16")

    assert metrics["position_review_alerts_opened"] == 1
    assert metrics["position_review_alerts_refreshed"] == 1
    assert len(repo._alerts) == 2
    assert repo._alerts[0]["title"] == "AAPL target price reached"
    assert repo._alerts[0]["last_seen_at"] == "2026-05-16T10:00:00+00:00"


def test_resolves_alert_when_condition_disappears(monkeypatch) -> None:
    monkeypatch.setattr("investment_app.alerts.position_review.utc_now", _fixed_now)
    existing = {
        "id": "alert-1",
        "position_id": "pos-1",
        "user_id": "user-1",
        "company_id": "company-1",
        "alert_type": "target_price_reached",
        "severity": "warning",
        "status": "open",
        "title": "AAPL target price reached",
        "message": "The latest stored price has reached or exceeded the manual target price.",
        "details": {},
        "dedupe_key": "pos-1:target_price_reached:220.0000:USD",
        "triggered_at": "2026-05-15T10:00:00+00:00",
        "first_seen_at": "2026-05-15T10:00:00+00:00",
        "last_seen_at": "2026-05-15T10:00:00+00:00",
        "resolved_at": None,
        "dismissed_at": None,
        "dismissed_reason": None,
        "snoozed_until": None,
        "created_at": "2026-05-15T10:00:00+00:00",
        "updated_at": "2026-05-15T10:00:00+00:00",
    }
    repo = _Repo(
        positions=[_position(current_price=210.0, current_signal="buy", current_readiness_status="analysis_ready", current_data_quality_status="healthy")],
        profiles=[_profile()],
        alerts=[existing],
    )

    metrics = process_position_review_alerts(repo, "2026-05-16")

    assert metrics["position_review_alerts_opened"] == 0
    assert metrics["position_review_alerts_refreshed"] == 0
    assert metrics["position_review_alerts_resolved"] == 1
    assert repo._alerts[0]["status"] == "resolved"
    assert repo._alerts[0]["resolved_at"] == "2026-05-16T10:00:00+00:00"


def test_snoozed_alert_persists_without_duplicate_until_expiry(monkeypatch) -> None:
    monkeypatch.setattr("investment_app.alerts.position_review.utc_now", _fixed_now)
    existing = {
        "id": "alert-1",
        "position_id": "pos-1",
        "user_id": "user-1",
        "company_id": "company-1",
        "alert_type": "target_price_reached",
        "severity": "warning",
        "status": "snoozed",
        "title": "AAPL target price reached",
        "message": "The latest stored price has reached or exceeded the manual target price.",
        "details": {},
        "dedupe_key": "pos-1:target_price_reached:220.0000:USD",
        "triggered_at": "2026-05-15T10:00:00+00:00",
        "first_seen_at": "2026-05-15T10:00:00+00:00",
        "last_seen_at": "2026-05-15T10:00:00+00:00",
        "resolved_at": None,
        "dismissed_at": None,
        "dismissed_reason": None,
        "snoozed_until": "2026-06-15T10:00:00+00:00",
        "created_at": "2026-05-15T10:00:00+00:00",
        "updated_at": "2026-05-15T10:00:00+00:00",
    }
    repo = _Repo(
        positions=[_position(current_signal="buy", current_readiness_status="analysis_ready", current_data_quality_status="healthy", current_price=225.0)],
        profiles=[_profile(entry_signal="buy")],
        alerts=[existing],
    )

    metrics = process_position_review_alerts(repo, "2026-05-16")

    assert metrics["position_review_alerts_opened"] == 0
    assert metrics["position_review_alerts_refreshed"] == 1
    assert len(repo._alerts) == 1
    assert repo._alerts[0]["status"] == "snoozed"
    assert repo._alerts[0]["snoozed_until"] == "2026-06-15T10:00:00+00:00"
    assert repo._alerts[0]["last_seen_at"] == "2026-05-16T10:00:00+00:00"


def test_snoozed_alert_reopens_after_expiry_if_condition_persists(monkeypatch) -> None:
    monkeypatch.setattr("investment_app.alerts.position_review.utc_now", _fixed_now)
    existing = {
        "id": "alert-1",
        "position_id": "pos-1",
        "user_id": "user-1",
        "company_id": "company-1",
        "alert_type": "target_price_reached",
        "severity": "warning",
        "status": "snoozed",
        "title": "AAPL target price reached",
        "message": "The latest stored price has reached or exceeded the manual target price.",
        "details": {},
        "dedupe_key": "pos-1:target_price_reached:220.0000:USD",
        "triggered_at": "2026-05-15T10:00:00+00:00",
        "first_seen_at": "2026-05-15T10:00:00+00:00",
        "last_seen_at": "2026-05-15T10:00:00+00:00",
        "resolved_at": None,
        "dismissed_at": None,
        "dismissed_reason": None,
        "snoozed_until": "2026-05-01T10:00:00+00:00",
        "created_at": "2026-05-15T10:00:00+00:00",
        "updated_at": "2026-05-15T10:00:00+00:00",
    }
    repo = _Repo(
        positions=[_position(current_signal="buy", current_readiness_status="analysis_ready", current_data_quality_status="healthy", current_price=225.0)],
        profiles=[_profile(entry_signal="buy")],
        alerts=[existing],
    )

    metrics = process_position_review_alerts(repo, "2026-05-16")

    assert metrics["position_review_alerts_opened"] == 0
    assert metrics["position_review_alerts_refreshed"] == 1
    assert repo._alerts[0]["status"] == "open"
    assert repo._alerts[0]["snoozed_until"] is None


def test_dismissed_alert_does_not_duplicate_for_same_dedupe(monkeypatch) -> None:
    monkeypatch.setattr("investment_app.alerts.position_review.utc_now", _fixed_now)
    existing = {
        "id": "alert-1",
        "position_id": "pos-1",
        "user_id": "user-1",
        "company_id": "company-1",
        "alert_type": "target_price_reached",
        "severity": "warning",
        "status": "dismissed",
        "title": "AAPL target price reached",
        "message": "The latest stored price has reached or exceeded the manual target price.",
        "details": {},
        "dedupe_key": "pos-1:target_price_reached:220.0000:USD",
        "triggered_at": "2026-05-15T10:00:00+00:00",
        "first_seen_at": "2026-05-15T10:00:00+00:00",
        "last_seen_at": "2026-05-15T10:00:00+00:00",
        "resolved_at": None,
        "dismissed_at": "2026-05-15T11:00:00+00:00",
        "dismissed_reason": "dismissed_in_ui",
        "snoozed_until": None,
        "created_at": "2026-05-15T10:00:00+00:00",
        "updated_at": "2026-05-15T10:00:00+00:00",
    }
    repo = _Repo(
        positions=[_position(current_signal="buy", current_readiness_status="analysis_ready", current_data_quality_status="healthy", current_price=225.0)],
        profiles=[_profile(entry_signal="buy")],
        alerts=[existing],
    )

    metrics = process_position_review_alerts(repo, "2026-05-16")

    assert metrics["position_review_alerts_opened"] == 0
    assert metrics["position_review_alerts_refreshed"] == 1
    assert len(repo._alerts) == 1
    assert repo._alerts[0]["status"] == "dismissed"
    assert repo._alerts[0]["dismissed_reason"] == "dismissed_in_ui"


def test_materially_new_dedupe_opens_new_alert_after_previous_dismissal(monkeypatch) -> None:
    monkeypatch.setattr("investment_app.alerts.position_review.utc_now", _fixed_now)
    existing = {
        "id": "alert-1",
        "position_id": "pos-1",
        "user_id": "user-1",
        "company_id": "company-1",
        "alert_type": "target_price_reached",
        "severity": "warning",
        "status": "dismissed",
        "title": "AAPL target price reached",
        "message": "The latest stored price has reached or exceeded the manual target price.",
        "details": {},
        "dedupe_key": "pos-1:target_price_reached:220.0000:USD",
        "triggered_at": "2026-05-15T10:00:00+00:00",
        "first_seen_at": "2026-05-15T10:00:00+00:00",
        "last_seen_at": "2026-05-15T10:00:00+00:00",
        "resolved_at": None,
        "dismissed_at": "2026-05-15T11:00:00+00:00",
        "dismissed_reason": "dismissed_in_ui",
        "snoozed_until": None,
        "created_at": "2026-05-15T10:00:00+00:00",
        "updated_at": "2026-05-15T10:00:00+00:00",
    }
    repo = _Repo(
        positions=[_position(current_signal="buy", current_readiness_status="analysis_ready", current_data_quality_status="healthy", current_price=235.0)],
        profiles=[_profile(target_price=230.0, entry_signal="buy")],
        alerts=[existing],
    )

    metrics = process_position_review_alerts(repo, "2026-05-16")

    assert metrics["position_review_alerts_opened"] == 1
    assert metrics["position_review_alerts_refreshed"] == 0
    assert metrics["position_review_alerts_resolved"] == 1
    assert len(repo._alerts) == 2
    assert {row["status"] for row in repo._alerts} == {"open", "resolved"}
