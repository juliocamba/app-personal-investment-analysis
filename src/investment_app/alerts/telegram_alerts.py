"""Telegram Bot API alert adapter for Phase 7."""
from __future__ import annotations

from typing import Any, Callable

import httpx


def _telegram_config_error(settings: Any) -> ValueError:
	return ValueError("Telegram alerts are disabled or missing required Telegram configuration")


def _escape_markdown_v2(text: str) -> str:
	"""Escape Telegram MarkdownV2 control characters."""
	chars = "_[]()~`>#+-=|{}.!"
	escaped = text
	for char in chars:
		escaped = escaped.replace(char, f"\\{char}")
	return escaped


def send_telegram_alert(
	*,
	title: str,
	message: str,
	settings: Any,
	http_post: Callable[..., Any] = httpx.post,
) -> None:
	"""Send a Telegram message via Bot API using MarkdownV2-safe text."""
	if not getattr(settings, "telegram_enabled", False):
		raise _telegram_config_error(settings)

	bot_token = getattr(settings, "telegram_bot_token", "")
	chat_id = getattr(settings, "telegram_chat_id", "")
	if not bot_token or not chat_id:
		raise _telegram_config_error(settings)

	payload = {
		"chat_id": chat_id,
		"text": f"*{_escape_markdown_v2(title)}*\n{_escape_markdown_v2(message)}",
		"parse_mode": "MarkdownV2",
		"disable_web_page_preview": True,
	}
	response = http_post(
		f"https://api.telegram.org/bot{bot_token}/sendMessage",
		json=payload,
		timeout=10,
	)
	if hasattr(response, "raise_for_status"):
		response.raise_for_status()
