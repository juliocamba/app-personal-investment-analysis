"""SMTP email alert adapter for Phase 7."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any


def _email_config_error(settings: Any) -> ValueError:
	return ValueError("Email alerts are disabled or missing required SMTP configuration")


def send_email_alert(
	*,
	title: str,
	message: str,
	settings: Any,
	smtp_cls: Any = smtplib.SMTP,
) -> None:
	"""Send a plain-text email alert using SMTP."""
	if not getattr(settings, "smtp_enabled", False):
		raise _email_config_error(settings)

	smtp_host = getattr(settings, "smtp_host", "")
	smtp_port = int(getattr(settings, "smtp_port", 587) or 587)
	email_from = getattr(settings, "alert_email_from", "")
	email_to = getattr(settings, "alert_email_to", "")
	if not smtp_host or not email_from or not email_to:
		raise _email_config_error(settings)

	email = EmailMessage()
	email["Subject"] = title
	email["From"] = email_from
	email["To"] = email_to
	email.set_content(message)

	smtp_user = getattr(settings, "smtp_user", "")
	smtp_password = getattr(settings, "smtp_password", "")

	with smtp_cls(smtp_host, smtp_port, timeout=10) as smtp:
		if hasattr(smtp, "ehlo"):
			smtp.ehlo()
		if hasattr(smtp, "starttls"):
			smtp.starttls()
			if hasattr(smtp, "ehlo"):
				smtp.ehlo()
		if smtp_user and smtp_password and hasattr(smtp, "login"):
			smtp.login(smtp_user, smtp_password)
		smtp.send_message(email)
